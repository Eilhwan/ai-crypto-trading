import os
import httpx
from loguru import logger
from models.schemas import AnalyzeResponse, TradeResult


OPENCLAW_URL = os.getenv("OPENCLAW_URL", "")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")


def _openclaw_enabled() -> bool:
    return bool(OPENCLAW_URL and OPENCLAW_TOKEN)


def _build_notify_text(response: AnalyzeResponse) -> str:
    emoji = "📈" if response.score > 0 else "📉"
    action_label = {
        "notify": "⚠️ 승인 요청",
        "auto_trade": "🤖 자동 거래 실행",
    }.get(response.action.value, "")

    lines = [
        f"{emoji} **AI Trading Alert** {action_label}",
        f"심볼: {response.symbol}",
        f"점수: {response.score:+.1f}",
        "",
        "**지표 내역**",
        f"- 뉴스 감성: {response.breakdown.news_score:+.1f}",
        f"- RSI: {response.breakdown.rsi_score:+.1f}",
        f"- MACD: {response.breakdown.macd_score:+.1f}",
        f"- 거래량: {response.breakdown.volume_score:+.1f}",
        f"- 공포/탐욕: {response.breakdown.fear_greed_score:+.1f}",
        "",
        "**뉴스 감성**",
    ]
    for s in response.sentiments[:3]:
        icon = "🟢" if s.sentiment == "positive" else ("🔴" if s.sentiment == "negative" else "⚪")
        lines.append(f"{icon} {s.title[:60]} ({s.confidence:.0%})")

    return "\n".join(lines)


def _build_trade_text(result: TradeResult) -> str:
    if not result.signal:
        return ""
    side_emoji = "🟢" if result.signal.side == "Buy" else "🔴"
    status = "✅ 성공" if result.success else "❌ 실패"
    return (
        f"{side_emoji} **자동 거래 결과** {status}\n"
        f"심볼: {result.signal.symbol}\n"
        f"방향: {result.signal.side}  수량: {result.signal.qty}\n"
        f"주문 ID: {result.order_id or '-'}\n"
        f"메시지: {result.message}"
    )


async def _post_to_openclaw(text: str) -> None:
    headers = {
        "Authorization": f"Bearer {OPENCLAW_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"message": text}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{OPENCLAW_URL}/api/message",
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 400:
                logger.warning(f"OpenClaw notification failed: {resp.status_code} {resp.text[:100]}")
            else:
                logger.info("OpenClaw notification sent.")
    except Exception as e:
        logger.warning(f"OpenClaw unreachable: {e}")


async def notify_analysis(response: AnalyzeResponse) -> None:
    if not _openclaw_enabled():
        logger.debug("OpenClaw not configured, skipping notification.")
        return
    text = _build_notify_text(response)
    await _post_to_openclaw(text)


async def notify_trade(result: TradeResult) -> None:
    if not _openclaw_enabled():
        return
    text = _build_trade_text(result)
    if text:
        await _post_to_openclaw(text)
