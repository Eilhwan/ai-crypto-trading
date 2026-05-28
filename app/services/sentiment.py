from loguru import logger
from models.schemas import NewsItem, SentimentResult
from utils.mock import is_mock, mock_sentiment, log_mock
import asyncio
from functools import lru_cache

MODEL_NAME = "ProsusAI/finbert"


@lru_cache(maxsize=1)
def _load_pipeline():
    from transformers import pipeline  # lazy: only imported when not in mock mode
    logger.info(f"Loading sentiment model: {MODEL_NAME}")
    return pipeline("text-classification", model=MODEL_NAME, top_k=None)


def _run_inference(texts: list[str]) -> list[dict]:
    nlp = _load_pipeline()
    results = []
    for text in texts:
        truncated = text[:512]
        output = nlp(truncated)
        results.append(output)
    return results


def _mock_inference(news_items: list[NewsItem]) -> list[SentimentResult]:
    results = []
    for item in news_items:
        raw = mock_sentiment(item.title, item.content or "")
        label = raw["label"]
        confidence = raw["score"]
        normalized = confidence if label == "positive" else (-confidence if label == "negative" else 0.0)
        results.append(SentimentResult(
            title=item.title,
            sentiment=label,
            score=round(normalized, 4),
            confidence=round(confidence, 4),
        ))
    return results


async def analyze_sentiment(news_items: list[NewsItem]) -> list[SentimentResult]:
    if not news_items:
        return []

    if is_mock():
        log_mock("sentiment analysis")
        return _mock_inference(news_items)

    texts = [f"{item.title}. {item.content}"[:512] for item in news_items]

    loop = asyncio.get_event_loop()
    raw_results = await loop.run_in_executor(None, _run_inference, texts)

    sentiment_results = []
    for item, raw in zip(news_items, raw_results):
        label_scores = {r["label"].lower(): r["score"] for r in raw}

        best_label = max(label_scores, key=label_scores.get)
        best_score = label_scores[best_label]

        if best_label == "positive":
            normalized = best_score
        elif best_label == "negative":
            normalized = -best_score
        else:
            normalized = 0.0

        sentiment_results.append(SentimentResult(
            title=item.title,
            sentiment=best_label,
            score=round(normalized, 4),
            confidence=round(best_score, 4),
        ))

    return sentiment_results


def calculate_news_score(sentiments: list[SentimentResult]) -> float:
    if not sentiments:
        return 0.0

    total = sum(s.score * s.confidence for s in sentiments)
    avg = total / len(sentiments)

    # Map [-1, 1] → [-7, +7] score range
    return round(avg * 7, 2)
