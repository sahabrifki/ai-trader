"""
IHSG Swing Scanner v2.3
Upgrades vs v2.2:
- Market regime filter (bearish → raise min_score + restrict phases; crisis → abort)
- Candle confirmation (hammer/engulfing/bullish bonus + display)
- Top 3 actionable summary at end of output
"""

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import os
import csv
from datetime import datetime, date

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
PORTFOLIO = {
    # ticker: entry_price  — always included regardless of filters
    # e.g. "ESSA.JK": 800,
}

MIN_SCORE = 55
MAX_GORENGAN_RANGE = 15     # % 5-day range threshold
MIN_VOL_VALUE_IDR = 5e9     # avg daily value > 5B IDR
PERIOD = "120d"
MODAL = 10_000_000          # user's trading capital in IDR
MAX_ALLOC_PCT = 0.40        # max 40% of modal per position
RISK_PER_TRADE_PCT = 0.015  # 1.5% of modal = max loss per trade
LATE_STAGE_THRESHOLD = 10.0 # % above MA20 = late stage warning
RS_BONUS_THRESHOLD = 2.0    # RS vs IHSG > 2% = bonus score
JOURNAL_FILE = os.path.join(os.path.dirname(__file__), "pick_journal.csv")
JOURNAL_COLS = [
    "date","ticker","sector","cap_tier","phase","score",
    "entry_low","entry_high","sl","tp1","tp2","rr_tp2",
    "rsi","rs_vs_ihsg","late_stage","price_at_scan",
    "outcome","outcome_date","outcome_price","pnl_pct"
]

# ─────────────────────────────────────────
# UNIVERSE — 80+ liquid IHSG stocks
# ─────────────────────────────────────────
UNIVERSE = [
    # Large cap banking
    "BBCA.JK","BBRI.JK","BMRI.JK","BBNI.JK","BRIS.JK","BDMN.JK",
    # Large cap consumer
    "UNVR.JK","ICBP.JK","INDF.JK","MYOR.JK","SIDO.JK","KLBF.JK","CPIN.JK","JPFA.JK",
    # Energy / oil & gas
    "PGAS.JK","MEDC.JK","ENRG.JK","ESSA.JK","ELSA.JK","RUIS.JK",
    # Coal
    "ADRO.JK","ITMG.JK","PTBA.JK","HRUM.JK","AADI.JK","BUMI.JK","INDY.JK","KKGI.JK",
    # Mining / metals
    "ANTM.JK","INCO.JK","MDKA.JK","NCKL.JK","TINS.JK","PSAB.JK","MBMA.JK",
    # Petrochemical / basic materials
    "BRPT.JK","TPIA.JK","INKP.JK","TKIM.JK","FASW.JK",
    # Telco
    "TLKM.JK","EXCL.JK","ISAT.JK","TOWR.JK","TBIG.JK",
    # Infrastructure / construction
    "JSMR.JK","WIKA.JK","WSKT.JK","PTPP.JK","ADHI.JK",
    # Property
    "BSDE.JK","SMRA.JK","CTRA.JK","PWON.JK","LPKR.JK",
    # Auto / heavy equipment
    "ASII.JK","UNTR.JK","HEXA.JK",
    # Mining services
    "PTRO.JK","DSSA.JK",
    # Healthcare
    "MIKA.JK","HEAL.JK",
    # Retail / consumer cyclical
    "MAPI.JK","ACES.JK","HERO.JK","LPPF.JK",
    # Plantation / CPO
    "AALI.JK","SIMP.JK","TAPG.JK","SSMS.JK",
    # Finance / multifinance
    "ADMF.JK","BFIN.JK","WOMF.JK",
    # Mid cap specials
    "CUAN.JK","MBSS.JK","BULL.JK","LEAD.JK","TOBA.JK","GZCO.JK","ARCI.JK",
]
UNIVERSE = list(dict.fromkeys(UNIVERSE))

SECTOR_MAP = {
    "BBCA.JK":"Banking","BBRI.JK":"Banking","BMRI.JK":"Banking",
    "BBNI.JK":"Banking","BRIS.JK":"Banking","BDMN.JK":"Banking",
    "UNVR.JK":"Consumer","ICBP.JK":"Consumer","INDF.JK":"Consumer",
    "MYOR.JK":"Consumer","SIDO.JK":"Consumer","KLBF.JK":"Consumer",
    "CPIN.JK":"Consumer","JPFA.JK":"Consumer",
    "PGAS.JK":"Energy","MEDC.JK":"Energy","ENRG.JK":"Energy",
    "ESSA.JK":"Energy","ELSA.JK":"Energy","RUIS.JK":"Energy",
    "ADRO.JK":"Coal","ITMG.JK":"Coal","PTBA.JK":"Coal",
    "HRUM.JK":"Coal","AADI.JK":"Coal","BUMI.JK":"Coal",
    "INDY.JK":"Coal","KKGI.JK":"Coal",
    "ANTM.JK":"Mining","INCO.JK":"Mining","MDKA.JK":"Mining",
    "NCKL.JK":"Mining","TINS.JK":"Mining","PSAB.JK":"Mining","MBMA.JK":"Mining",
    "BRPT.JK":"Petrochem","TPIA.JK":"Petrochem","INKP.JK":"Petrochem",
    "TKIM.JK":"Petrochem","FASW.JK":"Petrochem",
    "TLKM.JK":"Telco","EXCL.JK":"Telco","ISAT.JK":"Telco",
    "TOWR.JK":"Telco","TBIG.JK":"Telco",
    "JSMR.JK":"Infrastructure","WIKA.JK":"Infrastructure","WSKT.JK":"Infrastructure",
    "PTPP.JK":"Infrastructure","ADHI.JK":"Infrastructure",
    "BSDE.JK":"Property","SMRA.JK":"Property","CTRA.JK":"Property",
    "PWON.JK":"Property","LPKR.JK":"Property",
    "ASII.JK":"Auto","UNTR.JK":"Auto","HEXA.JK":"Auto",
    "PTRO.JK":"Mining Services","DSSA.JK":"Mining Services",
    "MIKA.JK":"Healthcare","HEAL.JK":"Healthcare",
    "MAPI.JK":"Retail","ACES.JK":"Retail","HERO.JK":"Retail","LPPF.JK":"Retail",
    "AALI.JK":"Plantation","SIMP.JK":"Plantation","TAPG.JK":"Plantation","SSMS.JK":"Plantation",
    "ADMF.JK":"Finance","BFIN.JK":"Finance","WOMF.JK":"Finance",
    "CUAN.JK":"Mid-Cap Spec","MBSS.JK":"Mid-Cap Spec","BULL.JK":"Mid-Cap Spec",
    "LEAD.JK":"Mid-Cap Spec","TOBA.JK":"Mid-Cap Spec","GZCO.JK":"Mid-Cap Spec","ARCI.JK":"Mid-Cap Spec",
}

# ─────────────────────────────────────────
# CAP TIER MAP
# Large  : IDX30 / LQ45 core, mkt cap >10T IDR
# Mid    : mkt cap ~1T–10T IDR
# Small  : mkt cap ~100B–1T IDR
# Low    : mkt cap <100B IDR (micro)
# ─────────────────────────────────────────
CAP_TIER_MAP = {
    # Large Cap
    "BBCA.JK":"Large","BBRI.JK":"Large","BMRI.JK":"Large","BBNI.JK":"Large",
    "BRIS.JK":"Large","TLKM.JK":"Large","ASII.JK":"Large","UNTR.JK":"Large",
    "ICBP.JK":"Large","INDF.JK":"Large","UNVR.JK":"Large","KLBF.JK":"Large",
    "PGAS.JK":"Large","ANTM.JK":"Large","ADRO.JK":"Large","PTBA.JK":"Large",
    "INCO.JK":"Large","BRPT.JK":"Large","TPIA.JK":"Large","AALI.JK":"Large",
    "JSMR.JK":"Large","BSDE.JK":"Large","CTRA.JK":"Large","TOWR.JK":"Large",
    "MDKA.JK":"Large","TBIG.JK":"Large","EXCL.JK":"Large","ISAT.JK":"Large",
    "MYOR.JK":"Large","ITMG.JK":"Large","CPIN.JK":"Large","INKP.JK":"Large",
    "BDMN.JK":"Large",
    # Mid Cap
    "MEDC.JK":"Mid","ESSA.JK":"Mid","INDY.JK":"Mid","AADI.JK":"Mid",
    "HRUM.JK":"Mid","NCKL.JK":"Mid","TINS.JK":"Mid","MBMA.JK":"Mid",
    "TAPG.JK":"Mid","SSMS.JK":"Mid","SIMP.JK":"Mid","SMRA.JK":"Mid",
    "PWON.JK":"Mid","LPKR.JK":"Mid","WIKA.JK":"Mid","WSKT.JK":"Mid",
    "PTPP.JK":"Mid","ADHI.JK":"Mid","HEXA.JK":"Mid","MAPI.JK":"Mid",
    "ACES.JK":"Mid","LPPF.JK":"Mid","MIKA.JK":"Mid","HEAL.JK":"Mid",
    "DSSA.JK":"Mid","PTRO.JK":"Mid","JPFA.JK":"Mid","SIDO.JK":"Mid",
    "ADMF.JK":"Mid","TKIM.JK":"Mid","FASW.JK":"Mid","ELSA.JK":"Mid",
    "BUMI.JK":"Mid","PSAB.JK":"Mid",
    # Small Cap
    "ENRG.JK":"Small","RUIS.JK":"Small","KKGI.JK":"Small",
    "BFIN.JK":"Small","HERO.JK":"Small","TOBA.JK":"Small",
    "MBSS.JK":"Small","ARCI.JK":"Small","CUAN.JK":"Small",
    # Low / Micro Cap
    "BULL.JK":"Low","LEAD.JK":"Low","GZCO.JK":"Low","WOMF.JK":"Low",
}

CAP_TIER_ORDER = {"Large": 1, "Mid": 2, "Small": 3, "Low": 4}


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist


def get_swing_support(close, below_price, lookback=30):
    """Find nearest structural support strictly below below_price."""
    lows = close.tail(lookback)
    arr = lows.values
    local_mins = []
    for i in range(1, len(arr) - 1):
        if arr[i] < arr[i-1] and arr[i] < arr[i+1]:
            local_mins.append(arr[i])

    ceiling = below_price * 0.99
    valid = [x for x in local_mins if x < ceiling]
    if valid:
        return max(valid)  # nearest support below entry

    # Fallback: min of recent closes that are below ceiling
    fallback = lows[lows < ceiling]
    if len(fallback) > 0:
        return fallback.min()
    return lows.min()


def scan_ticker(ticker, is_portfolio=False, portfolio_entry=None, ihsg_ret5=0.0):
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=PERIOD)

        # Drop rows with incomplete OHLCV (e.g. partial data before market close)
        hist = hist.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])

        if len(hist) < 60:
            return None

        close = hist['Close']
        open_prices = hist['Open']
        vol = hist['Volume']
        high = hist['High']
        low = hist['Low']

        last = close.iloc[-1]
        vol_today = vol.iloc[-1]
        vol_avg20 = vol.rolling(20).mean().iloc[-2]

        if vol_avg20 <= 0:
            return None

        # Liquidity filter
        avg_daily_value = vol_avg20 * last
        if not is_portfolio and avg_daily_value < MIN_VOL_VALUE_IDR:
            return None

        # Anti-gorengan
        close5 = close.tail(5)
        range5_pct = (close5.max() - close5.min()) / close5.min() * 100
        if not is_portfolio and range5_pct > MAX_GORENGAN_RANGE:
            return None

        # Indicators
        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        rsi = calc_rsi(close).iloc[-1]
        macd_line, macd_sig, macd_hist = calc_macd(close)
        macd_cross_bull = bool((macd_hist.iloc[-1] > 0) and (macd_hist.iloc[-2] <= 0))
        macd_bull = bool(macd_hist.iloc[-1] > 0)
        macd_rising = bool(macd_hist.iloc[-1] > macd_hist.iloc[-2])

        vol_ratio = vol_today / vol_avg20
        ret5 = (last - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else 0
        highest_10 = close.iloc[-11:-1].max() if len(close) >= 11 else close.max()
        breakout = bool(last > highest_10)

        tr = pd.concat([high - low,
                        (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        atr_avg20_val = tr.rolling(14).mean().iloc[-20:-1].mean()
        vol_squeeze = bool(atr14 < atr_avg20_val * 0.9)

        price_up_5d = ret5 > 0
        vol_trend_5d = bool(vol.tail(5).mean() > vol.tail(10).head(5).mean())
        smart_accum = bool(price_up_5d and vol_trend_5d)
        distribution = bool((not price_up_5d) and vol_trend_5d)
        tight_range = bool(range5_pct < 5)

        # Scoring
        score = 0
        if last > ma20:             score += 20
        if ma20 > ma50:             score += 20
        if ret5 > 0:                score += 15
        if breakout:                score += 25
        if vol_ratio >= 2.0:        score += 20
        elif vol_ratio >= 1.5:      score += 15
        elif vol_ratio >= 1.0:      score += 8
        if 45 <= rsi <= 65:         score += 10
        elif 65 < rsi <= 75:        score += 5
        elif rsi > 75:              score -= 15
        elif rsi < 35:              score += 5
        if macd_cross_bull:         score += 15
        elif macd_bull and macd_rising: score += 8
        if smart_accum:             score += 8
        if distribution:            score -= 10

        # Relative Strength vs IHSG
        rs_vs_ihsg = round(ret5 - ihsg_ret5, 2)
        if rs_vs_ihsg >= RS_BONUS_THRESHOLD * 2:    score += 15  # strong outperformer
        elif rs_vs_ihsg >= RS_BONUS_THRESHOLD:       score += 8   # moderate outperformer
        elif rs_vs_ihsg < -RS_BONUS_THRESHOLD:       score -= 8   # underperformer

        # Candle confirmation (last bar)
        o0 = open_prices.iloc[-1]
        o1 = open_prices.iloc[-2]
        c0, c1 = close.iloc[-1], close.iloc[-2]
        h0, l0 = high.iloc[-1], low.iloc[-1]
        body = abs(c0 - o0)
        lower_wick = min(o0, c0) - l0
        upper_wick = h0 - max(o0, c0)
        bull_candle = c0 > o0
        hammer = body > 0 and lower_wick > 2 * body and upper_wick < body * 0.5
        engulfing = (c0 > o0 and o0 <= c1 and c0 >= o1 and o1 > c1)
        if engulfing:
            candle_signal = "Bull Engulf"
            score += 8
        elif hammer:
            candle_signal = "Hammer"
            score += 5
        elif bull_candle:
            candle_signal = "Bullish"
            score += 3
        else:
            candle_signal = "No confirm"

        score = max(0, min(score, 100))  # cap [0, 100]

        # Late-stage detection — price too far above MA20
        pct_above_ma20 = round((last - ma20) / ma20 * 100, 1)
        late_stage = pct_above_ma20 > LATE_STAGE_THRESHOLD

        # Phase
        if score >= 75 and vol_ratio >= 1.5 and last > ma20:
            phase = "Expansion"
        elif (tight_range or vol_squeeze) and score >= 50:
            phase = "Pre-Breakout"
        elif tight_range and smart_accum and not breakout:
            phase = "Accumulation"
        elif rsi < 35 and last < ma20 and vol_ratio >= 1.2:
            phase = "Oversold Bounce"
        else:
            phase = "Weak"

        # Entry zone from structure
        if last > ma20 * 1.03:
            # Price extended above MA20 — ideal entry is pullback to MA20 zone
            entry_low = int(round(ma20 * 0.99 / 10) * 10)
            entry_high = int(round(ma20 * 1.01 / 10) * 10)
        else:
            # Price near MA20 — entry near current
            entry_low = int(round(last * 0.995 / 10) * 10)
            entry_high = int(round(last * 1.005 / 10) * 10)

        # SL: structural support strictly below entry_low, capped at 7% max
        support = get_swing_support(close, below_price=entry_low, lookback=30)
        sl_raw = min(support * 0.98, entry_low * 0.965)  # at least 3.5% below entry_low
        sl_raw = max(sl_raw, entry_low * 0.93)           # cap: no wider than 7%
        sl = int(round(sl_raw / 10) * 10)

        # Guarantee SL < entry_low
        if sl >= entry_low:
            sl = int(round(entry_low * 0.96 / 10) * 10)

        sl_pct = round((entry_low - sl) / entry_low * 100, 1)
        tp1 = int(round(entry_high * 1.04 / 10) * 10)   # +4% short-term
        tp2 = int(round(entry_high * 1.12 / 10) * 10)   # +12% extended swing
        sl_distance = entry_high - sl
        rr_tp1 = round((tp1 - entry_high) / max(sl_distance, 1), 2)
        rr_tp2 = round((tp2 - entry_high) / max(sl_distance, 1), 2)

        # Skip: R/R too poor to be actionable
        if rr_tp2 < 1.5 and not is_portfolio:
            return None

        if rsi > 75:    rsi_flag = "OVERBOUGHT"
        elif rsi > 65:  rsi_flag = "Hot"
        elif rsi < 35:  rsi_flag = "Oversold"
        elif rsi < 45:  rsi_flag = "Neutral-Low"
        else:           rsi_flag = "Healthy"

        pnl = None
        if is_portfolio and portfolio_entry:
            pnl = round((last - portfolio_entry) / portfolio_entry * 100, 2)

        # Cap tier & position sizing for 10jt modal
        cap_tier = CAP_TIER_MAP.get(ticker, "Mid")
        lot_cost = int(entry_high * 100)                          # 1 lot = 100 shares
        max_alloc = MODAL * MAX_ALLOC_PCT
        risk_budget = MODAL * RISK_PER_TRADE_PCT                  # e.g. 150,000 IDR
        risk_per_lot = max((entry_high - sl) * 100, 1)
        lots_by_risk = int(risk_budget / risk_per_lot)            # lots within risk budget
        lots_by_alloc = int(max_alloc / lot_cost) if lot_cost > 0 else 0
        suggested_lots = max(1, min(lots_by_risk, lots_by_alloc)) # binding constraint
        suggested_alloc = suggested_lots * lot_cost

        return {
            'ticker': ticker.replace('.JK', ''),
            'sector': SECTOR_MAP.get(ticker, 'Other'),
            'last': round(last, 0),
            'ma20': round(ma20, 0),
            'ma50': round(ma50, 0),
            'rsi': round(rsi, 1),
            'rsi_flag': rsi_flag,
            'macd_cross': macd_cross_bull,
            'macd_bull': macd_bull,
            'macd_rising': macd_rising,
            'ret5': round(ret5, 2),
            'vol_ratio': round(vol_ratio, 2),
            'score': score,
            'phase': phase,
            'range5': round(range5_pct, 2),
            'vol_squeeze': vol_squeeze,
            'smart_accum': smart_accum,
            'distribution': distribution,
            'tight': tight_range,
            'entry_low': int(entry_low),
            'entry_high': int(entry_high),
            'sl': int(sl),
            'sl_pct': sl_pct,
            'tp1': int(tp1),
            'tp2': int(tp2),
            'rr_tp1': rr_tp1,
            'rr_tp2': rr_tp2,
            'support': round(support, 0),
            'atr14': round(atr14, 0),
            'is_portfolio': is_portfolio,
            'portfolio_entry': portfolio_entry,
            'pnl': pnl,
            'rs_vs_ihsg': rs_vs_ihsg,
            'late_stage': late_stage,
            'pct_above_ma20': pct_above_ma20,
            'candle_signal': candle_signal,
            'cap_tier': cap_tier,
            'lot_cost': lot_cost,
            'suggested_lots': suggested_lots,
            'suggested_alloc': suggested_alloc,
            'risk_per_lot': risk_per_lot,
        }

    except Exception:
        return None


def fetch_ihsg_ret5():
    """Fetch IHSG 5-day return for RS calculation."""
    try:
        jkse = yf.Ticker("^JKSE")
        h = jkse.history(period="10d")
        if len(h) >= 6:
            return round((h['Close'].iloc[-1] - h['Close'].iloc[-6]) / h['Close'].iloc[-6] * 100, 2)
    except Exception:
        pass
    return 0.0


def run_scan(portfolio_override=None, min_score=MIN_SCORE, force=False):
    if portfolio_override:
        global PORTFOLIO
        PORTFOLIO = portfolio_override

    print(f"\n{'='*60}")
    print(f"IHSG SWING SCANNER v2.3")
    print(f"Date: {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print(f"Universe: {len(UNIVERSE)} tickers  |  Period: {PERIOD}")
    print(f"Min Score: {min_score}  |  Max Gorengan Range: {MAX_GORENGAN_RANGE}%")
    print(f"{'='*60}\n")

    # Fetch IHSG benchmark return once
    ihsg_ret5 = fetch_ihsg_ret5()
    print(f"IHSG 5d return (benchmark): {ihsg_ret5:+.2f}%")

    # Market regime filter
    if ihsg_ret5 < -4.0:
        print(f"\n🚨 MARKET REGIME: CRISIS (IHSG {ihsg_ret5:+.1f}% in 5d)")
        if not force:
            print(f"   Scan aborted — conditions too bearish for swing entries.")
            print(f"   Wait for IHSG to stabilize before re-entering.")
            print(f"   Use --force to override and scan anyway.\n")
            print(f"{'='*60}\n")
            return
        print(f"   ⚠️  --force override active — scanning with min_score=80, Expansion/Oversold Bounce only\n")
        effective_min_score = 80
        regime_valid_phases = {'Expansion', 'Oversold Bounce'}
    elif ihsg_ret5 < -2.0:
        regime = "BEARISH"
        effective_min_score = max(min_score, 70)
        regime_valid_phases = {'Expansion', 'Oversold Bounce'}
        print(f"⚠️  MARKET REGIME: BEARISH — min_score raised to {effective_min_score}, phases: Expansion / Oversold Bounce only\n")
    else:
        regime = "NORMAL"
        effective_min_score = min_score
        regime_valid_phases = {'Expansion', 'Pre-Breakout', 'Accumulation', 'Oversold Bounce'}
        print(f"✅  MARKET REGIME: NORMAL\n")

    results = []
    errors = []

    for t in UNIVERSE:
        is_port = t in PORTFOLIO
        entry_px = PORTFOLIO.get(t)
        r = scan_ticker(t, is_portfolio=is_port, portfolio_entry=entry_px, ihsg_ret5=ihsg_ret5)
        if r:
            results.append(r)
        else:
            errors.append(t)

    if not results:
        print("No data returned.")
        return

    df = pd.DataFrame(results)

    # Sector strength
    sector_strength = df.groupby('sector').agg(
        avg_score=('score', 'mean'),
        avg_ret5=('ret5', 'mean'),
        n_above60=('score', lambda x: (x >= 60).sum()),
    ).round(1).sort_values('avg_score', ascending=False)

    print("SECTOR STRENGTH:")
    print("-" * 52)
    for sec, row in sector_strength.iterrows():
        tag = "STRONG" if row['avg_score'] >= 55 else ("NEUTRAL" if row['avg_score'] >= 35 else "WEAK  ")
        bar = "█" * int(row['avg_score'] / 10)
        print(f"  {sec:<18} {tag}  score:{row['avg_score']:5.1f}  ret5:{row['avg_ret5']:+5.1f}%  {bar}")

    # Qualified: valid phase + min score (regime-adjusted), OR portfolio override
    qualified = df[
        ((df['score'] >= effective_min_score) & (df['phase'].isin(regime_valid_phases))) |
        (df['is_portfolio'])
    ].copy()
    qualified = qualified.sort_values('score', ascending=False)

    print(f"\n\nQUALIFIED SETUPS ({len(qualified)} found) — grouped by cap tier:")

    qualified['_tier_order'] = qualified['cap_tier'].map(CAP_TIER_ORDER).fillna(5)
    qualified = qualified.sort_values(['_tier_order', 'score'], ascending=[True, False])

    current_tier = None
    rank = 1
    for _, r in qualified.iterrows():
        # Print tier header when tier changes
        if r['cap_tier'] != current_tier:
            current_tier = r['cap_tier']
            tier_labels = {
                "Large": "LARGE CAP  (mkt cap >10T — 1 lot bisa mahal, liquidity tinggi)",
                "Mid":   "MID CAP    (mkt cap 1T–10T — sweet spot untuk swing)",
                "Small": "SMALL CAP  (mkt cap 100B–1T — volatilitas lebih tinggi)",
                "Low":   "LOW CAP    (mkt cap <100B — hati-hati gorengan)",
            }
            print(f"\n{'='*60}")
            print(f"  {tier_labels.get(current_tier, current_tier)}")
            print(f"{'='*60}")

        tag = " [PORTFOLIO]" if r['is_portfolio'] else ""
        ob_warn = " ⚠️ OVERBOUGHT" if r['rsi_flag'] == "OVERBOUGHT" else ""
        dist_warn = " ⚠️ DISTRIBUTION" if r['distribution'] else ""
        rs_label = (f"  RS vs IHSG: {r['rs_vs_ihsg']:>+6.2f}%"
                    + (" 🔥 OUTPERFORM" if r['rs_vs_ihsg'] >= RS_BONUS_THRESHOLD else
                       (" ⚠️ UNDERPERFORM" if r['rs_vs_ihsg'] < -RS_BONUS_THRESHOLD else "  neutral")))

        print(f"\n#{rank} — {r['ticker']}  [{r['sector']} / {r['cap_tier']}]{tag}")
        print(f"  Phase:      {r['phase']}{ob_warn}{dist_warn}")
        print(f"  Score:      {r['score']}/100")
        print(f"  Price:      {r['last']:>8,.0f}  |  MA20: {r['ma20']:>8,.0f}  (+{r['pct_above_ma20']:.1f}%)  |  MA50: {r['ma50']:>8,.0f}")
        print(f"  RSI(14):    {r['rsi']:>5.1f}  [{r['rsi_flag']}]")
        print(f"  Candle:     {r['candle_signal']}")
        print(f"  MACD:       FreshCross={'YES 🔥' if r['macd_cross'] else 'No ':5}  Bull={str(r['macd_bull']):<5}  Rising={r['macd_rising']}")
        print(f"  5d Return:  {r['ret5']:>+6.2f}%  |  VolRatio: {r['vol_ratio']:.2f}x  |  Range5: {r['range5']:.1f}%")
        print(rs_label)
        print(f"  SmAccum:    {str(r['smart_accum']):<5}  |  Squeeze: {r['vol_squeeze']}")

        # Late-stage warning block
        if r['late_stage']:
            print(f"  {'─'*50}")
            print(f"  🚫 LATE STAGE — price {r['pct_above_ma20']:.1f}% above MA20")
            print(f"     DO NOT CHASE at current {r['last']:,}")
            print(f"     PULLBACK ENTRY ONLY: {r['entry_low']:,} – {r['entry_high']:,}")
            print(f"  {'─'*50}")
        else:
            print(f"  ---")

        print(f"  Entry:      {r['entry_low']:>8,} – {r['entry_high']:>8,}  ← DO NOT ENTER ABOVE {r['entry_high']:,}")
        print(f"  SL:         {r['sl']:>8,}  (-{r['sl_pct']}% from entry low)")
        tp1_pct = round((r['tp1'] - r['entry_high']) / r['entry_high'] * 100, 1)
        tp2_pct = round((r['tp2'] - r['entry_high']) / r['entry_high'] * 100, 1)
        print(f"  TP1:        {r['tp1']:>8,}  (+{tp1_pct}%)   R/R 1:{r['rr_tp1']}")
        print(f"  TP2:        {r['tp2']:>8,}  (+{tp2_pct}%)   R/R 1:{r['rr_tp2']}")
        print(f"  Support:    {r['support']:>8,.0f}  |  ATR14: {r['atr14']:,.0f}")
        print(f"  --- Sizing (modal Rp{MODAL/1e6:.0f}jt) ---")
        print(f"  1 lot cost: Rp{r['lot_cost']:>8,}  |  Suggested: {r['suggested_lots']} lot  "
              f"(Rp{r['suggested_alloc']:,} = {r['suggested_alloc']/MODAL*100:.0f}% modal)")
        print(f"  Max loss if SL hit: Rp{r['risk_per_lot'] * r['suggested_lots']:,}  "
              f"({r['risk_per_lot'] * r['suggested_lots'] / MODAL * 100:.1f}% modal)")

        if r['is_portfolio'] and r['pnl'] is not None:
            emoji = "✅" if r['pnl'] > 0 else "🔴"
            print(f"  P&L:        Entry {r['portfolio_entry']:,} → Now {r['last']:,.0f}  =  {r['pnl']:+.2f}% {emoji}")
            if r['rsi'] > 70:
                print(f"  ⚡ ACTION:  RSI {r['rsi']:.0f} — consider trimming 50% of position")

        rank += 1

    # Overbought alerts — exclude stocks already in qualified list
    qualified_tickers = set(qualified['ticker'])
    ob_list = df[
        (df['rsi'] > 72) &
        (~df['is_portfolio']) &
        (~df['ticker'].isin(qualified_tickers))
    ].sort_values('rsi', ascending=False)
    if not ob_list.empty:
        print(f"\n⚠️  AVOID — OVERBOUGHT (RSI > 72):")
        print("-" * 40)
        for _, r in ob_list.iterrows():
            print(f"  {r['ticker']:<8}  RSI:{r['rsi']:.0f}  5d:{r['ret5']:+.1f}%  Phase:{r['phase']}")

    # ── TOP PICK PER CAP TIER ─────────────────────────────────
    non_port = qualified[~qualified['is_portfolio']].copy()
    actionable = non_port[
        ~non_port['late_stage'] &
        (non_port['rsi_flag'] != 'OVERBOUGHT')
    ].sort_values('score', ascending=False)

    print(f"\n{'='*60}")
    print(f"⭐  BEST PICK PER CAP TIER — ACTIONABLE NOW")
    print(f"{'='*60}")

    tier_labels = {'Large': 'LARGE CAP', 'Mid': 'MID CAP', 'Small': 'SMALL CAP'}
    found_any = False
    for tier in ['Large', 'Mid', 'Small']:
        tier_picks = actionable[actionable['cap_tier'] == tier]
        if tier_picks.empty:
            print(f"\n  {tier_labels[tier]:<10}  — no qualified setup")
            continue
        found_any = True
        r = tier_picks.iloc[0]
        rs_str = f"RS {r['rs_vs_ihsg']:+.1f}%"
        sec_score = sector_strength.loc[r['sector'], 'avg_score'] if r['sector'] in sector_strength.index else 0
        print(f"\n  {tier_labels[tier]} — {r['ticker']}  Score:{r['score']}/100")
        print(f"  Entry: {r['entry_low']:,} – {r['entry_high']:,}  |  SL: {r['sl']:,}  |  TP2: {r['tp2']:,}  |  R/R 1:{r['rr_tp2']}")
        print(f"  {r['phase']} | RSI {r['rsi']:.0f} | {rs_str} | Candle: {r['candle_signal']} | {r['sector']} ({sec_score:.0f})")

    if not found_any:
        print("  No actionable setups today.")
    print(f"{'='*60}")

    print(f"\n{'='*60}")
    print(f"Scanned: {len(results)} | Qualified: {len(qualified)} | Skipped: {len(errors)}")
    best = qualified.iloc[0] if len(qualified) > 0 else None
    if best is not None:
        print(f"Best setup: {best['ticker']} (score {best['score']}, RSI {best['rsi']:.0f}, phase {best['phase']})")
    print(f"Top sector: {sector_strength.index[0]}")
    print(f"{'='*60}\n")

    # Auto-save non-portfolio picks to journal
    new_picks = qualified[~qualified['is_portfolio']]
    if len(new_picks) > 0:
        save_journal(new_picks)

    # Auto-check outcomes of past picks
    review_journal(silent=True)


# ─────────────────────────────────────────
# PICK JOURNAL
# ─────────────────────────────────────────

def save_journal(picks_df):
    """Append today's qualified picks to journal CSV (no duplicates for same date+ticker)."""
    today = date.today().isoformat()
    write_header = not os.path.exists(JOURNAL_FILE)

    # Load existing to check duplicates
    existing_keys = set()
    if os.path.exists(JOURNAL_FILE):
        try:
            existing = pd.read_csv(JOURNAL_FILE)
            for _, row in existing.iterrows():
                existing_keys.add((str(row['date']), str(row['ticker'])))
        except Exception:
            pass

    new_rows = 0
    with open(JOURNAL_FILE, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLS)
        if write_header:
            writer.writeheader()
        for _, r in picks_df.iterrows():
            key = (today, r['ticker'])
            if key in existing_keys:
                continue
            writer.writerow({
                'date': today,
                'ticker': r['ticker'],
                'sector': r['sector'],
                'cap_tier': r['cap_tier'],
                'phase': r['phase'],
                'score': r['score'],
                'entry_low': r['entry_low'],
                'entry_high': r['entry_high'],
                'sl': r['sl'],
                'tp1': r['tp1'],
                'tp2': r['tp2'],
                'rr_tp2': r['rr_tp2'],
                'rsi': r['rsi'],
                'rs_vs_ihsg': r['rs_vs_ihsg'],
                'late_stage': r['late_stage'],
                'price_at_scan': r['last'],
                'outcome': 'OPEN',
                'outcome_date': '',
                'outcome_price': '',
                'pnl_pct': '',
            })
            new_rows += 1

    if new_rows > 0:
        print(f"📓 Journal: {new_rows} new pick(s) saved → {JOURNAL_FILE}")


def review_journal(silent=False):
    """
    Auto-update outcomes for open picks by checking current price vs SL/TP1/TP2.
    Print summary stats if journal has enough history.
    """
    if not os.path.exists(JOURNAL_FILE):
        return

    try:
        df = pd.read_csv(JOURNAL_FILE)
    except Exception:
        return

    if df.empty:
        return

    today_str = date.today().isoformat()
    # Only auto-close picks that were saved on a PRIOR day — same-day picks
    # haven't been entered yet (price_at_scan may already be above entry_high)
    open_picks = df[(df['outcome'] == 'OPEN') & (df['date'] != today_str)].copy()
    updated = 0
    rows_to_update = []

    for idx, row in open_picks.iterrows():
        try:
            tk = yf.Ticker(row['ticker'] + '.JK')
            hist = tk.history(period='5d')
            if hist.empty:
                continue
            current = hist['Close'].iloc[-1]
            entry = float(row['entry_high'])
            sl = float(row['sl'])
            tp1 = float(row['tp1'])
            tp2 = float(row['tp2'])

            outcome = 'OPEN'
            if current <= sl:
                outcome = 'SL_HIT'
            elif current >= tp2:
                outcome = 'TP2_HIT'
            elif current >= tp1:
                outcome = 'TP1_HIT'

            if outcome != 'OPEN':
                pnl = round((current - entry) / entry * 100, 2)
                rows_to_update.append((idx, outcome, today_str, round(float(current), 0), pnl))
                updated += 1
        except Exception:
            continue

    if updated > 0:
        for idx, outcome, odate, oprice, pnl in rows_to_update:
            df.loc[idx, 'outcome'] = outcome
            df.loc[idx, 'outcome_date'] = odate
            df.loc[idx, 'outcome_price'] = oprice
            df.loc[idx, 'pnl_pct'] = pnl
        df.to_csv(JOURNAL_FILE, index=False)
        if not silent:
            print(f"📓 Journal: {updated} outcome(s) auto-updated")

    # Stats — only show if ≥5 closed picks
    closed = df[df['outcome'] != 'OPEN']
    if len(closed) < 5:
        if not silent:
            print(f"📓 Journal: {len(closed)} closed picks so far (need 5+ for stats)")
        return

    print(f"\n{'='*60}")
    print(f"📓 PICK JOURNAL STATS  ({len(closed)} closed picks)")
    print(f"{'='*60}")

    wins = closed[closed['outcome'].isin(['TP1_HIT', 'TP2_HIT'])]
    losses = closed[closed['outcome'] == 'SL_HIT']
    win_rate = len(wins) / len(closed) * 100

    pnl_vals = closed['pnl_pct'].astype(float).dropna()
    print(f"  Win Rate:       {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
    if len(pnl_vals) > 0:
        best_idx = pnl_vals.idxmax()
        worst_idx = pnl_vals.idxmin()
        print(f"  Avg PnL:        {pnl_vals.mean():+.2f}%")
        print(f"  Best trade:     {pnl_vals.max():+.2f}%  ({closed.loc[best_idx, 'ticker']})")
        print(f"  Worst trade:    {pnl_vals.min():+.2f}%  ({closed.loc[worst_idx, 'ticker']})")
    else:
        print(f"  Avg PnL:        (no pnl data yet)")

    # Win rate by phase
    print(f"\n  By Phase:")
    for phase, grp in closed.groupby('phase'):
        w = (grp['outcome'].isin(['TP1_HIT','TP2_HIT'])).sum()
        print(f"    {phase:<20} {w}/{len(grp)}  ({w/len(grp)*100:.0f}% win)")

    # Win rate by sector
    print(f"\n  By Sector (top 5):")
    sec_stats = closed.groupby('sector').apply(
        lambda g: pd.Series({
            'n': len(g),
            'wins': g['outcome'].isin(['TP1_HIT','TP2_HIT']).sum(),
            'avg_pnl': g['pnl_pct'].astype(float).mean()
        })
    ).sort_values('avg_pnl', ascending=False).head(5)
    for sec, srow in sec_stats.iterrows():
        avg_str = f"{srow['avg_pnl']:+.2f}%" if not pd.isna(srow['avg_pnl']) else "n/a"
        print(f"    {sec:<18} {srow['wins']:.0f}/{srow['n']:.0f}  avg {avg_str}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if 'journal' in args:
        review_journal(silent=False)
    else:
        run_scan(force='--force' in args)
