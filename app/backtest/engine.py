import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger

from models.schemas import BacktestConfig, BacktestResult, BacktestTrade

_INTERVAL_HOURS = {"60": 1, "120": 2, "240": 4, "360": 6, "720": 12, "D": 24}


def _fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    from utils.mock import is_mock
    if is_mock():
        from utils.mock import mock_klines
        return mock_klines(symbol, limit=limit)

    from services.market import _get_bybit_client
    client = _get_bybit_client(testnet=False)
    resp = client.get_kline(symbol=symbol, interval=interval, limit=limit)
    if resp["retCode"] != 0:
        raise RuntimeError(f"Kline fetch failed: {resp['retMsg']}")

    rows = resp["result"]["list"]
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
    df["timestamp"] = pd.to_numeric(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    volume = df["volume"]

    df["rsi"] = ta.rsi(close, length=14)

    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    if macd_df is not None:
        macd_col = next((c for c in macd_df.columns if c.startswith("MACD_")), None)
        sig_col = next((c for c in macd_df.columns if c.startswith("MACDs_")), None)
        df["macd"] = macd_df[macd_col] if macd_col else np.nan
        df["macd_signal"] = macd_df[sig_col] if sig_col else np.nan
    else:
        df["macd"] = np.nan
        df["macd_signal"] = np.nan

    vol_avg = volume.rolling(20).mean().shift(1)
    df["vol_change_pct"] = ((volume - vol_avg) / vol_avg * 100).where(vol_avg > 0, other=np.nan)

    return df.dropna(subset=["rsi", "macd"]).reset_index(drop=True)


def _score_row(row: pd.Series, news_score: float, fear_greed: float) -> float:
    rsi_score = 0.0
    rsi = row.get("rsi")
    if pd.notna(rsi):
        if rsi < 30:
            rsi_score = 3.0
        elif rsi > 70:
            rsi_score = -3.0

    macd_score = 0.0
    macd = row.get("macd")
    macd_sig = row.get("macd_signal")
    if pd.notna(macd) and pd.notna(macd_sig):
        macd_score = 5.0 if macd > macd_sig else -5.0

    vol_score = 0.0
    vcp = row.get("vol_change_pct")
    if pd.notna(vcp):
        if vcp >= 150:
            vol_score = 4.0
        elif vcp >= 50:
            vol_score = 2.0
        elif vcp <= -50:
            vol_score = -2.0

    fg_score = 2.0 if fear_greed < 25 else (-2.0 if fear_greed > 75 else 0.0)

    return news_score + rsi_score + macd_score + vol_score + fg_score


def run_backtest(config: BacktestConfig) -> BacktestResult:
    hours_per_candle = _INTERVAL_HOURS.get(config.interval, 4)
    candles_needed = min(int(config.days * 24 / hours_per_candle) + 60, 1000)

    df = _fetch_klines(config.symbol, config.interval, candles_needed)
    df = _add_indicators(df)

    if len(df) < 10:
        raise ValueError(f"Not enough candles after indicator warmup: {len(df)}")

    capital = config.initial_capital
    position_qty = 0.0
    entry_price = 0.0
    peak_equity = capital
    max_drawdown = 0.0
    trades: list[BacktestTrade] = []
    returns: list[float] = []
    prev_equity = capital

    for i, row in df.iterrows():
        price = float(row["close"])
        score = round(_score_row(row, config.news_score, config.fear_greed), 2)
        equity = capital + position_qty * price

        # Drawdown tracking
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity * 100
        if dd > max_drawdown:
            max_drawdown = dd

        # Period return
        returns.append((equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0)
        prev_equity = equity

        # Entry: no position, bullish signal
        if position_qty == 0 and score >= config.entry_score:
            invest = capital * (config.position_pct / 100)
            if invest > price * 0.0001:
                position_qty = invest / price
                capital -= invest
                entry_price = price
                logger.debug(f"BT BUY  [{i}] price={price:.2f} score={score:.2f} qty={position_qty:.6f}")

        # Exit: holding, bearish signal
        elif position_qty > 0 and score <= config.exit_score:
            proceeds = position_qty * price
            pnl_usdt = proceeds - position_qty * entry_price
            pnl_pct = (price - entry_price) / entry_price * 100
            capital += proceeds
            trades.append(BacktestTrade(
                index=int(i),
                side="Sell",
                price=round(price, 4),
                qty=round(position_qty, 6),
                pnl_usdt=round(pnl_usdt, 4),
                pnl_pct=round(pnl_pct, 4),
                score=score,
            ))
            logger.debug(f"BT SELL [{i}] price={price:.2f} score={score:.2f} pnl={pnl_usdt:+.2f}")
            position_qty = 0.0

    # Close any remaining position at last price
    if position_qty > 0:
        last_price = float(df["close"].iloc[-1])
        proceeds = position_qty * last_price
        pnl_usdt = proceeds - position_qty * entry_price
        pnl_pct = (last_price - entry_price) / entry_price * 100
        capital += proceeds
        trades.append(BacktestTrade(
            index=int(len(df) - 1),
            side="Sell",
            price=round(last_price, 4),
            qty=round(position_qty, 6),
            pnl_usdt=round(pnl_usdt, 4),
            pnl_pct=round(pnl_pct, 4),
            score=0.0,
        ))

    final_capital = round(capital, 4)
    total_return = round((final_capital - config.initial_capital) / config.initial_capital * 100, 4)
    winning = [t for t in trades if t.pnl_usdt > 0]
    losing = [t for t in trades if t.pnl_usdt <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 2) if trades else 0.0

    sharpe = None
    if len(returns) > 1:
        arr = np.array(returns)
        std = float(arr.std())
        if std > 0:
            annualization = (24 * 365 / hours_per_candle) ** 0.5
            sharpe = round(float(arr.mean()) / std * annualization, 4)

    logger.info(
        f"Backtest [{config.symbol}] {config.days}d | "
        f"return={total_return:+.2f}% MDD={max_drawdown:.2f}% "
        f"trades={len(trades)} win={win_rate:.1f}%"
    )

    return BacktestResult(
        symbol=config.symbol,
        days=config.days,
        initial_capital=config.initial_capital,
        final_capital=final_capital,
        total_return_pct=total_return,
        max_drawdown_pct=round(max_drawdown, 4),
        win_rate=win_rate,
        sharpe_ratio=sharpe,
        total_trades=len(trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        candles_analyzed=len(df),
        trades=trades,
    )
