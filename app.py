"""Web dashboard.  Run:  streamlit run app.py"""
from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
import paper
from scanner import scan, trade_plan
from technicals import add_emas, get_history, indicators, market_mood
from universe import UNIVERSES

st.set_page_config(page_title="Swing Scanner", page_icon="📈", layout="wide")

GREEN, RED, MUTED = "#22c55e", "#ef4444", "#94a3b8"
st.markdown(f"""<style>
.block-container {{padding-top: 4rem;}}
[data-testid="stProgress"] p {{font-size:.85rem;color:{MUTED};margin-bottom:.3rem}}
.chip {{display:inline-block;padding:1px 9px;margin:2px 4px 2px 0;border-radius:999px;font-size:.76rem;
        background:rgba(34,197,94,.12);color:{GREEN};border:1px solid rgba(34,197,94,.35)}}
.chip.bad {{background:rgba(239,68,68,.12);color:{RED};border-color:rgba(239,68,68,.35)}}
.sym {{font-size:1.15rem;font-weight:700;margin:0;line-height:1.4;word-break:break-word}}
.sub {{color:{MUTED};font-size:.78rem;line-height:1.35;margin:0 0 .5rem}}
.score {{display:inline-block;font-size:.85rem;font-weight:700;padding:1px 8px;border-radius:6px;
         background:rgba(34,197,94,.15);color:{GREEN};margin-bottom:4px}}
.tiles {{display:flex;flex-wrap:wrap;gap:10px;margin:.4rem 0 1rem}}
.tile {{flex:1 1 140px;border:1px solid rgba(148,163,184,.25);border-radius:10px;padding:10px 14px}}
.tl {{font-size:.78rem;color:{MUTED}}}
.tv {{font-size:1.45rem;font-weight:700;line-height:1.3}}
.ts {{font-size:.78rem}}
.plan {{margin:.7rem 0 .3rem;font-size:.8rem;color:{MUTED};border-top:1px solid rgba(148,163,184,.2);padding-top:.5rem}}
.plan div {{display:flex;justify-content:space-between;align-items:baseline;padding:1px 0}}
.plan b {{font-size:.95rem;color:#e2e8f0}}
.plan .stop b {{color:{RED}}} .plan .tgt b {{color:{GREEN}}}
</style>""", unsafe_allow_html=True)


# ---------- helpers ----------
def chips(reasons) -> str:
    return "".join(f'<span class="chip{"" if good else " bad"}">{text}</span>' for text, good in reasons)


def sparkline(values, color, w=120, h=26) -> str:
    lo, hi = min(values), max(values)
    pts = " ".join(f"{i * w / (len(values) - 1):.1f},{h - (v - lo) / ((hi - lo) or 1) * h:.1f}"
                   for i, v in enumerate(values))
    return (f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'style="margin-top:4px"><polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>')


def tile(label, value, sub, color=MUTED, tip="", extra="") -> str:
    return (f'<div class="tile" title="{tip}"><div class="tl">{label}</div><div class="tv">{value}</div>'
            f'<div class="ts" style="color:{color}">{sub}</div>{extra}</div>')


def money(v) -> str:
    return f"{'-' if v < 0 else ''}₹{abs(v):,.0f}"


def safe_md(text: str) -> str:
    return text.replace("[", "(").replace("]", ")").replace("$", "\\$")


def show_headlines(items):
    if not items:
        st.caption("No headlines in the last few days.")
    for h in items:
        icon = "🟢" if h["sentiment"] >= 0.2 else "🔴" if h["sentiment"] <= -0.2 else "⚪"
        st.markdown(f"{icon} `{h['sentiment']:+.2f}` [{safe_md(h['title'])}]({h['link']}) "
                    f"<span style='color:{MUTED};font-size:.8rem'>· {h['source']}</span>",
                    unsafe_allow_html=True)


def how_it_works():
    st.markdown(f"""
**1. Chart check (all stocks).** One fast price download for every stock in the list. Stocks trading
under ₹5 crore a day are skipped (hard to buy and sell). Each stock gets chart points:

| Check | Points |
|---|---|
| Uptrend: price > EMA20 > EMA50 | +2 |
| Pulled back near EMA20 (good entry) | +1 |
| RSI 45-65 (healthy momentum) | +1 |
| Volume 1.5x normal on an up move | +1 |
| Within 5% of 52-week high | +0.5 |
| Downtrend / RSI > 75 / RSI < 30 | -2 / -1 / -1 |

**2. News check (top N only).** The best chart setups get a Google News search of the last
{config.NEWS_LOOKBACK_DAYS} days. Each headline is scored -1 to +1, and newer ones count more.

**3. Final score** = chart points + 3 × news score.

**4. Trade plan.** Stop-loss = entry − {config.ATR_STOP_MULT} × ATR (the stock's normal daily move).
Target = {config.REWARD_RISK:g} × risk above entry. Quantity is chosen so that hitting the stop loses only your chosen risk %.

**Rules that protect you:** always place the stop-loss, avoid buying when the market trend is down,
and paper-trade for a few weeks before using real money.
""")


# ---------- sidebar ----------
with st.sidebar:
    st.header("⚙️ Scan")
    universe = st.selectbox("Stocks to scan", UNIVERSES, index=2)
    news_top_n = st.slider("Read news for top N chart setups", 10, 50, 30, 5,
                           help="More = slower and more Google News requests.")
    run = st.button("🔍 Run scan", type="primary", width="stretch")

    st.divider()
    st.header("💰 Your money")
    capital = st.number_input("Trading capital (₹)", 10_000, 10_000_000, config.CAPITAL, 10_000)
    risk_pct = st.slider("Max risk per trade (%)", 0.25, 3.0, config.RISK_PER_TRADE_PCT, 0.25)
    st.caption(f"Max loss on one trade: **₹{capital * risk_pct / 100:,.0f}**")

    st.divider()
    min_score = st.slider("Top picks: minimum score", 0.0, 8.0, 3.0, 0.5)

st.title("📈 Swing Scanner")
st.caption("NSE stocks ranked by chart setup + latest news. It gives you a research list, not buy advice.")

# ---------- run ----------
if run:
    with st.container(border=True):
        bar = st.progress(0.0, text="⏳ Starting scan…")
        res = scan(universe, news_top_n, progress=lambda f, t: bar.progress(min(f, 1.0), text=f"⏳ {t}"))
        bar.progress(1.0, text="⏳ Checking Nifty 50 trend…")
        res["mood"] = market_mood()
    res["time"] = datetime.now()
    st.session_state.res = res
    st.rerun()  # redraw cleanly without the progress box

res = st.session_state.get("res")
df = news = None


@st.cache_data(ttl=600, show_spinner="Updating prices…")
def price_history(symbols: tuple) -> dict:
    return get_history(list(symbols))


def paper_form(key: str, symbol: str, name: str, qty: int, entry: float, stop: float, target: float,
               entry_date: date, score=None, why: str = ""):
    with st.form(key, border=False):
        c1, c2 = st.columns(2)
        qty = c1.number_input("Quantity", min_value=1, value=max(int(qty), 1), step=1)
        entry = c2.number_input("Buy price ₹", min_value=0.01, value=float(entry), format="%.2f")
        c3, c4 = st.columns(2)
        stop = c3.number_input("Stop-loss ₹", min_value=0.01, value=float(stop), format="%.2f")
        target = c4.number_input("Target ₹", min_value=0.01, value=float(target), format="%.2f")
        day = st.date_input("Bought on", value=entry_date, max_value=date.today(),
                            help="Tracking starts from the next trading day.")
        if st.form_submit_button("📝 Add paper trade", type="primary", width="stretch"):
            if not stop < entry < target:
                st.error("Stop-loss must be below the buy price, and target above it.")
            else:
                paper.add_trade(symbol, qty, entry, stop, target, day, name, score, why)
                st.toast(f"Added {qty} × {symbol} to paper trades", icon="✅")


# ---------- market mood (needs a scan) ----------
if res:
    df, news, mood = res["df"], res["news"], res["mood"]
    plans = pd.DataFrame([trade_plan(c, a, capital, risk_pct) for c, a in zip(df.close, df.atr)],
                         index=df.index)
    df = pd.concat([df, plans], axis=1)

    tiles = []
    if mood:
        up = mood["chg_5d_pct"] >= 0
        tiles.append(tile("Nifty 50", f"{mood['close']:,.0f}",
                          f"{'▲' if up else '▼'} {mood['chg_5d_pct']:+.2f}% in 5 days", GREEN if up else RED,
                          extra=sparkline(mood["spark"], GREEN if up else RED) if mood.get("spark") else ""))
        tcolor, tnote = {"Uptrend": (GREEN, "Good for swing buys"), "Sideways": ("#f59e0b", "Be selective"),
                         "Downtrend": (RED, "Avoid new buys")}[mood["trend"]]
        tiles.append(tile("Market trend", mood["trend"], tnote, tcolor, "Nifty 50 vs its 20 & 50-day averages"))
    breadth = ((df.close > df.ema20) & (df.ema20 > df.ema50)).mean() * 100
    tiles.append(tile("Stocks in uptrend", f"{breadth:.0f}%", "Healthy" if breadth >= 50 else "Weak",
                      GREEN if breadth >= 50 else RED, "Market breadth. Above 50% is healthy."))
    tiles.append(tile("Scanned", f"{len(df)}", f"of {res['total']} in {res['universe']}",
                      tip="Low-volume stocks are skipped"))
    st.markdown(f'<div class="tiles">{"".join(tiles)}</div>', unsafe_allow_html=True)

    if mood and mood["trend"] == "Downtrend":
        st.error("Market is falling. Most swing buys fail in a falling market. Consider waiting or using half size.")
    elif mood and mood["trend"] == "Sideways":
        st.warning("Market is sideways. Be selective and take profits quicker.")
    st.caption(f"Last scan: {res['time']:%d %b %Y, %I:%M %p} · {res['universe']} · "
               f"news read for {int(df.news_checked.sum())} stocks")
else:
    st.info("👈 Choose which stocks to scan and click **Run scan**. Nifty 200 takes about 30 seconds. "
            "Your **📝 Paper trades** tab works without a scan.")

tab_picks, tab_all, tab_chart, tab_paper, tab_help = st.tabs(
    ["🏆 Top picks", "📊 All stocks", "📈 Chart", "📝 Paper trades", "ℹ️ How it works"])
NEED_SCAN = "Run a scan first (sidebar → **Run scan**)."

# ---------- top picks ----------
with tab_picks:
    if not res:
        st.caption(NEED_SCAN)
    else:
        picks = df[(df.score >= min_score) & df.news_checked & ~(df.news_sentiment <= -0.2)].head(12)
        if picks.empty:
            st.info("No stock meets your minimum score. Lower the slider in the sidebar or scan a bigger list.")
        for start in range(0, len(picks), 3):
            cols = st.columns(3)
            for col, r in zip(cols, picks.iloc[start:start + 3].itertuples()):
                with col.container(border=True):
                    st.markdown(f'<span class="score">Score {r.score:.1f}</span><div class="sym">{r.symbol}</div>'
                                f'<div class="sub">{r.name} · {r.sector}</div>{chips(r.reasons)}'
                                f'<div class="plan"><div><span>Entry</span><b>₹{r.entry:,.2f}</b></div>'
                                f'<div class="stop"><span>Stop-loss</span><b>₹{r.stop_loss:,.2f}</b></div>'
                                f'<div class="tgt"><span>Target</span><b>₹{r.target:,.2f}</b></div></div>',
                                unsafe_allow_html=True)
                    if r.qty == 0:
                        st.caption("⚠️ One share risks more than your limit. Skip it or raise capital.")
                    else:
                        st.caption(f"Buy **{r.qty}** shares (₹{r.qty * r.entry:,.0f}) · "
                                   f"risk ₹{r.risk_rs:,} → reward ₹{r.reward_rs:,}")
                    with st.expander(f"📰 {r.headlines} news · {r.news_sentiment:+.2f}"):
                        show_headlines(news.get(r.symbol, []))
                    with st.popover("📝 Paper trade", width="stretch"):
                        paper_form(f"pt_{r.symbol}", r.symbol, r.name, r.qty, r.entry, r.stop_loss, r.target,
                                   res["history"][r.symbol].index[-1].date(), r.score, r.why)

# ---------- all stocks ----------
with tab_all:
    if not res:
        st.caption(NEED_SCAN)
    else:
        f1, f2, f3 = st.columns([2, 3, 2])
        q = f1.text_input("Search", placeholder="Symbol or company")
        sectors = f2.multiselect("Sector", sorted(df.sector.dropna().unique()))
        only_up = f3.toggle("Uptrend only", value=False)
        view = df
        if q:
            view = view[view.symbol.str.contains(q, case=False, regex=False)
                        | view.name.str.contains(q, case=False, regex=False)]
        if sectors:
            view = view[view.sector.isin(sectors)]
        if only_up:
            view = view[(view.close > view.ema20) & (view.ema20 > view.ema50)]
        nc = st.column_config.NumberColumn
        st.dataframe(
            view[["symbol", "name", "sector", "score", "tech_score", "news_sentiment", "headlines", "rsi",
                  "chg_5d_pct", "from_52w_high_pct", "vol_ratio", "turnover_cr", "entry", "stop_loss",
                  "target", "qty", "why"]],
            hide_index=True, width="stretch", height=620,
            column_config={
                "symbol": "Symbol", "name": "Company", "sector": "Sector",
                "score": st.column_config.ProgressColumn("Score", min_value=-5, max_value=9, format="%.1f"),
                "tech_score": nc("Chart", format="%.1f"),
                "news_sentiment": nc("News", format="%.2f", help="Blank = news not checked"),
                "headlines": nc("Headlines"),
                "rsi": nc("RSI", format="%.0f"),
                "chg_5d_pct": nc("5D %", format="%.1f%%"),
                "from_52w_high_pct": nc("From 52W high", format="%.1f%%"),
                "vol_ratio": nc("Volume ×", format="%.1f"),
                "turnover_cr": nc("Turnover ₹Cr/day", format="%.0f"),
                "entry": nc("Entry ₹", format="%.2f"), "stop_loss": nc("Stop ₹", format="%.2f"),
                "target": nc("Target ₹", format="%.2f"), "qty": nc("Qty"),
                "why": st.column_config.TextColumn("Why", width="large"),
            })
        st.caption(f"{len(view)} stocks. Click a column header to sort.")

# ---------- chart ----------
with tab_chart:
    if not res:
        st.caption(NEED_SCAN)
    else:
        names = dict(zip(df.symbol, df.name))
        sym = st.selectbox("Stock", df.symbol.tolist(), format_func=lambda s: f"{s} · {names[s]}")
        r = df[df.symbol == sym].iloc[0]
        h = add_emas(res["history"][sym]).tail(130)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Score", f"{r.score:.1f}")
        m2.metric("Price", f"₹{r.close:,.2f}", f"{r.chg_5d_pct:+.1f}% 5D")
        m3.metric("RSI", f"{r.rsi:.0f}")
        m4.metric("Volume", f"{r.vol_ratio:.1f}× avg")
        m5.metric("News", "not checked" if not r.news_checked else f"{r.news_sentiment:+.2f}")
        st.markdown(chips(r.reasons), unsafe_allow_html=True)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
        fig.add_candlestick(x=h.index, open=h.Open, high=h.High, low=h.Low, close=h.Close, name="Price",
                            increasing_line_color=GREEN, decreasing_line_color=RED, row=1, col=1)
        fig.add_scatter(x=h.index, y=h.EMA20, name="EMA20", line=dict(color="#38bdf8", width=1.5), row=1, col=1)
        fig.add_scatter(x=h.index, y=h.EMA50, name="EMA50", line=dict(color="#f59e0b", width=1.5), row=1, col=1)
        for y, label, color in [(r.target, "Target", GREEN), (r.entry, "Entry", MUTED), (r.stop_loss, "Stop", RED)]:
            fig.add_hline(y=y, line_dash="dot", line_color=color, row=1, col=1,
                          annotation_text=f"{label} ₹{y:,.2f}", annotation_position="top left",
                          annotation_font_color=color)
        vol_colors = [GREEN if c >= o else RED for o, c in zip(h.Open, h.Close)]
        fig.add_bar(x=h.index, y=h.Volume, name="Volume", marker_color=vol_colors, opacity=0.6, row=2, col=1)
        fig.update_layout(height=600, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False,
                          legend=dict(orientation="h", y=1.05, x=0), hovermode="x unified")
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, width="stretch")

        if r.qty:
            st.success(f"**Plan:** buy {r.qty} shares near ₹{r.entry:,.2f} · stop-loss ₹{r.stop_loss:,.2f} "
                       f"(risk ₹{r.risk_rs:,}) · target ₹{r.target:,.2f} (reward ₹{r.reward_rs:,})")
        with st.popover("📝 Paper trade this stock"):
            paper_form(f"ptc_{sym}", sym, r["name"], r.qty, r.entry, r.stop_loss, r.target,
                       res["history"][sym].index[-1].date(), r.score, r.why)
        st.subheader("📰 Latest headlines")
        if r.news_checked:
            show_headlines(news.get(sym, []))
        else:
            st.caption("News wasn't checked for this stock because it wasn't in the top chart setups.")

# ---------- paper trades ----------
with tab_paper:
    trades = paper.load()

    with st.expander("➕ Add a trade manually (any NSE stock)", expanded=trades.empty):
        sym_in = st.text_input("NSE symbol", placeholder="e.g. TCS, RELIANCE, HDFCBANK", key="manual_sym")
        sym_in = sym_in.strip().upper()
        if sym_in:
            if df is not None and sym_in in set(df.symbol):
                r = df[df.symbol == sym_in].iloc[0]
                last_day = res["history"][sym_in].index[-1].date()
                paper_form(f"man_{sym_in}", sym_in, r["name"], r.qty, r.entry, r.stop_loss, r.target,
                           last_day, r.score, r.why)
            else:
                h = price_history((sym_in,)).get(sym_in)
                if h is None:
                    st.error(f"Couldn't find price data for **{sym_in}**. Check the NSE symbol.")
                else:
                    ind = indicators(h)
                    p = trade_plan(ind["close"], ind["atr"], capital, risk_pct)
                    st.caption(f"Last close ₹{ind['close']:,.2f}. Stop and target are suggested from ATR; edit them if you like.")
                    paper_form(f"man_{sym_in}", sym_in, sym_in, p["qty"], p["entry"], p["stop_loss"],
                               p["target"], h.index[-1].date())

    if trades.empty:
        st.info("No paper trades yet. Use **📝 Paper trade** on any Top-pick card, or add one above. "
                "The app then follows each trade every day and closes it automatically when the "
                "stop-loss or target is hit.")
    else:
        hist = price_history(tuple(sorted(trades.symbol.unique())))
        trades, changed = paper.evaluate(trades, hist)
        if changed:
            st.toast("Some paper trades hit their stop-loss or target and were closed.", icon="🔔")
        t = paper.with_pnl(trades)
        t["result"] = t.pnl.map(lambda v: "" if pd.isna(v) else ("🟢" if v >= 0 else "🔴"))
        open_t, closed = t[t.status == "OPEN"], t[t.status == "CLOSED"]

        realized = closed.pnl.sum()
        unrealized = open_t.pnl.sum()
        wins = int((closed.pnl > 0).sum())
        win_rate = wins / len(closed) * 100 if len(closed) else 0
        avg_r = closed.r_multiple.mean() if len(closed) else 0
        tl = [
            tile("Total P&L", money(realized + unrealized), "booked + open",
                 GREEN if realized + unrealized >= 0 else RED),
            tile("Booked P&L", money(realized), f"{len(closed)} closed trades", GREEN if realized >= 0 else RED),
            tile("Win rate", f"{win_rate:.0f}%" if len(closed) else "-", f"{wins} wins / {len(closed) - wins} losses",
                 GREEN if win_rate >= 40 else RED if len(closed) else MUTED,
                 "With a 1:2 reward/risk, about 34% wins is break-even."),
            tile("Avg result", f"{avg_r:+.2f}R" if len(closed) else "-", "per closed trade",
                 GREEN if avg_r > 0 else RED if len(closed) else MUTED,
                 "R = profit ÷ risk. +1R means you made what you risked."),
            tile("Open trades", f"{len(open_t)}", f"₹{open_t.invested.sum():,.0f} invested · {money(unrealized)} open P&L",
                 GREEN if unrealized >= 0 else RED),
        ]
        st.markdown(f'<div class="tiles">{"".join(tl)}</div>', unsafe_allow_html=True)
        if len(closed) < 20:
            st.caption(f"📏 {len(closed)}/20 closed trades. Judge the strategy only after at least 20 closed trades. "
                       "A few trades can be pure luck.")

        nc = st.column_config.NumberColumn
        st.subheader(f"Open trades ({len(open_t)})")
        if open_t.empty:
            st.caption("No open trades.")
        else:
            st.dataframe(
                open_t[["result", "symbol", "entry_date", "qty", "entry", "ltp", "stop_loss", "target",
                        "pnl", "pnl_pct", "days_held"]],
                hide_index=True, width="stretch",
                column_config={
                    "result": st.column_config.TextColumn("", width="small"), "symbol": "Symbol",
                    "entry_date": "Bought on", "qty": nc("Qty"), "entry": nc("Buy ₹", format="%.2f"),
                    "ltp": nc("Now ₹", format="%.2f"), "stop_loss": nc("Stop ₹", format="%.2f"),
                    "target": nc("Target ₹", format="%.2f"), "pnl": nc("P&L ₹", format="%.0f"),
                    "pnl_pct": nc("P&L %", format="%.2f%%"),
                    "days_held": nc("Days", help=f"Auto-closed after {paper.MAX_HOLD_DAYS} trading days"),
                })
            labels = {row.id: f"{row.symbol} · {int(row.qty)} @ ₹{row.entry:,.2f} ({row.entry_date})"
                      for row in open_t.itertuples()}
            a1, a2, a3 = st.columns([3, 1.4, 1])
            pick = a1.selectbox("Manage trade", list(labels), format_func=labels.get, label_visibility="collapsed")
            row = open_t[open_t.id == pick].iloc[0]
            if a2.button("Sell now", width="stretch", help="Close at the last price", disabled=pd.isna(row.ltp)):
                paper.close_trade(pick, float(row.ltp))
                st.rerun()
            if a3.button("🗑 Delete", width="stretch", help="Remove this trade completely"):
                paper.delete_trade(pick)
                st.rerun()

        st.subheader(f"Closed trades ({len(closed)})")
        if closed.empty:
            st.caption("Nothing closed yet. Trades close automatically at stop-loss or target.")
        else:
            closed = closed.sort_values("exit_date", ascending=False)
            st.dataframe(
                closed[["result", "symbol", "entry_date", "exit_date", "qty", "entry", "exit_price",
                        "pnl", "pnl_pct", "r_multiple", "exit_reason"]],
                hide_index=True, width="stretch",
                column_config={
                    "result": st.column_config.TextColumn("", width="small"), "symbol": "Symbol",
                    "entry_date": "Bought on", "exit_date": "Sold on", "qty": nc("Qty"),
                    "entry": nc("Buy ₹", format="%.2f"), "exit_price": nc("Sell ₹", format="%.2f"),
                    "pnl": nc("P&L ₹", format="%.0f"), "pnl_pct": nc("P&L %", format="%.2f%%"),
                    "r_multiple": nc("R", format="%.2f"), "exit_reason": "Why closed",
                })
            curve = closed.sort_values("exit_date").assign(cum=lambda d: d.pnl.cumsum())
            fig = go.Figure(go.Scatter(x=curve.exit_date, y=curve.cum, mode="lines+markers", fill="tozeroy",
                                       line=dict(color=GREEN if curve.cum.iloc[-1] >= 0 else RED, width=2),
                                       hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>"))
            fig.update_layout(title="Booked profit over time", height=300, margin=dict(l=10, r=10, t=40, b=10),
                              yaxis_title="₹")
            st.plotly_chart(fig, width="stretch")

        st.download_button("⬇️ Download all trades (CSV)", trades[paper.COLUMNS].to_csv(index=False),
                           "paper_trades.csv", "text/csv")

with tab_help:
    how_it_works()
