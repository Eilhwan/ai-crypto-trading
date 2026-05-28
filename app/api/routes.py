from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from loguru import logger

from models.schemas import (
    AnalyzeRequest, AnalyzeResponse, TradeAction, TradeResult, MarketData
)
from services.sentiment import analyze_sentiment
from services.market import get_market_data
from services.scoring import calculate_total_score, determine_action, build_reasoning
from traders.bybit_trader import execute_trade, build_trade_signal
from database.db import get_db, AnalysisLog, TradeLog

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    logger.info(f"Analyze request: {len(request.news)} news items for {request.symbol}")

    sentiments = await analyze_sentiment(request.news)
    market_data = await get_market_data(request.symbol)
    score, breakdown = calculate_total_score(sentiments, market_data, request.fear_greed_index)
    action = determine_action(score)
    reasoning = build_reasoning(score, breakdown, action)

    log = AnalysisLog(
        symbol=request.symbol,
        score=score,
        action=action.value,
        news_summary="; ".join(n.title for n in request.news[:5]),
        reasoning=reasoning,
    )
    db.add(log)
    await db.commit()

    if action == TradeAction.AUTO_TRADE:
        signal = build_trade_signal(
            symbol=request.symbol,
            score=score,
            qty=0.001,  # 초기: 최소 수량으로 고정
            reason=reasoning,
        )
        trade_result = await execute_trade(signal)
        logger.info(f"Auto trade result: {trade_result.message}")

    return AnalyzeResponse(
        symbol=request.symbol,
        score=score,
        action=action,
        breakdown=breakdown,
        sentiments=sentiments,
        reasoning=reasoning,
    )


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
        log = TradeLog(
            symbol=symbol,
            side=side,
            qty=qty,
            price=0.0,
            order_id=result.order_id or "",
            score=0.0,
            success=result.success,
            reason="수동 거래",
        )
        db.add(log)
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
