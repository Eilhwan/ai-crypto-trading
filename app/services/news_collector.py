import asyncio
import os
from datetime import datetime, timedelta, timezone
from loguru import logger

from models.schemas import NewsItem
from database.db import AsyncSessionLocal, SeenUrl
from sqlalchemy import select, delete
from utils.mock import is_mock

RSS_FEEDS = [
    "https://feeds.feedburner.com/CoinDesk",
    "https://cointelegraph.com/rss",
    "https://cryptonews.com/news/feed/",
    "https://www.newsbtc.com/feed/",
    "https://decrypt.co/feed",
]

_MOCK_NEWS = [
    NewsItem(title="Bitcoin ETF sees record inflows as institutional demand surges", content="Major financial institutions reported record Bitcoin ETF purchases, signaling strong bull momentum.", source="https://mock.coindesk.com/1"),
    NewsItem(title="Federal Reserve signals potential rate cuts boosting crypto markets", content="Fed officials hinted at possible rate reductions which historically correlate with crypto bull runs.", source="https://mock.cointelegraph.com/2"),
    NewsItem(title="Ethereum developers confirm major network upgrade timeline", content="The upcoming upgrade promises significant improvements in transaction throughput and fee reduction.", source="https://mock.cryptonews.com/3"),
    NewsItem(title="Crypto exchange hack leads to temporary market sell-off", content="A mid-sized exchange reported security breach causing temporary panic selling across major pairs.", source="https://mock.newsbtc.com/4"),
    NewsItem(title="Bitcoin miners report record revenues as hash rate hits all-time high", content="Mining profitability surged as network difficulty adjusted to new all-time high hash rate levels.", source="https://mock.decrypt.co/5"),
]


def _parse_entry_date(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        import time
        return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None


def _fetch_feed_sync(url: str) -> list[dict]:
    import feedparser
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries:
            items.append({
                "title": entry.get("title", "").strip(),
                "content": entry.get("summary", entry.get("description", ""))[:600].strip(),
                "source": entry.get("link", ""),
                "published": _parse_entry_date(entry),
            })
        return items
    except Exception as e:
        logger.warning(f"Feed fetch failed [{url}]: {e}")
        return []


async def _get_seen_urls() -> set[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SeenUrl.url))
        return {row[0] for row in result.fetchall()}


async def _mark_seen(urls: list[str]) -> None:
    if not urls:
        return
    async with AsyncSessionLocal() as db:
        for url in urls:
            db.add(SeenUrl(url=url))
        try:
            await db.commit()
        except Exception:
            await db.rollback()


async def cleanup_seen_urls(max_age_hours: int = 24) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(SeenUrl).where(SeenUrl.created_at < cutoff)
        )
        await db.commit()
        return result.rowcount


async def collect_news(hours: int | None = None) -> list[NewsItem]:
    if hours is None:
        hours = int(os.getenv("NEWS_LOOKBACK_HOURS", 2))

    if is_mock():
        logger.debug("[MOCK] returning mock news items")
        seen = await _get_seen_urls()
        new_items = [n for n in _MOCK_NEWS if n.source not in seen]
        await _mark_seen([n.source for n in new_items])
        return new_items

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    loop = asyncio.get_event_loop()

    raw_lists = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_feed_sync, url) for url in RSS_FEEDS],
        return_exceptions=True,
    )

    candidates: list[dict] = []
    for result in raw_lists:
        if isinstance(result, Exception):
            continue
        for item in result:
            if not item["title"] or not item["source"]:
                continue
            pub = item["published"]
            if pub and pub < cutoff:
                continue
            candidates.append(item)

    seen = await _get_seen_urls()
    new_items: list[NewsItem] = []
    new_urls: list[str] = []

    for item in candidates:
        if item["source"] not in seen:
            new_items.append(NewsItem(
                title=item["title"],
                content=item["content"],
                source=item["source"],
            ))
            new_urls.append(item["source"])

    await _mark_seen(new_urls)
    logger.info(f"Collected {len(new_items)} new articles (feeds: {len(RSS_FEEDS)}, lookback: {hours}h)")
    return new_items
