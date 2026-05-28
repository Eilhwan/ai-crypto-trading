import numpy as np
import pandas as pd
import uuid
import os
from loguru import logger

MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

_POSITIVE_KEYWORDS = {"etf", "approved", "surge", "bull", "rally", "gain", "buy", "record", "high", "adoption"}
_NEGATIVE_KEYWORDS = {"crash", "ban", "hack", "plunge", "drop", "sell", "fear", "loss", "bearish", "fraud"}


def is_mock() -> bool:
    return MOCK_MODE


def mock_sentiment(title: str, content: str = "") -> dict:
    text = (title + " " + content).lower()

    pos = sum(1 for w in _POSITIVE_KEYWORDS if w in text)
    neg = sum(1 for w in _NEGATIVE_KEYWORDS if w in text)

    rng = np.random.default_rng(abs(hash(title)) % (2**31))
    noise = rng.uniform(0.05, 0.15)

    if pos > neg:
        confidence = round(min(0.6 + pos * 0.1 + noise, 0.97), 4)
        return {"label": "positive", "score": confidence}
    elif neg > pos:
        confidence = round(min(0.6 + neg * 0.1 + noise, 0.97), 4)
        return {"label": "negative", "score": confidence}
    else:
        confidence = round(0.5 + noise, 4)
        return {"label": "neutral", "score": confidence}


_MOCK_SCENARIO = os.getenv("MOCK_SCENARIO", "default")


def mock_klines(symbol: str, limit: int = 100) -> pd.DataFrame:
    base_prices = {"BTCUSDT": 65000.0, "ETHUSDT": 3200.0, "SOLUSDT": 145.0}
    base = base_prices.get(symbol, 50000.0)

    now_ms = 1747353600000
    timestamps = [now_ms - (limit - i) * 3_600_000 for i in range(limit)]

    if _MOCK_SCENARIO == "bullish":
        # Generates: RSI oversold → +3, MACD golden cross → +5, volume spike → +4
        rng = np.random.default_rng(7)
        # Sharp drop then strong recovery → oversold RSI, MACD crossover
        half = limit // 2
        down = base * np.cumprod(1 + rng.normal(-0.008, 0.005, half))
        up = down[-1] * np.cumprod(1 + rng.normal(0.012, 0.004, limit - half))
        closes = np.concatenate([down, up])
    elif _MOCK_SCENARIO == "bearish":
        # Generates: RSI overbought → -3, MACD death cross → -5
        rng = np.random.default_rng(13)
        up = base * np.cumprod(1 + rng.normal(0.010, 0.005, limit // 2))
        down = up[-1] * np.cumprod(1 + rng.normal(-0.006, 0.005, limit - limit // 2))
        closes = np.concatenate([up, down])
    else:
        rng = np.random.default_rng(42)
        closes = base * np.cumprod(1 + rng.normal(0.0002, 0.012, limit))

    rng2 = np.random.default_rng(99)
    opens = np.roll(closes, 1)
    opens[0] = base
    highs = closes * rng2.uniform(1.001, 1.015, limit)
    lows = closes * rng2.uniform(0.985, 0.999, limit)
    volumes = rng2.uniform(500, 3000, limit)
    vol_mult = 2.6 if _MOCK_SCENARIO == "bullish" else 1.8
    volumes[-1] = volumes[:-1].mean() * vol_mult

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens.round(2),
        "high": highs.round(2),
        "low": lows.round(2),
        "close": closes.round(2),
        "volume": volumes.round(4),
        "turnover": (closes * volumes).round(2),
    })
    return df


_SCENARIO_MARKET = {
    "bullish": {
        "price": 63500.0,
        "rsi": 27.3,          # oversold → +3
        "macd": 350.5,        # golden cross → +5
        "macd_signal": 210.2,
        "volume_change_pct": 162.0,  # > 150% → +4
        "bb_upper": 70000.0,
        "bb_lower": 60000.0,
    },
    "bearish": {
        "price": 58000.0,
        "rsi": 74.8,          # overbought → -3
        "macd": -280.0,       # death cross → -5
        "macd_signal": -150.0,
        "volume_change_pct": -65.0,  # shrinking volume → -2
        "bb_upper": 65000.0,
        "bb_lower": 55000.0,
    },
}


def mock_market_data(symbol: str):
    from models.schemas import MarketData
    preset = _SCENARIO_MARKET.get(_MOCK_SCENARIO)
    if preset is None:
        return None
    return MarketData(symbol=symbol, **preset)


def mock_order_id() -> str:
    return f"MOCK-{uuid.uuid4().hex[:16].upper()}"


def mock_wallet_equity() -> float:
    return 1000.0


def log_mock(label: str) -> None:
    logger.debug(f"[MOCK] {label}")
