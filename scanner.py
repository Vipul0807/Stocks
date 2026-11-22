"""Two-stage swing scanner.

Stage 1: chart checks on every stock in the universe (one bulk price download - fast).
Stage 2: news sentiment only for the top N chart setups (keeps Google News happy).

Run from terminal:  python scanner.py "Nifty 200"
"""
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

import config
from news import fetch_headlines, news_score
from technicals import get_history, indicators, technical_score
from universe import load_universe

NEWS_WEIGHT = 3.0      # news sentiment (-1..+1) is multiplied by this
MIN_TURNOVER_CR = 5.0  # skip stocks trading less than ₹5 crore a day (hard to buy/sell)


def trade_plan(close: float, atr: float, capital: float, risk_pct: float) -> dict:
    stop = close - config.ATR_STOP_MULT * atr
    risk_per_share = close - stop
    target = close + config.REWARD_RISK * risk_per_share
    qty = int(min(capital * risk_pct / 100 / risk_per_share, capital / close))
    return {"entry": round(close, 2), "stop_loss": round(stop, 2), "target": round(target, 2),
            "qty": qty, "risk_rs": round(qty * risk_per_share), "reward_rs": round(qty * (target - close))}


def scan(universe: str = "Nifty 200", news_top_n: int = 30, progress=None) -> dict:
    report = progress or (lambda frac, text: print(text))
    stocks = load_universe(universe)

    # ---- Stage 1: charts for everyone ----
    report(0.05, f"Downloading prices for {len(stocks)} stocks…")
    history = get_history(stocks.symbol.tolist())

    rows = []
    for s in stocks.itertuples():
        if s.symbol not in history:
            continue
        ind = indicators(history[s.symbol])
        if ind["turnover_cr"] < MIN_TURNOVER_CR:
            continue
        t_score, reasons = technical_score(ind)
        rows.append({"symbol": s.symbol, "name": s.name, "sector": s.sector,
                     "tech_score": t_score, "reasons": reasons, **ind})
    df = pd.DataFrame(rows)
    df = df.sort_values(["tech_score", "vol_ratio"], ascending=False).reset_index(drop=True)

    # ---- Stage 2: news only for the best chart setups ----
    shortlist = df[df.tech_score > 0].head(news_top_n)
    news: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_headlines, r.name): r.symbol for r in shortlist.itertuples()}
        for i, fut in enumerate(as_completed(futures), 1):
            sym = futures[fut]
            try:
                news[sym] = fut.result()
            except Exception:
                news[sym] = []
            report(0.4 + 0.6 * i / max(len(futures), 1), f"Reading news {i}/{len(futures)}: {sym}")

    df["news_checked"] = df.symbol.isin(news.keys())
    df["news_sentiment"] = df.symbol.map(lambda s: news_score(news[s]) if s in news else np.nan)
    df["headlines"] = df.symbol.map(lambda s: len(news.get(s, [])))
    df["score"] = (df.tech_score + NEWS_WEIGHT * df.news_sentiment.fillna(0)).round(2)

    def add_news_reason(r):
        rs = list(r.reasons)
        if r.news_checked:
            if r.news_sentiment >= 0.2:
                rs.append(("Positive news", True))
            elif r.news_sentiment <= -0.2:
                rs.append(("Negative news", False))
        return rs
    df["reasons"] = df.apply(add_news_reason, axis=1)
    df["why"] = df.reasons.map(lambda rs: ", ".join(t for t, _ in rs))

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return {"df": df, "news": news, "history": history, "universe": universe,
            "total": len(stocks)}


if __name__ == "__main__":
    universe = sys.argv[1] if len(sys.argv) > 1 else "Nifty 200"
    res = scan(universe)
    df = res["df"]
    pd.set_option("display.width", 250)
    print(f"\n{universe}: {len(df)} liquid stocks scanned, news checked for {df.news_checked.sum()}\n")
    plans = pd.DataFrame([trade_plan(r.close, r.atr, config.CAPITAL, config.RISK_PER_TRADE_PCT)
                          for r in df.head(10).itertuples()])
    print(pd.concat([df.head(10)[["symbol", "score", "tech_score", "news_sentiment", "rsi"]], plans], axis=1)
          .to_string(index=False))
    print()
    for r in df.head(5).itertuples():
        print(f"{r.symbol}: {r.why}")
        for h in res["news"].get(r.symbol, [])[:3]:
            print(f"    [{h['sentiment']:+.2f}] {h['title']}")
