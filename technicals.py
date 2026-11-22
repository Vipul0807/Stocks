"""Price data (Yahoo Finance, free) and swing-trading indicators."""
import pandas as pd
import yfinance as yf


def get_history(symbols: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    tickers = [f"{s}.NS" for s in symbols]
    raw = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                      auto_adjust=True, progress=False, threads=True)
    out = {}
    for s, t in zip(symbols, tickers):
        try:
            df = raw[t] if raw.columns.nlevels > 1 else raw
            df = df.dropna()
        except KeyError:
            continue
        if len(df) >= 60:
            out[s] = df
    return out


def add_emas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    return df


def indicators(df: pd.DataFrame) -> dict:
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss)

    prev_close = close.shift()
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()

    last = close.iloc[-1]
    avg_vol = vol.iloc[-21:-1].mean()
    return {
        "close": float(last),
        "ema20": float(ema20.iloc[-1]),
        "ema50": float(ema50.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "atr": float(atr.iloc[-1]),
        "vol_ratio": float(vol.iloc[-1] / avg_vol) if avg_vol else 0.0,
        "chg_5d_pct": float((last / close.iloc[-6] - 1) * 100),
        "from_52w_high_pct": float((last / close.max() - 1) * 100),
        "turnover_cr": float((close * vol).iloc[-20:].mean() / 1e7),  # avg daily traded value, ₹ crore
    }


def technical_score(ind: dict) -> tuple[float, list[tuple[str, bool]]]:
    """Score a swing-long setup (about -4 to +5.5). Returns (score, [(reason, is_good)])."""
    score, why = 0.0, []
    c, e20, e50, rsi = ind["close"], ind["ema20"], ind["ema50"], ind["rsi"]

    if c > e20 > e50:
        score += 2; why.append(("Uptrend", True))
    elif c < e20 < e50:
        score -= 2; why.append(("Downtrend", False))

    if c > e50 and abs(c / e20 - 1) <= 0.03:
        score += 1; why.append(("Near EMA20 support", True))

    if 45 <= rsi <= 65:
        score += 1; why.append((f"Healthy RSI {rsi:.0f}", True))
    elif rsi > 75:
        score -= 1; why.append((f"Overbought RSI {rsi:.0f}", False))
    elif rsi < 30:
        score -= 1; why.append((f"Weak RSI {rsi:.0f}", False))

    if ind["vol_ratio"] >= 1.5 and ind["chg_5d_pct"] > 0:
        score += 1; why.append((f"Volume {ind['vol_ratio']:.1f}x", True))

    if ind["from_52w_high_pct"] > -5:
        score += 0.5; why.append(("Near 52W high", True))

    return score, why


def market_mood() -> dict | None:
    """Nifty 50 trend: swing longs work far better when the overall market is rising."""
    try:
        df = yf.Ticker("^NSEI").history(period="6mo")
        if len(df) < 60:
            return None
        df = add_emas(df)
        c, e20, e50 = df["Close"].iloc[-1], df["EMA20"].iloc[-1], df["EMA50"].iloc[-1]
        trend = "Uptrend" if c > e20 > e50 else "Downtrend" if c < e20 < e50 else "Sideways"
        return {"close": float(c), "chg_5d_pct": float((c / df["Close"].iloc[-6] - 1) * 100), "trend": trend,
                "spark": df["Close"].tail(30).round(0).tolist()}
    except Exception:
        return None
