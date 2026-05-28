from models.schemas import TradeAction, ScoreBreakdown, SentimentResult, MarketData
from services.market import calculate_market_score
from services.sentiment import calculate_news_score
import os


def calculate_total_score(
    sentiments: list[SentimentResult],
    market_data: MarketData,
    fear_greed_index: float = 50.0,
) -> tuple[float, ScoreBreakdown]:

    news_score = calculate_news_score(sentiments)
    market_scores = calculate_market_score(market_data)

    # Fear & Greed: <25 → extreme fear → possible buy, >75 → extreme greed → caution
    fear_greed_score = 0.0
    if fear_greed_index < 25:
        fear_greed_score = 2.0
    elif fear_greed_index > 75:
        fear_greed_score = -2.0

    total = (
        news_score
        + market_scores["rsi_score"]
        + market_scores["macd_score"]
        + market_scores["volume_score"]
        + fear_greed_score
    )

    breakdown = ScoreBreakdown(
        news_score=round(news_score, 2),
        rsi_score=market_scores["rsi_score"],
        macd_score=market_scores["macd_score"],
        volume_score=market_scores["volume_score"],
        fear_greed_score=fear_greed_score,
        total=round(total, 2),
    )

    return round(total, 2), breakdown


def determine_action(score: float) -> TradeAction:
    notify_min = float(os.getenv("SCORE_NOTIFY_MIN", 10))
    auto_trade_min = float(os.getenv("SCORE_AUTO_TRADE_MIN", 20))

    abs_score = abs(score)
    if abs_score >= auto_trade_min:
        return TradeAction.AUTO_TRADE
    elif abs_score >= notify_min:
        return TradeAction.NOTIFY
    return TradeAction.IGNORE


def build_reasoning(score: float, breakdown: ScoreBreakdown, action: TradeAction) -> str:
    direction = "매수" if score > 0 else "매도"
    parts = [f"총점: {score:.1f} ({direction} 신호)"]

    if breakdown.news_score != 0:
        parts.append(f"뉴스 감성: {breakdown.news_score:+.1f}")
    if breakdown.rsi_score != 0:
        parts.append(f"RSI: {breakdown.rsi_score:+.1f}")
    if breakdown.macd_score != 0:
        parts.append(f"MACD: {breakdown.macd_score:+.1f}")
    if breakdown.volume_score != 0:
        parts.append(f"거래량: {breakdown.volume_score:+.1f}")
    if breakdown.fear_greed_score != 0:
        parts.append(f"공포/탐욕: {breakdown.fear_greed_score:+.1f}")

    action_str = {
        TradeAction.IGNORE: "→ 무시",
        TradeAction.NOTIFY: "→ 사용자 승인 요청",
        TradeAction.AUTO_TRADE: "→ 자동 거래 실행",
    }[action]
    parts.append(action_str)

    return " | ".join(parts)
