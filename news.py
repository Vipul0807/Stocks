"""Fetch recent headlines from Google News RSS and score their sentiment."""
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config

_analyzer = SentimentIntensityAnalyzer()

# VADER is a general-purpose model; teach it common market words.
_analyzer.lexicon.update({
    "upgrade": 2.5, "upgrades": 2.5, "upgraded": 2.5, "outperform": 2.0,
    "beats": 2.0, "beat": 1.5, "surge": 2.0, "surges": 2.0, "rally": 2.0, "rallies": 2.0,
    "jumps": 1.8, "soars": 2.5, "record": 1.2, "bullish": 2.5, "buy": 1.5,
    "order": 1.0, "orders": 1.0, "wins": 1.8, "bags": 1.8, "expansion": 1.5,
    "profit": 1.2, "dividend": 1.2, "buyback": 2.0, "approval": 1.5,
    "downgrade": -2.5, "downgrades": -2.5, "downgraded": -2.5, "underperform": -2.0,
    "misses": -2.0, "miss": -1.5, "plunge": -2.5, "plunges": -2.5, "slumps": -2.2,
    "crash": -3.0, "falls": -1.5, "tumbles": -2.2, "bearish": -2.5, "sell": -1.5,
    "loss": -1.8, "probe": -2.0, "raid": -2.2, "penalty": -2.0, "fraud": -3.0,
    "sebi": -0.3, "lawsuit": -2.0, "default": -2.5, "resigns": -1.5, "cut": -1.2,
    # neutral in a market context (VADER treats these as positive)
    "share": 0.0, "shares": 0.0, "live": 0.0, "interest": 0.0, "top": 0.0,
})

# Price-ticker pages, not real news.
_BOILERPLATE = re.compile(r"share price( today| live)?$|stock price|live nse|live updates|price chart|"
                          r"share price today", re.I)


def fetch_headlines(search_name: str) -> list[dict]:
    query = urllib.parse.quote(f'"{search_name}" share OR stock')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.NEWS_LOOKBACK_DAYS)

    items = []
    for e in feed.entries:
        if not getattr(e, "published_parsed", None):
            continue
        published = datetime.fromtimestamp(time.mktime(e.published_parsed), tz=timezone.utc)
        if published < cutoff:
            continue
        title = e.title.rsplit(" - ", 1)[0]  # strip " - Publisher"
        if _BOILERPLATE.search(title):
            continue
        score = _analyzer.polarity_scores(title)["compound"]
        items.append({"title": title, "link": e.link, "published": published, "sentiment": score,
                      "source": e.title.rsplit(" - ", 1)[-1]})
        if len(items) >= config.MAX_HEADLINES_PER_STOCK:
            break
    return items


def news_score(headlines: list[dict]) -> float:
    """Average sentiment (-1..+1), newer headlines weighted more."""
    if not headlines:
        return 0.0
    now = datetime.now(timezone.utc)
    total = weight_sum = 0.0
    for h in headlines:
        age_days = (now - h["published"]).total_seconds() / 86400
        w = 1.0 / (1.0 + age_days)
        total += h["sentiment"] * w
        weight_sum += w
    return total / weight_sum
