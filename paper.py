"""Paper trading: record pretend trades and auto-close them when stop-loss / target is hit.

Trades are stored in data/paper_trades.csv on your computer.
"""
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PATH = Path(__file__).parent / "data" / "paper_trades.csv"
MAX_HOLD_DAYS = 20   # swing trades still open after 20 trading days are closed at that day's close

COLUMNS = ["id", "symbol", "name", "added_at", "entry_date", "entry", "qty", "stop_loss", "target",
           "score", "why", "status", "exit_date", "exit_price", "exit_reason"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(PATH, dtype={"id": str, "entry_date": str, "exit_date": str})
    df = df.reindex(columns=COLUMNS)
    text_cols = ["symbol", "name", "added_at", "status", "exit_date", "exit_reason", "why"]
    df[text_cols] = df[text_cols].astype(object)
    df["exit_price"] = pd.to_numeric(df.exit_price, errors="coerce")
    return df


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(exist_ok=True)
    df.to_csv(PATH, index=False)


def add_trade(symbol: str, qty: int, entry: float, stop_loss: float, target: float,
              entry_date: date, name: str = "", score: float | None = None, why: str = "") -> None:
    df = load()
    row = {"id": uuid.uuid4().hex[:8], "symbol": symbol.upper(), "name": name or symbol.upper(),
           "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "entry_date": entry_date.isoformat(),
           "entry": round(entry, 2), "qty": int(qty), "stop_loss": round(stop_loss, 2),
           "target": round(target, 2), "score": score, "why": why, "status": "OPEN"}
    save(pd.concat([df, pd.DataFrame([row])], ignore_index=True))


def close_trade(trade_id: str, price: float, reason: str = "Closed manually") -> None:
    df = load()
    i = df.index[df.id == trade_id]
    df.loc[i, ["status", "exit_date", "exit_price", "exit_reason"]] = \
        ["CLOSED", date.today().isoformat(), round(price, 2), reason]
    save(df)


def delete_trade(trade_id: str) -> None:
    df = load()
    save(df[df.id != trade_id])


def evaluate(df: pd.DataFrame, history: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, bool]:
    """Walk each open trade day by day after its entry date and close it if stop/target was hit.

    If a day touches both stop and target we assume the stop came first (the cautious choice).
    If the price gaps past a level at the open, we exit at the open price (what really happens).
    Adds helper columns: ltp (last price) and days_held.
    """
    df = df.copy()
    df["ltp"] = pd.NA
    df["days_held"] = pd.NA
    changed = False
    for i, t in df.iterrows():
        h = history.get(t.symbol)
        if h is None or h.empty:
            continue
        df.at[i, "ltp"] = float(h.Close.iloc[-1])
        after = h[h.index.date > date.fromisoformat(str(t.entry_date))]
        if t.status != "OPEN":
            continue
        df.at[i, "days_held"] = len(after)
        for n, (day, c) in enumerate(after.iterrows(), 1):
            exit_ = None
            if c.Low <= t.stop_loss:
                exit_ = (min(c.Open, t.stop_loss), "Stop-loss hit")
            elif c.High >= t.target:
                exit_ = (max(c.Open, t.target), "Target hit")
            elif n >= MAX_HOLD_DAYS:
                exit_ = (c.Close, f"Time exit ({MAX_HOLD_DAYS} days)")
            if exit_:
                df.loc[i, ["status", "exit_date", "exit_price", "exit_reason", "days_held"]] = \
                    ["CLOSED", day.date().isoformat(), round(float(exit_[0]), 2), exit_[1], n]
                changed = True
                break
    if changed:
        save(df[COLUMNS])
    return df, changed


def with_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """Add P&L columns. Open trades use the last price, closed trades use the exit price."""
    df = df.copy()
    price = pd.to_numeric(df.exit_price.where(df.status == "CLOSED", df.ltp), errors="coerce")
    df["pnl"] = ((price - df.entry) * df.qty).round(0)
    df["pnl_pct"] = ((price / df.entry - 1) * 100).round(2)
    df["r_multiple"] = ((price - df.entry) / (df.entry - df.stop_loss)).round(2)
    df["invested"] = (df.entry * df.qty).round(0)
    return df
