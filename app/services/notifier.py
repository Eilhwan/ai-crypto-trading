import os
import httpx
from loguru import logger
from models.schemas import AnalyzeResponse, TradeResult


OPENCLAW_URL = os.getenv("OPENCLAW_URL", "")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


def _build_analysis_text(response: AnalyzeResponse) -> str:
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


async def _send_openclaw(text: str) -> None:
    if not (OPENCLAW_URL and OPENCLAW_TOKEN):
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{OPENCLAW_URL}/api/message",
                json={"message": text},
                headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                logger.warning(f"OpenClaw notification failed: {resp.status_code}")
            else:
                logger.info("OpenClaw notification sent.")
    except Exception as e:
        logger.warning(f"OpenClaw unreachable: {e}")


async def _send_telegram(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    # Strip markdown bold markers for Telegram compatibility
    clean = text.replace("**", "*")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": clean,
                "parse_mode": "Markdown",
            })
            if resp.status_code >= 400:
                logger.warning(f"Telegram notification failed: {resp.status_code} {resp.text[:100]}")
            else:
                logger.info("Telegram notification sent.")
    except Exception as e:
        logger.warning(f"Telegram unreachable: {e}")


async def _send_discord(text: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DISCORD_WEBHOOK_URL, json={
                "content": text,
                "username": "AI Crypto Trading",
            })
            if resp.status_code >= 400:
                logger.warning(f"Discord notification failed: {resp.status_code}")
            else:
                logger.info("Discord notification sent.")
    except Exception as e:
        logger.warning(f"Discord unreachable: {e}")


async def notify_analysis(response: AnalyzeResponse) -> None:
    text = _build_analysis_text(response)
    await _send_openclaw(text)
    await _send_telegram(text)
    await _send_discord(text)


async def notify_trade(result: TradeResult) -> None:
    text = _build_trade_text(result)
    if not text:
        return
    await _send_openclaw(text)
    await _send_telegram(text)
    await _send_discord(text)
