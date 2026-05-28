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


# ── Backtesting ─────────────────────────────────────────────────────────────

class BacktestConfig(BaseModel):
    symbol: str = "BTCUSDT"
    days: int = Field(default=30, ge=1, le=365)
    initial_capital: float = Field(default=10000.0, gt=0)
    position_pct: float = Field(default=10.0, gt=0, le=100)
    # interval: 60=1h, 240=4h, D=daily
    interval: str = Field(default="240", pattern=r"^(60|120|240|360|720|D)$")
    # Fixed inputs replacing live news / fear-greed during simulation
    news_score: float = Field(default=0.0, ge=-7.0, le=7.0)
    fear_greed: float = Field(default=50.0, ge=0, le=100)
    # Score thresholds (lower than live defaults so pure-technical signals fire)
    entry_score: float = Field(default=8.0)
    exit_score: float = Field(default=-5.0)


class RiskStatus(BaseModel):
    consecutive_losses: int
    max_consecutive_losses: int
    daily_loss_usdt: float
    max_daily_loss_pct: float
    trading_halted: bool
    halted_reason: str
    last_reset_date: str


class BacktestTrade(BaseModel):
    index: int
    side: str
    price: float
    qty: float
    pnl_usdt: float
    pnl_pct: float
    score: float


class BacktestResult(BaseModel):
    symbol: str
    days: int
    initial_capital: float
    final_capital: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    sharpe_ratio: Optional[float] = None
    total_trades: int
    winning_trades: int
    losing_trades: int
    candles_analyzed: int
    trades: list[BacktestTrade]
