import pandas as pd
import pandas_ta as ta
from loguru import logger
from models.schemas import MarketData
from utils.mock import is_mock, mock_klines, log_mock
import os


def _get_bybit_client(testnet: bool = None):
    from pybit.unified_trading import HTTP  # lazy: only imported when not in mock mode
    use_testnet = testnet if testnet is not None else os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    return HTTP(
        testnet=use_testnet,
        api_key=os.getenv("BYBIT_API_KEY", ""),
        api_secret=os.getenv("BYBIT_API_SECRET", ""),
    )


def fetch_klines(symbol: str, interval: str = "60", limit: int = 100) -> pd.DataFrame:
    client = _get_bybit_client()
    resp = client.get_kline(symbol=symbol, interval=interval, limit=limit)

    if resp["retCode"] != 0:
        raise RuntimeError(f"Bybit kline error: {resp['retMsg']}")

    rows = resp["result"]["list"]
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
    df["timestamp"] = pd.to_numeric(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def compute_indicators(df: pd.DataFrame) -> dict:
    close = df["close"]
    volume = df["volume"]

    rsi_series = ta.rsi(close, length=14)
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    bb_df = ta.bbands(close, length=20, std=2)

    rsi = float(rsi_series.iloc[-1]) if rsi_series is not None else None

    macd_val = macd_signal = None
    if macd_df is not None:
        macd_col = next((c for c in macd_df.columns if c.startswith("MACD_")), None)
        sig_col = next((c for c in macd_df.columns if c.startswith("MACDs_")), None)
        if macd_col:
            macd_val = float(macd_df[macd_col].iloc[-1])
        if sig_col:
            macd_signal = float(macd_df[sig_col].iloc[-1])

    bb_upper = bb_lower = None
    if bb_df is not None:
        upper_col = next((c for c in bb_df.columns if c.startswith("BBU_")), None)
        lower_col = next((c for c in bb_df.columns if c.startswith("BBL_")), None)
        if upper_col:
            bb_upper = float(bb_df[upper_col].iloc[-1])
        if lower_col:
            bb_lower = float(bb_df[lower_col].iloc[-1])

    vol_change_pct = None
    if len(volume) >= 20:
        avg_vol = volume.iloc[-20:-1].mean()
        if avg_vol > 0:
            vol_change_pct = round((volume.iloc[-1] - avg_vol) / avg_vol * 100, 2)

    return {
        "rsi": round(rsi, 2) if rsi is not None else None,
        "macd": round(macd_val, 4) if macd_val is not None else None,
        "macd_signal": round(macd_signal, 4) if macd_signal is not None else None,
        "bb_upper": round(bb_upper, 2) if bb_upper is not None else None,
        "bb_lower": round(bb_lower, 2) if bb_lower is not None else None,
        "volume_change_pct": vol_change_pct,
        "price": round(float(df["close"].iloc[-1]), 2),
    }


async def get_market_data(symbol: str) -> MarketData:
    try:
        if is_mock():
            from utils.mock import mock_market_data
            log_mock(f"market data for {symbol}")
            override = mock_market_data(symbol)
            if override is not None:
                return override
            df = mock_klines(symbol)
        else:
            df = fetch_klines(symbol)
        indicators = compute_indicators(df)
        return MarketData(symbol=symbol, **indicators)
    except Exception as e:
        logger.error(f"Market data fetch failed for {symbol}: {e}")
        return MarketData(symbol=symbol, price=0.0)


def calculate_market_score(data: MarketData) -> dict:
    scores = {"rsi_score": 0.0, "macd_score": 0.0, "volume_score": 0.0}

    if data.rsi is not None:
        if data.rsi < 30:
            scores["rsi_score"] = 3.0  # oversold → buy signal
        elif data.rsi > 70:
            scores["rsi_score"] = -3.0  # overbought → sell signal

    if data.macd is not None and data.macd_signal is not None:
        if data.macd > data.macd_signal:
            scores["macd_score"] = 5.0  # golden cross
        elif data.macd < data.macd_signal:
            scores["macd_score"] = -5.0  # death cross

    if data.volume_change_pct is not None:
        if data.volume_change_pct >= 150:
            scores["volume_score"] = 4.0
        elif data.volume_change_pct >= 50:
            scores["volume_score"] = 2.0
        elif data.volume_change_pct <= -50:
            scores["volume_score"] = -2.0

    return scores
