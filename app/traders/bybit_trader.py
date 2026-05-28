from loguru import logger
from models.schemas import TradeSignal, TradeResult
from utils.mock import is_mock, mock_order_id, mock_wallet_equity, log_mock
import os


def _get_client():
    from pybit.unified_trading import HTTP  # lazy: only imported when not in mock mode
    return HTTP(
        testnet=os.getenv("BYBIT_TESTNET", "true").lower() == "true",
        api_key=os.getenv("BYBIT_API_KEY", ""),
        api_secret=os.getenv("BYBIT_API_SECRET", ""),
    )


def _check_risk_limits(signal: TradeSignal) -> tuple[bool, str]:
    max_position_pct = float(os.getenv("MAX_POSITION_PCT", 10.0))

    if is_mock():
        equity = mock_wallet_equity()
        max_qty_usdt = equity * (max_position_pct / 100)
        mock_price = 65000.0
        order_value = signal.qty * mock_price
        if order_value > max_qty_usdt:
            return False, f"포지션 한도 초과: {order_value:.2f} USDT > {max_qty_usdt:.2f} USDT"
        return True, "OK"

    try:
        client = _get_client()
        wallet = client.get_wallet_balance(accountType="UNIFIED")
        if wallet["retCode"] != 0:
            return False, f"지갑 조회 실패: {wallet['retMsg']}"

        equity = float(wallet["result"]["list"][0]["totalEquity"])
        max_qty_usdt = equity * (max_position_pct / 100)

        ticker = client.get_tickers(category="spot", symbol=signal.symbol)
        if ticker["retCode"] != 0:
            return False, f"가격 조회 실패: {ticker['retMsg']}"

        price = float(ticker["result"]["list"][0]["lastPrice"])
        order_value = signal.qty * price

        if order_value > max_qty_usdt:
            return False, f"포지션 한도 초과: {order_value:.2f} USDT > {max_qty_usdt:.2f} USDT"

        return True, "OK"

    except Exception as e:
        return False, f"리스크 체크 오류: {e}"


async def execute_trade(signal: TradeSignal) -> TradeResult:
    ok, reason = _check_risk_limits(signal)
    if not ok:
        logger.warning(f"Trade blocked by risk check: {reason}")
        return TradeResult(success=False, message=reason, signal=signal)

    if is_mock():
        order_id = mock_order_id()
        log_mock(f"order placed: {signal.side} {signal.qty} {signal.symbol} | orderId={order_id}")
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
            return TradeResult(success=False, message=msg, signal=signal)

        order_id = resp["result"]["orderId"]
        logger.info(f"Order placed: {signal.side} {signal.qty} {signal.symbol} | orderId={order_id}")
        return TradeResult(
            success=True,
            order_id=order_id,
            message=f"{signal.side} 주문 완료: {signal.qty} {signal.symbol}",
            signal=signal,
        )

    except Exception as e:
        msg = f"거래 실행 예외: {e}"
        logger.exception(msg)
        return TradeResult(success=False, message=msg, signal=signal)


def build_trade_signal(symbol: str, score: float, qty: float, reason: str) -> TradeSignal:
    side = "Buy" if score > 0 else "Sell"
    return TradeSignal(symbol=symbol, side=side, qty=qty, score=score, reason=reason)
