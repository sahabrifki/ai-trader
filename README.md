# IHSG Swing Scanner

An independent Python scanner for the Indonesian Stock Exchange (IHSG) that identifies high-probability swing trade setups using technical analysis, smart money detection, and automatic risk management.

**No broker integration. No auto-trading. Decision support only.**

---

## Features

- Market regime filter — bearish market automatically raises quality bar and restricts phase types; crisis aborts scan entirely
- Candle confirmation — detects bullish engulfing, hammer, and plain bullish candles; scored as bonus signal
- Relative Strength vs IHSG — each stock's 5-day return vs benchmark; outperformers get score bonus
- Late-stage flag — price >10% above MA20 is flagged as DO NOT CHASE with pullback-only entry zone
- Cap tier grouping — output grouped into Large / Mid / Small / Low cap with per-tier context
- Automatic position sizing — lot count calculated from modal, risk per trade (1.5%), and max allocation (40%)
- Anti-gorengan filter — excludes manipulated/pump-dump stocks via 5-day price range threshold
- Pick journal — auto-saves qualified setups to CSV; auto-detects SL/TP1/TP2 hits on subsequent runs; prints win-rate stats after 5+ closed trades
- Top 3 summary — actionable-now setups at end of output (excludes late-stage and overbought)

---

## Installation

**Requirements: Python 3.9+**

```bash
# 1. Clone the repo
git clone https://github.com/sahabrifki/ai-trader.git
cd ai-trader

# 2. (Recommended) Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Run daily scan
```bash
python3 scripts/ihsg_swing_scanner.py
```

### Review pick journal (check outcomes of past setups)
```bash
python3 scripts/ihsg_swing_scanner.py journal
```

### Auto-run every morning via cron (optional)
```bash
# Add to crontab — runs at 08:45 WIB Mon–Fri before market opens at 09:00
45 8 * * 1-5 cd /path/to/ai-trader && python3 scripts/ihsg_swing_scanner.py >> logs/scan.log 2>&1
```

---

## Configuration

Edit the `CONFIG` block at the top of `scripts/ihsg_swing_scanner.py`:

| Variable | Default | Description |
|---|---|---|
| `PORTFOLIO` | `{}` | Your open positions `{"TICKER.JK": entry_price}` — always included in output |
| `MIN_SCORE` | `55` | Minimum technical score to qualify (0–100) |
| `MAX_GORENGAN_RANGE` | `15%` | Max 5-day price range — stocks above this are excluded as manipulated |
| `MODAL` | `10_000_000` | Your total trading capital in IDR |
| `MAX_ALLOC_PCT` | `0.40` | Max allocation per position (40% of modal) |
| `RISK_PER_TRADE_PCT` | `0.015` | Max loss per trade as % of modal (1.5%) |
| `LATE_STAGE_THRESHOLD` | `10.0` | % above MA20 that triggers late-stage warning |

---

## Scanning Methodology

The scanner runs 5 sequential steps on a universe of ~80 liquid IHSG stocks.

### Step 1 — Universe Filter

Before any analysis, stocks are filtered for tradability:

- **Liquidity**: Average daily value (volume × price) > IDR 5 billion
- **Anti-gorengan**: 5-day price range < 15% — eliminates pump-dump / manipulated stocks
- **Data requirement**: Minimum 60 days of history

### Step 2 — Technical Scoring (0–100 pts)

Each stock is scored on the following criteria:

| Condition | Points |
|---|---|
| Close > MA20 | +20 |
| MA20 > MA50 (uptrend alignment) | +20 |
| 5-day return > 0% | +15 |
| Breakout: close > highest close of prior 10 days | +25 |
| Volume ratio ≥ 2.0x 20-day avg | +20 |
| Volume ratio 1.5x–2.0x | +15 |
| Volume ratio 1.0x–1.5x | +8 |
| RSI 45–65 (healthy momentum zone) | +10 |
| RSI 65–75 (hot but not extreme) | +5 |
| RSI > 75 (overbought) | –15 |
| RSI < 35 (oversold) | +5 |
| MACD fresh bullish crossover | +15 |
| MACD bullish and rising | +8 |
| Smart accumulation (price up + volume up 5d) | +8 |
| Distribution pattern (price down + volume up 5d) | –10 |
| RS vs IHSG ≥ +4% (strong outperformer) | +15 |
| RS vs IHSG ≥ +2% (moderate outperformer) | +8 |
| RS vs IHSG < –2% (underperformer) | –8 |
| Bullish engulfing candle | +8 |
| Hammer candle | +5 |
| Plain bullish candle (close > open) | +3 |

Score is capped at 100.

### Step 3 — Phase Classification

Based on score and market structure, each stock is assigned a phase:

| Phase | Criteria |
|---|---|
| **Expansion** | Score ≥ 75, volume ratio ≥ 1.5x, price > MA20 — confirmed breakout in progress |
| **Pre-Breakout** | Volatility squeeze or tight range (5d range < 5%), score ≥ 50 — building pressure |
| **Accumulation** | Tight range + rising volume without breakout — smart money loading |
| **Oversold Bounce** | RSI < 35, price < MA20, volume spike — potential reversal |
| **Weak** | None of the above — excluded from output |

### Step 4 — Market Regime Filter

Before outputting setups, the scanner checks IHSG's own 5-day return:

| IHSG 5d Return | Regime | Effect |
|---|---|---|
| ≥ –2% | **Normal** | MIN_SCORE as configured, all phases allowed |
| –2% to –4% | **Bearish** | MIN_SCORE raised to 70, only Expansion and Oversold Bounce qualify |
| < –4% | **Crisis** | Scan aborted — no setups generated |

This prevents the scanner from generating "buy" signals during a broad market downturn.

### Step 5 — Entry, Stop Loss, and Take Profit

Levels are derived from price structure, not fixed percentages:

**Entry zone**
- If price > MA20 × 1.03 (extended): entry set at MA20 ± 1% — pullback entry
- Otherwise: entry set near current price ± 0.5%

**Stop Loss**
- Calculated from nearest swing support below entry (30-day lookback for local minima)
- Minimum distance: 3.5% below entry low
- Maximum distance: 7% below entry low (hard cap)
- Guaranteed to be below entry low

**Take Profit**
- TP1: entry high + 4% (short-term target, 2–3 day hold)
- TP2: entry high + 12% (extended swing target)
- Minimum R/R to qualify: 1:1.5 at TP2

**Position Sizing** (based on user's configured `MODAL`):
- Risk budget per trade: `MODAL × RISK_PER_TRADE_PCT` (default IDR 150,000 for 10jt modal)
- Lots by risk: `risk_budget / (entry_high − SL) / 100`
- Lots by allocation: `MODAL × MAX_ALLOC_PCT / lot_cost`
- Suggested lots: `min(lots_by_risk, lots_by_allocation)`, minimum 1 lot

---

## Pick Journal

Every scan auto-saves qualified setups to `scripts/pick_journal.csv`. On subsequent runs, the scanner checks prior-day open picks against current prices and auto-updates outcomes:

| Outcome | Condition |
|---|---|
| `TP2_HIT` | Current price ≥ TP2 |
| `TP1_HIT` | Current price ≥ TP1 |
| `SL_HIT` | Current price ≤ SL |
| `OPEN` | None of the above |

After 5+ closed picks, the scanner prints win-rate statistics broken down by phase and sector.

Same-day picks are never auto-closed (the trade hasn't been entered yet).

---

## Output Example

```
IHSG SWING SCANNER v2.3
Date: Thursday, 23 April 2026 09:00
Universe: 80 tickers  |  Period: 120d
Min Score: 55  |  Max Gorengan Range: 15%

IHSG 5d return (benchmark): -2.30%
⚠️  MARKET REGIME: BEARISH — min_score raised to 70, phases: Expansion / Oversold Bounce only

SECTOR STRENGTH:
  Retail         STRONG  score: 97.5  ret5: +5.0%
  Energy         STRONG  score: 87.0  ret5: +8.8%
  ...

QUALIFIED SETUPS (5 found) — grouped by cap tier:

#1 — ELSA  [Energy / Mid]
  Phase:      Expansion
  Score:      100/100
  RSI(14):    70.3  [Healthy]
  Candle:     Bullish
  RS vs IHSG: +12.86% 🔥 OUTPERFORM
  Entry:        710 –   730
  SL:           680  (-4.1%)
  TP1:          760  (+4.1%)   R/R 1:0.75
  TP2:          820  (+12.3%)  R/R 1:2.25
  Suggested: 3 lot  (Rp219,000 = 22% modal)

⭐  TOP 3 BEST SETUPS — ACTIONABLE NOW
  #1 ELSA   Score:100/100  Entry: 710–730 | SL: 680 | TP2: 820 | R/R 1:1.8
  #2 LPPF   Score:96/100   Entry: 1,870–1,910 | SL: 1,790 | TP2: 2,140 | R/R 1:1.92
```

---

## Disclaimer

This tool is for **educational and decision-support purposes only**. It does not constitute financial advice. Always do your own research. Past scanner performance does not guarantee future results. Trading involves significant risk of loss.

---

## License

MIT
