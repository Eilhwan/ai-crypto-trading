import os
from datetime import datetime, timezone
from loguru import logger
import httpx

from models.schemas import FearGreedResponse
from utils.mock import is_mock, _MOCK_SCENARIO

FEAR_GREED_URL = "https://api.alternative.me/fng/"
_CACHE_TTL = 300  # seconds

_cache: dict = {"value": None, "classification": None, "fetched_at": None}

_CLASSIFICATION_MAP = {
    (0, 25): "Extreme Fear",
    (25, 45): "Fear",
    (45, 55): "Neutral",
    (55, 75): "Greed",
    (75, 101): "Extreme Greed",
}

_MOCK_VALUES = {"bullish": 72.0, "bearish": 28.0, "default": 50.0}


def _classify(value: float) -> str:
    for (lo, hi), label in _CLASSIFICATION_MAP.items():
        if lo <= value < hi:
            return label
    return "Neutral"


async def _fetch_live() -> tuple[float, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(FEAR_GREED_URL, params={"limit": 1})
        resp.raise_for_status()
        entry = resp.json()["data"][0]
        value = float(entry["value"])
        classification = entry.get("value_classification", _classify(value))
        return value, classification


async def get_fear_greed() -> float:
    return (await get_fear_greed_response()).value


async def get_fear_greed_response() -> FearGreedResponse:
    if is_mock():
        value = _MOCK_VALUES.get(_MOCK_SCENARIO, 50.0)
        logger.debug(f"[MOCK] fear_greed={value} (scenario={_MOCK_SCENARIO})")
        return FearGreedResponse(
            value=value,
            classification=_classify(value),
            cached=False,
        )

    now = datetime.now(timezone.utc)

    if _cache["value"] is not None:
        age = (now - _cache["fetched_at"]).total_seconds()
        if age < _CACHE_TTL:
            return FearGreedResponse(
                value=_cache["value"],
                classification=_cache["classification"],
                cached=True,
                fetched_at=_cache["fetched_at"].isoformat(),
            )

    try:
        value, classification = await _fetch_live()
        _cache["value"] = value
        _cache["classification"] = classification
        _cache["fetched_at"] = now
        logger.info(f"Fear & Greed: {value} ({classification})")
        return FearGreedResponse(
            value=value,
            classification=classification,
            cached=False,
            fetched_at=now.isoformat(),
        )
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")
        fallback = _cache["value"] if _cache["value"] is not None else 50.0
        return FearGreedResponse(
            value=fallback,
            classification=_classify(fallback),
            cached=_cache["value"] is not None,
            fetched_at=_cache["fetched_at"].isoformat() if _cache["fetched_at"] else None,
        )
