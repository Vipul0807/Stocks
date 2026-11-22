# Swing Scanner (NSE)

Ranks NSE stocks for swing trades (held for a few days to a few weeks) using a **two-stage scan**:

1. **Chart check on every stock** in Nifty 50 / 100 / 200 / 500 (one bulk price download). Stocks trading under ₹5 Cr a day are skipped.
2. **News check for only the top N chart setups** (default 30): Google News headlines from the last 3 days, scored with VADER plus finance words. This keeps the scan fast and avoids getting blocked by Google.
3. **Score** = chart points + 3 × news sentiment.
4. **Trade plan**: entry, ATR stop-loss, a 1:2 target, and a quantity sized to your risk %.

## Run
```
.venv\Scripts\activate
streamlit run app.py              # dashboard at http://localhost:8501
python scanner.py "Nifty 500"     # terminal output
```
First-time setup: `python -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`

## Dashboard
- **Market tiles**: Nifty trend and breadth. Don't buy aggressively in a downtrend.
- **🏆 Top picks**: cards with reasons, a trade plan and headlines.
- **📊 All stocks**: every scanned stock, with search, sector filter and sorting.
- **📈 Chart**: candlesticks with EMA20/50, entry/stop/target lines and volume.
- **📝 Paper trades**: record pretend trades (stock, date, quantity, price). Each day the app checks prices and closes a trade automatically at its stop-loss or target, or after 20 trading days. Shows P&L, win rate, average R and a profit curve. Saved in `data/paper_trades.csv`.

## Files
| File | Job |
|---|---|
| `config.py` | Personal watchlist, capital, risk %, stop/target settings |
| `universe.py` | Downloads the Nifty index lists from NSE (cached weekly in `data/`) |
| `technicals.py` | Prices, indicators, chart score, market mood |
| `news.py` | Headlines and sentiment |
| `scanner.py` | The two-stage scan and trade plan |
| `app.py` | Dashboard |

Prices are end-of-day from Yahoo Finance. This is a research tool, not investment advice.
