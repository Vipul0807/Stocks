"""Settings you can edit freely."""

# NSE symbol -> search name used for news lookup.
# Liquid large/mid caps work best for swing trading (tight spreads, real news coverage).
WATCHLIST = {
    "RELIANCE": "Reliance Industries",
    "TCS": "TCS Tata Consultancy",
    "INFY": "Infosys",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "SBI State Bank of India",
    "AXISBANK": "Axis Bank",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "BHARTIARTL": "Bharti Airtel",
    "ITC": "ITC Ltd",
    "LT": "Larsen & Toubro",
    "HINDUNILVR": "Hindustan Unilever",
    "BAJFINANCE": "Bajaj Finance",
    "MARUTI": "Maruti Suzuki",
    "M&M": "Mahindra & Mahindra",
    "TMPV": "Tata Motors",
    "SUNPHARMA": "Sun Pharma",
    "TITAN": "Titan Company",
    "ASIANPAINT": "Asian Paints",
    "HCLTECH": "HCL Technologies",
    "WIPRO": "Wipro",
    "NTPC": "NTPC",
    "POWERGRID": "Power Grid",
    "ONGC": "ONGC",
    "COALINDIA": "Coal India",
    "TATASTEEL": "Tata Steel",
    "JSWSTEEL": "JSW Steel",
    "ADANIPORTS": "Adani Ports",
    "ULTRACEMCO": "UltraTech Cement",
    "DRREDDY": "Dr Reddy's",
    "CIPLA": "Cipla",
    "BEL": "Bharat Electronics",
    "HAL": "Hindustan Aeronautics HAL",
    "TRENT": "Trent Ltd",
    "DLF": "DLF",
}

NEWS_LOOKBACK_DAYS = 3        # only consider headlines from the last N days
MAX_HEADLINES_PER_STOCK = 15

# Risk management (used to suggest position size)
CAPITAL = 100000              # your trading capital in INR
RISK_PER_TRADE_PCT = 1.0      # max % of capital you are willing to lose on one trade
ATR_STOP_MULT = 1.5           # stop-loss = entry - 1.5 x ATR
REWARD_RISK = 2.0             # target = entry + 2 x risk
