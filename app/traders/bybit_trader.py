import os
from loguru import logger
from models.schemas import TradeSignal, TradeResult
from utils.mock import is_mock, mock_order_id, mock_wallet_equity, mock_market_data, log_mock
from services.risk_manager import is_trading_halted, record_trade_result


def _get_client():
    from pybit.unified_trading import HTTP
    return HTTP(
        testnet=os.getenv("BYBIT_TESTNET", "true").lower() == "true",
        api_key=os.getenv("BYBIT_API_KEY", ""),
        api_secret=os.getenv("BYBIT_API_SECRET", ""),
    )


def _get_equity_and_price(symbol: str) -> tuple[float, float]:
    """Return (wallet_equity_usdt, current_price)."""
    if is_mock():
        md = mock_market_data(symbol)
        price = md.price if md else 63500.0
        return mock_wallet_equity(), price

    try:
        client = _get_client()
        wallet = client.get_wallet_balance(accountType="UNIFIED")
        equity = float(wallet["result"]["list"][0]["totalEquity"]) if wallet["retCode"] == 0 else 1000.0

        ticker = client.get_tickers(category="spot", symbol=symbol)
        price = float(ticker["result"]["list"][0]["lastPrice"]) if ticker["retCode"] == 0 else 0.0
        return equity, price
    except Exception as e:
        logger.warning(f"Failed to fetch equity/price: {e}")
        return 1000.0, 0.0


def calculate_dynamic_qty(symbol: str, score: float) -> float:
    """
    Position size = (equity × MAX_POSITION_PCT%) × score_factor / price
    score_factor scales from 1.0 at the auto-trade threshold (20) to 1.5 at score ≥ 30.
    """
    max_position_pct = float(os.getenv("MAX_POSITION_PCT", 10.0))
    auto_trade_min = float(os.getenv("SCORE_AUTO_TRADE_MIN", 20.0))

    equity, price = _get_equity_and_price(symbol)
    if price <= 0:
        logger.warning(f"Cannot calculate qty: price={price}")
        return 0.0

    base_invest = equity * (max_position_pct / 100.0)
    score_factor = min(abs(score) / auto_trade_min, 1.5)
    invest_usdt = base_invest * score_factor
    qty = invest_usdt / price

    return round(qty, 6)


def _check_position_limit(signal: TradeSignal) -> tuple[bool, str]:
    max_position_pct = float(os.getenv("MAX_POSITION_PCT", 10.0))
    equity, price = _get_equity_and_price(signal.symbol)
    if price <= 0:
        return False, "가격 조회 실패"

    max_invest = equity * (max_position_pct / 100.0)
    order_value = signal.qty * price

    if order_value > max_invest * 1.6:  # allow up to 1.5× score factor + buffer
        return False, f"포지션 한도 초과: {order_value:.2f} USDT > {max_invest:.2f} USDT"
    return True, "OK"


async def execute_trade(signal: TradeSignal) -> TradeResult:
    # Risk halt check
    halted, halt_reason = is_trading_halted()
    if halted:
        msg = f"거래 중단 상태: {halt_reason}"
        logger.warning(f"Trade blocked — {msg}")
        return TradeResult(success=False, message=msg, signal=signal)

    ok, reason = _check_position_limit(signal)
    if not ok:
        logger.warning(f"Trade blocked by position limit: {reason}")
        record_trade_result(success=False)
        return TradeResult(success=False, message=reason, signal=signal)

    if is_mock():
        order_id = mock_order_id()
        log_mock(f"order: {signal.side} {signal.qty} {signal.symbol} | id={order_id}")
        record_trade_result(success=True)
        return TradeResult(
            success=True,
            order_id=order_id,
            message=f"[MOCK] {signal.side} 주문 완료: {signal.qty} {signal.symbol}",
            signal=signal,
        )

    try:
        client = _get_client()
        resp = client.place_order(
            category="spot",
            symbol=signal.symbol,
            side=signal.side,
            orderType="Market",
            qty=str(signal.qty),
        )

        if resp["retCode"] != 0:
            msg = f"주문 실패: {resp['retMsg']}"
            logger.error(msg)
            record_trade_result(success=False)
            return TradeResult(success=False, message=msg, signal=signal)

        order_id = resp["result"]["orderId"]
        logger.info(f"Order placed: {signal.side} {signal.qty} {signal.symbol} | orderId={order_id}")
        record_trade_result(success=True)
        return TradeResult(
            success=True,
            order_id=order_id,
            message=f"{signal.side} 주문 완료: {signal.qty} {signal.symbol}",
            signal=signal,
        )

    except Exception as e:
        msg = f"거래 실행 예외: {e}"
        logger.exception(msg)
        record_trade_result(success=False)
        return TradeResult(success=False, message=msg, signal=signal)


def build_trade_signal(symbol: str, score: float, qty: float, reason: str) -> TradeSignal:
    side = "Buy" if score > 0 else "Sell"
    return TradeSignal(symbol=symbol, side=side, qty=qty, score=score, reason=reason)
