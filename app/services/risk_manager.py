import os
from datetime import date
from loguru import logger

_MAX_CONSECUTIVE = int(os.getenv("MAX_CONSECUTIVE_LOSSES", 5))
_MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", 3.0))

_state: dict = {
    "consecutive_losses": 0,
    "daily_loss_usdt": 0.0,
    "trading_halted": False,
    "halted_reason": "",
    "last_reset_date": date.today().isoformat(),
}


def _auto_reset_daily() -> None:
    today = date.today().isoformat()
    if _state["last_reset_date"] != today:
        _state["daily_loss_usdt"] = 0.0
        _state["last_reset_date"] = today
        logger.info("Daily loss counter reset (new day)")


def is_trading_halted() -> tuple[bool, str]:
    _auto_reset_daily()
    return _state["trading_halted"], _state["halted_reason"]


def record_trade_result(success: bool, pnl_usdt: float = 0.0, equity: float = 1000.0) -> None:
    _auto_reset_daily()

    is_loss = not success or pnl_usdt < 0

    if is_loss:
        _state["consecutive_losses"] += 1
        if pnl_usdt < 0:
            _state["daily_loss_usdt"] += abs(pnl_usdt)
        logger.warning(f"Loss recorded — consecutive={_state['consecutive_losses']}, daily_loss={_state['daily_loss_usdt']:.2f} USDT")

        if _state["consecutive_losses"] >= _MAX_CONSECUTIVE:
            _halt(f"연속 손실 {_state['consecutive_losses']}회 한도 초과")
            return

        if equity > 0:
            daily_pct = _state["daily_loss_usdt"] / equity * 100
            if daily_pct >= _MAX_DAILY_LOSS_PCT:
                _halt(f"일일 손실 한도 초과: -{daily_pct:.1f}% (한도 {_MAX_DAILY_LOSS_PCT}%)")
    else:
        if _state["consecutive_losses"] > 0:
            logger.info(f"Trade success — consecutive loss streak reset (was {_state['consecutive_losses']})")
        _state["consecutive_losses"] = 0


def _halt(reason: str) -> None:
    _state["trading_halted"] = True
    _state["halted_reason"] = reason
    logger.error(f"[RISK] Trading HALTED: {reason}")


def reset_risk_state(reason: str = "수동 리셋") -> None:
    _state["consecutive_losses"] = 0
    _state["daily_loss_usdt"] = 0.0
    _state["trading_halted"] = False
    _state["halted_reason"] = ""
    _state["last_reset_date"] = date.today().isoformat()
    logger.info(f"Risk state reset: {reason}")


def get_risk_status() -> dict:
    _auto_reset_daily()
    return {
        "consecutive_losses": _state["consecutive_losses"],
        "max_consecutive_losses": _MAX_CONSECUTIVE,
        "daily_loss_usdt": round(_state["daily_loss_usdt"], 4),
        "max_daily_loss_pct": _MAX_DAILY_LOSS_PCT,
        "trading_halted": _state["trading_halted"],
        "halted_reason": _state["halted_reason"],
        "last_reset_date": _state["last_reset_date"],
    }
