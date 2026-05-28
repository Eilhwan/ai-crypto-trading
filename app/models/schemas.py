from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class TradeAction(str, Enum):
    IGNORE = "ignore"
    NOTIFY = "notify"
    AUTO_TRADE = "auto_trade"


class NewsItem(BaseModel):
    title: str
    content: Optional[str] = ""
    source: Optional[str] = ""


class AnalyzeRequest(BaseModel):
    news: list[NewsItem]
    symbol: str = "BTCUSDT"
    fear_greed_index: Optional[float] = None  # None = auto-fetch from API


class SentimentResult(BaseModel):
    title: str
    sentiment: str
    score: float
    confidence: float


class ScoreBreakdown(BaseModel):
    news_score: float = 0.0
    rsi_score: float = 0.0
    macd_score: float = 0.0
    volume_score: float = 0.0
    fear_greed_score: float = 0.0
    total: float = 0.0


class AnalyzeResponse(BaseModel):
    symbol: str
    score: float
    action: TradeAction
    breakdown: ScoreBreakdown
    sentiments: list[SentimentResult]
    reasoning: str


class TradeSignal(BaseModel):
    symbol: str
    side: str  # Buy / Sell
    qty: float
    score: float
    reason: str


class TradeResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    message: str
    signal: Optional[TradeSignal] = None


class MarketData(BaseModel):
    symbol: str
    price: float
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    volume_change_pct: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None


class WebhookNewsRequest(BaseModel):
    token: str
    symbol: str = "BTCUSDT"
    news: list[NewsItem]
    fear_greed_index: Optional[float] = None


class FearGreedResponse(BaseModel):
    value: float
    classification: str
    cached: bool
    fetched_at: Optional[str] = None


class SchedulerStatus(BaseModel):
    running: bool
    interval_minutes: int
    watch_symbols: list[str]
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    last_run_articles: int = 0
