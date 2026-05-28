import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from loguru import logger

from models.schemas import (
    AnalyzeRequest, AnalyzeResponse, TradeAction, TradeResult, MarketData,
    WebhookNewsRequest, FearGreedResponse, SchedulerStatus,
    BacktestConfig, BacktestResult,
)
from services.sentiment import analyze_sentiment
from services.market import get_market_data
from services.scoring import calculate_total_score, determine_action, build_reasoning
from services.notifier import notify_analysis, notify_trade
from services.fear_greed import get_fear_greed, get_fear_greed_response
from services.scheduler import get_scheduler_status, run_analysis_cycle
from traders.bybit_trader import execute_trade, build_trade_signal
from backtest.engine import run_backtest
from database.db import get_db, AnalysisLog, TradeLog, BacktestLog

router = APIRouter()


async def _run_analyze(
    news,
    symbol: str,
    fear_greed_index,
    db: AsyncSession,
) -> AnalyzeResponse:
    if fear_greed_index is None:
        fear_greed_index = await get_fear_greed()

    sentiments = await analyze_sentiment(news)
    market_data = await get_market_data(symbol)
    score, breakdown = calculate_total_score(sentiments, market_data, fear_greed_index)
    action = determine_action(score)
    reasoning = build_reasoning(score, breakdown, action)

    db.add(AnalysisLog(
        symbol=symbol,
        score=score,
        action=action.value,
        news_summary="; ".join(n.title for n in news[:5]),
        reasoning=reasoning,
    ))
    await db.commit()

    response = AnalyzeResponse(
        symbol=symbol,
        score=score,
        action=action,
        breakdown=breakdown,
        sentiments=sentiments,
        reasoning=reasoning,
    )

    if action == TradeAction.AUTO_TRADE:
        signal = build_trade_signal(symbol=symbol, score=score, qty=0.001, reason=reasoning)
        trade_result = await execute_trade(signal)
        logger.info(f"Auto trade result: {trade_result.message}")
        await notify_trade(trade_result)

    if action in (TradeAction.NOTIFY, TradeAction.AUTO_TRADE):
        await notify_analysis(response)

    return response


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Analyze request: {len(request.news)} news items for {request.symbol}")
    return await _run_analyze(request.news, request.symbol, request.fear_greed_index, db)


@router.post("/webhook/news", response_model=AnalyzeResponse)
async def webhook_news(request: WebhookNewsRequest, db: AsyncSession = Depends(get_db)):
    expected = os.getenv("WEBHOOK_TOKEN", "")
    if not expected or request.token != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    logger.info(f"Webhook: {len(request.news)} news items for {request.symbol}")
    return await _run_analyze(request.news, request.symbol, request.fear_greed_index, db)


@router.get("/fear-greed", response_model=FearGreedResponse)
async def fear_greed():
    return await get_fear_greed_response()


@router.get("/scheduler/status", response_model=SchedulerStatus)
async def scheduler_status():
    return get_scheduler_status()


@router.post("/scheduler/trigger")
async def scheduler_trigger():
    logger.info("Manual scheduler trigger requested")
    asyncio.create_task(run_analysis_cycle())
    return {"message": "Analysis cycle triggered"}


# ── Backtesting ──────────────────────────────────────────────────────────────

@router.post("/backtest/run", response_model=BacktestResult)
async def backtest_run(config: BacktestConfig, db: AsyncSession = Depends(get_db)):
    logger.info(f"Backtest request: {config.symbol} {config.days}d interval={config.interval}")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, run_backtest, config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.add(BacktestLog(
        symbol=result.symbol,
        days=result.days,
        interval=config.interval,
        initial_capital=result.initial_capital,
        final_capital=result.final_capital,
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        win_rate=result.win_rate,
        sharpe_ratio=result.sharpe_ratio or 0.0,
        total_trades=result.total_trades,
        candles_analyzed=result.candles_analyzed,
    ))
    await db.commit()
    return result


@router.get("/backtest/results")
async def backtest_results(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BacktestLog).order_by(desc(BacktestLog.created_at)).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "days": r.days,
            "interval": r.interval,
            "total_return_pct": r.total_return_pct,
            "max_drawdown_pct": r.max_drawdown_pct,
            "win_rate": r.win_rate,
            "sharpe_ratio": r.sharpe_ratio,
            "total_trades": r.total_trades,
            "candles_analyzed": r.candles_analyzed,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/market/{symbol}", response_model=MarketData)
async def market(symbol: str):
    return await get_market_data(symbol)


@router.post("/trade/manual", response_model=TradeResult)
async def manual_trade(symbol: str, side: str, qty: float, db: AsyncSession = Depends(get_db)):
    if side not in ("Buy", "Sell"):
        raise HTTPException(status_code=400, detail="side must be 'Buy' or 'Sell'")

    signal = build_trade_signal(symbol=symbol, score=1.0 if side == "Buy" else -1.0, qty=qty, reason="수동 거래")
    result = await execute_trade(signal)

    if result.signal:
        db.add(TradeLog(
            symbol=symbol,
            side=side,
            qty=qty,
            price=0.0,
            order_id=result.order_id or "",
            score=0.0,
            success=result.success,
            reason="수동 거래",
        ))
        await db.commit()

    return result


@router.get("/logs/analysis")
async def analysis_logs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AnalysisLog).order_by(desc(AnalysisLog.created_at)).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "score": r.score,
            "action": r.action,
            "reasoning": r.reasoning,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/logs/trades")
async def trade_logs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TradeLog).order_by(desc(TradeLog.created_at)).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "side": r.side,
            "qty": r.qty,
            "order_id": r.order_id,
            "success": r.success,
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/health")
async def health():
    return {"status": "ok"}
