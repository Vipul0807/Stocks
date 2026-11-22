"""Which stocks to scan: official NSE index lists (auto-downloaded) or your own watchlist."""
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

import config

UNIVERSES = ["Nifty 50", "Nifty 100", "Nifty 200", "Nifty 500", "My watchlist"]
DATA_DIR = Path(__file__).parent / "data"
REFRESH_DAYS = 7


def _watchlist() -> pd.DataFrame:
    return pd.DataFrame([{"symbol": s, "name": n, "sector": "-"} for s, n in config.WATCHLIST.items()])


def load_universe(name: str) -> pd.DataFrame:
    """Return a DataFrame with columns: symbol, name, sector."""
    if name == "My watchlist":
        return _watchlist()

    slug = name.lower().replace(" ", "")              # "Nifty 200" -> "nifty200"
    path = DATA_DIR / f"{slug}.csv"
    stale = not path.exists() or (time.time() - path.stat().st_mtime) > REFRESH_DAYS * 86400
    if stale:
        try:
            url = f"https://nsearchives.nseindia.com/content/indices/ind_{slug}list.csv"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=20).read()
            DATA_DIR.mkdir(exist_ok=True)
            path.write_bytes(data)
        except Exception as e:
            print(f"Could not download {name} list ({e}); using cached copy or watchlist.")
    if not path.exists():
        return _watchlist()

    df = pd.read_csv(path).rename(columns={"Symbol": "symbol", "Company Name": "name", "Industry": "sector"})
    df["name"] = df["name"].str.replace(r"\s+(Ltd\.?|Limited)$", "", regex=True, flags=re.I).str.strip()
    # use friendlier news-search names where we have them
    df["name"] = df.apply(lambda r: config.WATCHLIST.get(r.symbol, r["name"]), axis=1)
    return df[["symbol", "name", "sector"]]
