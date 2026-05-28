import os
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from models.schemas import AnalyzeResponse, TradeAction
from database.db import AsyncSessionLocal, AnalysisLog

scheduler = AsyncIOScheduler()

_last_run: Optional[datetime] = None
_last_run_articles: int = 0


async def run_analysis_cycle() -> None:
    global _last_run, _last_run_articles

    from services.news_collector import collect_news
    from services.fear_greed import get_fear_greed
    from services.sentiment import analyze_sentiment
    from services.market import get_market_data
    from services.scoring import calculate_total_score, determine_action, build_reasoning
    from services.notifier import notify_analysis, notify_trade
    from traders.bybit_trader import execute_trade, build_trade_signal

    _last_run = datetime.now(timezone.utc)

    symbols = [s.strip() for s in os.getenv("WATCH_SYMBOLS", "BTCUSDT").split(",") if s.strip()]

    logger.info(f"Scheduler cycle — symbols={symbols}")

    news = await collect_news()
    _last_run_articles = len(news)

    if not news:
        logger.info("No new articles — skipping analysis cycle")
        return

    fg = await get_fear_greed()
    sentiments = await analyze_sentiment(news)

    for symbol in symbols:
        try:
            market_data = await get_market_data(symbol)
            score, breakdown = calculate_total_score(sentiments, market_data, fg)
            action = determine_action(score)
            reasoning = build_reasoning(score, breakdown, action)

            async with AsyncSessionLocal() as db:
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
                result = await execute_trade(signal)
                logger.info(f"[{symbol}] auto-trade: {result.message}")
                await notify_trade(result)

            if action in (TradeAction.NOTIFY, TradeAction.AUTO_TRADE):
                await notify_analysis(response)

            logger.info(f"[{symbol}] score={score:.2f} action={action.value}")

        except Exception as e:
            logger.error(f"[{symbol}] cycle error: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    interval = int(os.getenv("SCHEDULE_INTERVAL_MIN", 30))

    scheduler.add_job(
        run_analysis_cycle,
        IntervalTrigger(minutes=interval),
        id="analysis_cycle",
        replace_existing=True,
    )

    from services.news_collector import cleanup_seen_urls
    scheduler.add_job(
        cleanup_seen_urls,
        IntervalTrigger(hours=24),
        id="cleanup_seen_urls",
        replace_existing=True,
    )

    logger.info(f"Scheduler configured: interval={interval}min")
    return scheduler


def get_scheduler_status():
    from models.schemas import SchedulerStatus

    interval = int(os.getenv("SCHEDULE_INTERVAL_MIN", 30))
    symbols = [s.strip() for s in os.getenv("WATCH_SYMBOLS", "BTCUSDT").split(",") if s.strip()]

    job = scheduler.get_job("analysis_cycle")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return SchedulerStatus(
        running=scheduler.running,
        interval_minutes=interval,
        watch_symbols=symbols,
        next_run=next_run,
        last_run=_last_run.isoformat() if _last_run else None,
        last_run_articles=_last_run_articles,
    )
