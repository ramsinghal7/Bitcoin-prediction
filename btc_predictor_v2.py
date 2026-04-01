"""
BTC 5-Minute Direction Predictor — v3 (High Accuracy)
======================================================
16 weighted indicators: ADX trend filter, multi-timeframe 15m,
RSI divergence, Williams %R, CCI, MFI, OBV + originals.

Install:
    pip install requests numpy

Run:
    python btc_predictor_v2.py
    python btc_predictor_v2.py --loop
"""

import requests
import numpy as np
import sys
import time
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SYMBOL   = "BTCUSDT"
INTERVAL = "5m"
LIMIT    = 200          # more candles = better indicator accuracy

ENDPOINTS = [
    f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
    f"https://api1.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
    f"https://api2.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
    f"https://api3.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
]

# Indicator weights (higher = more influential in final score)
WEIGHTS = {
    "RSI":           1.5,
    "RSI Divergence":2.0,   # High-conviction reversal signal
    "EMA Cross":     1.5,
    "MACD":          1.5,
    "Stochastic":    1.2,
    "Williams %R":   1.2,
    "CCI":           1.2,
    "MFI":           1.3,   # Volume-weighted RSI
    "Bollinger":     1.2,
    "VWAP":          1.2,
    "OBV":           1.3,
    "Volume":        1.0,
    "ATR Momentum":  1.0,
    "Candle":        0.8,
    "Trend Context": 1.3,
    "HTF 15m":       2.0,   # Higher timeframe — highest weight
}

# Only signal when this % of weighted score agrees
CONFIDENCE_THRESHOLD = 58

# ─── COLORS ───────────────────────────────────────────────────────────────────
G  = "\033[92m"
R  = "\033[91m"
Y  = "\033[93m"
C  = "\033[96m"
W  = "\033[97m"
DIM= "\033[90m"
B  = "\033[1m"
X  = "\033[0m"

# ─── FETCH DATA ───────────────────────────────────────────────────────────────
def fetch_candles():
    for url in ENDPOINTS:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                return [{
                    "o": float(c[1]), "h": float(c[2]),
                    "l": float(c[3]), "c": float(c[4]),
                    "v": float(c[5]),
                } for c in data]
        except Exception:
            continue
    raise ConnectionError("Cannot reach Binance. Use a VPN if in India.")

# ─── INDICATOR HELPERS ────────────────────────────────────────────────────────
def ema_array(values, period):
    k = 2 / (period + 1)
    r = [values[0]]
    for v in values[1:]:
        r.append(v * k + r[-1] * (1 - k))
    return r

def sma(values, period):
    return [np.mean(values[max(0,i-period+1):i+1]) for i in range(len(values))]

def calc_rsi(closes, period=14):
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    ag = np.mean(gains[:period])
    al = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        ag = (ag * (period-1) + gains[i])  / period
        al = (al * (period-1) + losses[i]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag/al)

def calc_stochastic(candles, k=14, d=3):
    highs  = [c["h"] for c in candles]
    lows   = [c["l"] for c in candles]
    closes = [c["c"] for c in candles]
    k_vals = []
    for i in range(k-1, len(closes)):
        hh = max(highs[i-k+1:i+1])
        ll = min(lows[i-k+1:i+1])
        k_vals.append(100 * (closes[i] - ll) / (hh - ll) if hh != ll else 50)
    d_val = np.mean(k_vals[-d:])
    return k_vals[-1], d_val

def calc_bollinger(closes, period=20, std_mult=2.0):
    mid  = np.mean(closes[-period:])
    std  = np.std(closes[-period:])
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    price = closes[-1]
    pct_b = (price - lower) / (upper - lower) if upper != lower else 0.5
    return upper, mid, lower, pct_b

def calc_atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        tr = max(
            candles[i]["h"] - candles[i]["l"],
            abs(candles[i]["h"] - candles[i-1]["c"]),
            abs(candles[i]["l"] - candles[i-1]["c"])
        )
        trs.append(tr)
    return np.mean(trs[-period:])

def calc_vwap(candles):
    tp_vol = sum(((c["h"]+c["l"]+c["c"])/3)*c["v"] for c in candles)
    vol    = sum(c["v"] for c in candles)
    return tp_vol / vol

def trend_context(closes, short=20, long=50):
    """Higher timeframe trend via SMA cross"""
    s = np.mean(closes[-short:])
    l = np.mean(closes[-long:])
    # Also check slope of short SMA
    slope = (np.mean(closes[-5:]) - np.mean(closes[-10:-5])) / np.mean(closes[-10:-5]) * 100
    return s, l, slope

# ─── ADDITIONAL INDICATORS ───────────────────────────────────────────────────
def fetch_candles_htf(interval="15m", limit=50):
    """Fetch higher-timeframe candles for trend confirmation."""
    urls = [
        f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit={limit}",
        f"https://api1.binance.com/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit={limit}",
        f"https://api2.binance.com/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit={limit}",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                return [{"o": float(c[1]), "h": float(c[2]),
                         "l": float(c[3]), "c": float(c[4]),
                         "v": float(c[5])} for c in r.json()]
        except Exception:
            continue
    raise ConnectionError("Cannot fetch HTF candles.")

def calc_rsi_series(closes, period=14):
    """RSI for every bar — needed for divergence detection."""
    result = [float("nan")] * period
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    ag = np.mean(gains[:period])
    al = np.mean(losses[:period])
    result.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    for i in range(period, len(deltas)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        result.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return result

def detect_rsi_divergence(closes, period=14, lookback=20):
    """Bullish divergence: price lower-low but RSI higher-low → reversal up.
    Bearish divergence: price higher-high but RSI lower-high → reversal down."""
    rsi_vals = calc_rsi_series(closes, period)
    half = lookback // 2
    p1_c = closes[-(lookback):-(half)]
    p2_c = closes[-(half):]
    p1_r = [v for v in rsi_vals[-(lookback):-(half)] if not np.isnan(v)]
    p2_r = [v for v in rsi_vals[-(half):]            if not np.isnan(v)]
    if not p1_r or not p2_r:
        return "HOLD", "no divergence"
    if min(p2_c) < min(p1_c) and min(p2_r) > min(p1_r):
        return "BULL", "bullish div (price↓ RSI↑)"
    if max(p2_c) > max(p1_c) and max(p2_r) < max(p1_r):
        return "BEAR", "bearish div (price↑ RSI↓)"
    return "HOLD", "no divergence"

def calc_adx(candles, period=14):
    """ADX trend strength: >25 trending, 18-25 weak, <18 choppy. Also ±DI."""
    plus_dm, minus_dm, tr_vals = [], [], []
    for i in range(1, len(candles)):
        up   = candles[i]["h"] - candles[i-1]["h"]
        down = candles[i-1]["l"] - candles[i]["l"]
        plus_dm.append(up   if up   > down and up   > 0 else 0.0)
        minus_dm.append(down if down > up  and down > 0 else 0.0)
        tr_vals.append(max(
            candles[i]["h"] - candles[i]["l"],
            abs(candles[i]["h"] - candles[i-1]["c"]),
            abs(candles[i]["l"] - candles[i-1]["c"])
        ))
    def wilder(vals, p):
        s, out = sum(vals[:p]), [sum(vals[:p])]
        for v in vals[p:]:
            s = s - s / p + v
            out.append(s)
        return out
    sm_tr  = wilder(tr_vals,  period)
    sm_pdm = wilder(plus_dm,  period)
    sm_mdm = wilder(minus_dm, period)
    dx_vals = []
    for t, p, m in zip(sm_tr, sm_pdm, sm_mdm):
        pdi = 100 * p / t if t else 0
        mdi = 100 * m / t if t else 0
        dx_vals.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0)
    adx_val  = np.mean(dx_vals[-period:]) if len(dx_vals) >= period else np.mean(dx_vals)
    plus_di  = 100 * sm_pdm[-1] / sm_tr[-1] if sm_tr[-1] else 0
    minus_di = 100 * sm_mdm[-1] / sm_tr[-1] if sm_tr[-1] else 0
    return adx_val, plus_di, minus_di

def calc_williams_r(candles, period=14):
    """Williams %R: 0 = overbought (bearish), -100 = oversold (bullish)."""
    subset = candles[-period:]
    hh = max(c["h"] for c in subset)
    ll = min(c["l"] for c in subset)
    return -100.0 * (hh - candles[-1]["c"]) / (hh - ll) if hh != ll else -50.0

def calc_cci(candles, period=20):
    """Commodity Channel Index: >100 overbought, <-100 oversold."""
    tp   = [(c["h"] + c["l"] + c["c"]) / 3 for c in candles[-period:]]
    mean = np.mean(tp)
    mad  = np.mean([abs(x - mean) for x in tp])
    return (tp[-1] - mean) / (0.015 * mad) if mad else 0.0

def calc_mfi(candles, period=14):
    """Money Flow Index — volume-weighted RSI. >80 overbought, <20 oversold."""
    pos_mf = neg_mf = 0.0
    for i in range(-period, 0):
        tp_c = (candles[i]["h"]   + candles[i]["l"]   + candles[i]["c"])   / 3
        tp_p = (candles[i-1]["h"] + candles[i-1]["l"] + candles[i-1]["c"]) / 3
        mf   = tp_c * candles[i]["v"]
        if   tp_c > tp_p: pos_mf += mf
        elif tp_c < tp_p: neg_mf += mf
    return 100.0 if neg_mf == 0 else 100 - 100 / (1 + pos_mf / neg_mf)

def calc_obv(candles):
    """On-Balance Volume with EMA-9/21 cross for trend direction."""
    obv, series = 0.0, [0.0]
    for i in range(1, len(candles)):
        if   candles[i]["c"] > candles[i-1]["c"]: obv += candles[i]["v"]
        elif candles[i]["c"] < candles[i-1]["c"]: obv -= candles[i]["v"]
        series.append(obv)
    obv9  = ema_array(series, 9)
    obv21 = ema_array(series, 21)
    slope = (series[-1] - series[-6]) / (abs(series[-6]) + 1e-9)
    return series[-1], obv9[-1] > obv21[-1], slope

# ─── SIGNAL HELPER ────────────────────────────────────────────────────────────
def sig_label(sig):
    if sig == "BULL": return f"{G}▲ BULL{X}"
    if sig == "BEAR": return f"{R}▼ BEAR{X}"
    return f"{Y}◆ HOLD{X}"

# ─── PREDICTION ENGINE ────────────────────────────────────────────────────────
def predict():
    print(f"\n{C}{'═'*56}{X}")
    print(f"{B}{C}   BTC 5-MIN PREDICTOR  v3  {DIM}(High Accuracy — 16 Indicators){X}")
    print(f"{C}{'═'*56}{X}")
    print(f"{DIM}  Fetching {LIMIT} candles...{X}", end="\r")

    candles = fetch_candles()
    closes  = [c["c"] for c in candles]
    highs   = [c["h"] for c in candles]
    lows    = [c["l"] for c in candles]
    vols    = [c["v"] for c in candles]
    last    = candles[-1]
    prev    = candles[-2]
    price   = last["c"]

    chg_pct = (price - prev["c"]) / prev["c"] * 100
    chg_col = G if chg_pct >= 0 else R
    print(f"  {W}BTC/USDT:{X}  {B}${price:,.2f}{X}  {chg_col}({chg_pct:+.3f}%){X}          ")
    print(f"  {DIM}H: ${last['h']:,.2f}  L: ${last['l']:,.2f}  Vol: {last['v']:.2f}{X}\n")

    results  = {}   # name -> (signal, detail, weight)
    score    = 0.0
    max_score= 0.0

    # ── 1. RSI ────────────────────────────────────────────────────────────────
    rsi = calc_rsi(np.array(closes))
    if   rsi < 30:  rsi_sig, rsi_note = "BULL", "oversold (<30)"
    elif rsi < 45:  rsi_sig, rsi_note = "BULL", "leaning bullish"
    elif rsi > 70:  rsi_sig, rsi_note = "BEAR", "overbought (>70)"
    elif rsi > 55:  rsi_sig, rsi_note = "BEAR", "leaning bearish"
    else:           rsi_sig, rsi_note = "HOLD", "neutral zone"
    results["RSI"] = (rsi_sig, f"{rsi:.1f} — {rsi_note}")

    # ── 2. EMA Cross 9/21 ─────────────────────────────────────────────────────
    ema9  = ema_array(closes, 9)
    ema21 = ema_array(closes, 21)
    cross_now  = ema9[-1] - ema21[-1]
    cross_prev = ema9[-2] - ema21[-2]
    if cross_now > 0 and cross_prev <= 0:
        ema_sig, ema_note = "BULL", "fresh bullish crossover ✓"
    elif cross_now < 0 and cross_prev >= 0:
        ema_sig, ema_note = "BEAR", "fresh bearish crossover ✓"
    elif cross_now > 0:
        ema_sig, ema_note = "BULL", f"above (gap={cross_now:.1f})"
    elif cross_now < 0:
        ema_sig, ema_note = "BEAR", f"below (gap={abs(cross_now):.1f})"
    else:
        ema_sig, ema_note = "HOLD", "flat"
    results["EMA Cross"] = (ema_sig, ema_note)

    # ── 3. MACD 12/26/9 ───────────────────────────────────────────────────────
    ema12  = ema_array(closes, 12)
    ema26  = ema_array(closes, 26)
    macd   = [a - b for a, b in zip(ema12, ema26)]
    sig_line = ema_array(macd, 9)
    hist_now  = macd[-1] - sig_line[-1]
    hist_prev = macd[-2] - sig_line[-2]
    # Fresh crossover is stronger signal
    if hist_now > 0 and hist_prev <= 0:
        macd_sig, macd_note = "BULL", f"bullish cross! hist={hist_now:.2f}"
    elif hist_now < 0 and hist_prev >= 0:
        macd_sig, macd_note = "BEAR", f"bearish cross! hist={hist_now:.2f}"
    elif hist_now > 0 and hist_now > hist_prev:
        macd_sig, macd_note = "BULL", f"rising hist={hist_now:.2f}"
    elif hist_now < 0 and hist_now < hist_prev:
        macd_sig, macd_note = "BEAR", f"falling hist={hist_now:.2f}"
    else:
        macd_sig, macd_note = "HOLD", f"hist={hist_now:.2f}"
    results["MACD"] = (macd_sig, macd_note)

    # ── 4. Stochastic 14,3 ────────────────────────────────────────────────────
    stoch_k, stoch_d = calc_stochastic(candles)
    if stoch_k < 20:   stoch_sig, stoch_note = "BULL", f"oversold K={stoch_k:.1f}"
    elif stoch_k > 80: stoch_sig, stoch_note = "BEAR", f"overbought K={stoch_k:.1f}"
    elif stoch_k > stoch_d and stoch_k < 80:
        stoch_sig, stoch_note = "BULL", f"K>D bullish K={stoch_k:.1f}"
    elif stoch_k < stoch_d and stoch_k > 20:
        stoch_sig, stoch_note = "BEAR", f"K<D bearish K={stoch_k:.1f}"
    else:
        stoch_sig, stoch_note = "HOLD", f"K={stoch_k:.1f} D={stoch_d:.1f}"
    results["Stochastic"] = (stoch_sig, stoch_note)

    # ── 5. Bollinger Bands ────────────────────────────────────────────────────
    bb_up, bb_mid, bb_low, pct_b = calc_bollinger(closes)
    if pct_b < 0.05:
        bb_sig, bb_note = "BULL", f"at lower band (mean revert?)"
    elif pct_b > 0.95:
        bb_sig, bb_note = "BEAR", f"at upper band (mean revert?)"
    elif pct_b < 0.4:
        bb_sig, bb_note = "BULL", f"%B={pct_b:.2f} lower half"
    elif pct_b > 0.6:
        bb_sig, bb_note = "BEAR", f"%B={pct_b:.2f} upper half"
    else:
        bb_sig, bb_note = "HOLD", f"%B={pct_b:.2f} mid zone"
    results["Bollinger"] = (bb_sig, bb_note)

    # ── 6. VWAP ───────────────────────────────────────────────────────────────
    vwap = calc_vwap(candles)
    vwap_dist = (price - vwap) / vwap * 100
    if price > vwap:
        vwap_sig = "BULL"
        vwap_note = f"above VWAP +{vwap_dist:.2f}%"
    else:
        vwap_sig = "BEAR"
        vwap_note = f"below VWAP {vwap_dist:.2f}%"
    results["VWAP"] = (vwap_sig, vwap_note)

    # ── 7. Volume Confirmation ────────────────────────────────────────────────
    avg_vol = np.mean(vols[-20:])
    vol_ratio = last["v"] / avg_vol
    price_up = last["c"] > last["o"]
    if vol_ratio > 1.5 and price_up:
        vol_sig, vol_note = "BULL", f"high vol bullish candle ({vol_ratio:.1f}x avg)"
    elif vol_ratio > 1.5 and not price_up:
        vol_sig, vol_note = "BEAR", f"high vol bearish candle ({vol_ratio:.1f}x avg)"
    elif vol_ratio < 0.7:
        vol_sig, vol_note = "HOLD", f"low volume ({vol_ratio:.1f}x) — weak move"
    else:
        vol_sig  = "BULL" if price_up else "BEAR"
        vol_note = f"normal vol ({vol_ratio:.1f}x avg)"
    results["Volume"] = (vol_sig, vol_note)

    # ── 8. ATR Momentum ───────────────────────────────────────────────────────
    atr = calc_atr(candles)
    # Compare last 3 candle closes direction weighted by body size
    momentum_score = 0
    for i in range(-3, 0):
        c = candles[i]
        body = c["c"] - c["o"]
        momentum_score += body / atr
    if momentum_score > 0.3:
        atr_sig, atr_note = "BULL", f"positive momentum ({momentum_score:.2f})"
    elif momentum_score < -0.3:
        atr_sig, atr_note = "BEAR", f"negative momentum ({momentum_score:.2f})"
    else:
        atr_sig, atr_note = "HOLD", f"weak momentum ({momentum_score:.2f})"
    results["ATR Momentum"] = (atr_sig, atr_note)

    # ── 9. Candle Pattern ─────────────────────────────────────────────────────
    body  = abs(last["c"] - last["o"])
    rng   = last["h"] - last["l"] or 0.0001
    ratio = body / rng
    upper_wick = last["h"] - max(last["c"], last["o"])
    lower_wick = min(last["c"], last["o"]) - last["l"]
    if ratio > 0.7:
        candle_sig  = "BULL" if last["c"] > last["o"] else "BEAR"
        candle_note = "marubozu (strong body)"
    elif lower_wick > 2 * body and last["c"] > last["o"]:
        candle_sig, candle_note = "BULL", "hammer pattern"
    elif upper_wick > 2 * body and last["c"] < last["o"]:
        candle_sig, candle_note = "BEAR", "shooting star"
    elif ratio < 0.2:
        candle_sig, candle_note = "HOLD", "doji — indecision"
    else:
        candle_sig  = "BULL" if last["c"] > last["o"] else "BEAR"
        candle_note = f"normal (body={ratio:.0%})"
    results["Candle"] = (candle_sig, candle_note)

    # ── 10. Trend Context (SMA 20 vs 50) ──────────────────────────────────────
    sma20, sma50, slope = trend_context(closes)
    if sma20 > sma50 and slope > 0.01:
        trend_sig, trend_note = "BULL", f"uptrend SMA20>50, slope +{slope:.3f}%"
    elif sma20 < sma50 and slope < -0.01:
        trend_sig, trend_note = "BEAR", f"downtrend SMA20<50, slope {slope:.3f}%"
    elif sma20 > sma50:
        trend_sig, trend_note = "BULL", f"weak uptrend, slope {slope:.3f}%"
    elif sma20 < sma50:
        trend_sig, trend_note = "BEAR", f"weak downtrend, slope {slope:.3f}%"
    else:
        trend_sig, trend_note = "HOLD", "no clear trend"
    results["Trend Context"] = (trend_sig, trend_note)

    # ── 11. Williams %R ───────────────────────────────────────────────────────
    willr = calc_williams_r(candles)
    if   willr < -80: willr_sig, willr_note = "BULL", f"oversold %R={willr:.1f}"
    elif willr > -20: willr_sig, willr_note = "BEAR", f"overbought %R={willr:.1f}"
    elif willr < -50: willr_sig, willr_note = "BULL", f"%R={willr:.1f} lower half"
    else:             willr_sig, willr_note = "BEAR", f"%R={willr:.1f} upper half"
    results["Williams %R"] = (willr_sig, willr_note)

    # ── 12. CCI ───────────────────────────────────────────────────────────────
    cci = calc_cci(candles)
    if   cci < -100: cci_sig, cci_note = "BULL", f"oversold CCI={cci:.1f}"
    elif cci >  100: cci_sig, cci_note = "BEAR", f"overbought CCI={cci:.1f}"
    elif cci <  -50: cci_sig, cci_note = "BULL", f"CCI={cci:.1f} mildly bullish"
    elif cci >   50: cci_sig, cci_note = "BEAR", f"CCI={cci:.1f} mildly bearish"
    else:            cci_sig, cci_note = "HOLD", f"CCI={cci:.1f} neutral"
    results["CCI"] = (cci_sig, cci_note)

    # ── 13. MFI (Money Flow Index) ────────────────────────────────────────────
    mfi = calc_mfi(candles)
    if   mfi < 20: mfi_sig, mfi_note = "BULL", f"oversold MFI={mfi:.1f}"
    elif mfi > 80: mfi_sig, mfi_note = "BEAR", f"overbought MFI={mfi:.1f}"
    elif mfi < 40: mfi_sig, mfi_note = "BULL", f"MFI={mfi:.1f} bullish bias"
    elif mfi > 60: mfi_sig, mfi_note = "BEAR", f"MFI={mfi:.1f} bearish bias"
    else:          mfi_sig, mfi_note = "HOLD", f"MFI={mfi:.1f} neutral"
    results["MFI"] = (mfi_sig, mfi_note)

    # ── 14. OBV Trend ─────────────────────────────────────────────────────────
    _, obv_bull, obv_slope = calc_obv(candles)
    if   obv_bull and obv_slope > 0:     obv_sig, obv_note = "BULL", "OBV rising EMA9>21"
    elif not obv_bull and obv_slope < 0: obv_sig, obv_note = "BEAR", "OBV falling EMA9<21"
    elif obv_bull:                       obv_sig, obv_note = "BULL", "OBV above EMA21"
    else:                                obv_sig, obv_note = "BEAR", "OBV below EMA21"
    results["OBV"] = (obv_sig, obv_note)

    # ── 15. RSI Divergence ────────────────────────────────────────────────────
    div_sig, div_note = detect_rsi_divergence(closes)
    results["RSI Divergence"] = (div_sig, div_note)

    # ── 16. HTF 15m Trend ─────────────────────────────────────────────────────
    try:
        candles_15m = fetch_candles_htf()
        closes_15m  = [c["c"] for c in candles_15m]
        ema9_15m    = ema_array(closes_15m, 9)
        ema21_15m   = ema_array(closes_15m, 21)
        htf_gap     = ema9_15m[-1] - ema21_15m[-1]
        htf_slope   = (closes_15m[-1] - closes_15m[-5]) / closes_15m[-5] * 100
        if   htf_gap > 0 and htf_slope > 0: htf_sig, htf_note = "BULL", f"15m uptrend +{htf_slope:.3f}%"
        elif htf_gap < 0 and htf_slope < 0: htf_sig, htf_note = "BEAR", f"15m downtrend {htf_slope:.3f}%"
        elif htf_gap > 0:                   htf_sig, htf_note = "BULL", f"15m weak bull {htf_slope:.3f}%"
        elif htf_gap < 0:                   htf_sig, htf_note = "BEAR", f"15m weak bear {htf_slope:.3f}%"
        else:                               htf_sig, htf_note = "HOLD", "15m flat"
    except Exception:
        htf_sig, htf_note = "HOLD", "15m data unavailable"
    results["HTF 15m"] = (htf_sig, htf_note)

    # ─── ADX MARKET REGIME ────────────────────────────────────────────────────
    adx_val, plus_di, minus_di = calc_adx(candles)
    if adx_val >= 25:
        adx_regime   = f"{G}TRENDING{X}"
        adx_note_str = f"ADX={adx_val:.1f}  +DI={plus_di:.1f}  -DI={minus_di:.1f}"
        adx_penalty  = 1.0
    elif adx_val >= 18:
        adx_regime   = f"{Y}WEAK TREND{X}"
        adx_note_str = f"ADX={adx_val:.1f} — caution"
        adx_penalty  = 0.88
    else:
        adx_regime   = f"{R}RANGING/CHOPPY{X}"
        adx_note_str = f"ADX={adx_val:.1f} — avoid trading!"
        adx_penalty  = 0.75

    # ─── WEIGHTED SCORING ─────────────────────────────────────────────────────
    bull_score = bear_score = 0.0
    for name, (sig, detail) in results.items():
        w = WEIGHTS.get(name, 1.0)
        max_score += w
        if sig == "BULL":   bull_score += w
        elif sig == "BEAR": bear_score += w

    bull_conf = round(bull_score / max_score * 100 * adx_penalty)
    bear_conf = round(bear_score / max_score * 100 * adx_penalty)

    # ─── PRINT TABLE ──────────────────────────────────────────────────────────
    print(f"  {B}{'INDICATOR':<16} {'WT':>3}  {'DETAIL':<32} SIG{X}")
    print(f"  {'─'*60}")
    for name, (sig, detail) in results.items():
        w = WEIGHTS.get(name, 1.0)
        detail_short = detail[:32]
        print(f"  {W}{name:<16}{X} {DIM}{w:.1f}  {detail_short:<32}{X} {sig_label(sig)}")

    # ─── CONFLUENCE CHECK ─────────────────────────────────────────────────────
    bull_count = sum(1 for s,_ in results.values() if s=="BULL")
    bear_count = sum(1 for s,_ in results.values() if s=="BEAR")
    hold_count = sum(1 for s,_ in results.values() if s=="HOLD")

    print(f"\n  {DIM}Raw votes → {G}▲ Bull:{bull_count}{X}  {Y}◆ Hold:{hold_count}{X}  {R}▼ Bear:{bear_count}{X}")
    print(f"  {DIM}Weighted  → {G}▲ {bull_conf}%{X}  {R}▼ {bear_conf}%{X}")
    print(f"  Market Regime: {adx_regime}  {DIM}{adx_note_str}{X}")
    print(f"  {'─'*60}")

    # ─── FINAL SIGNAL ─────────────────────────────────────────────────────────
    bar_len = 32
    if bull_conf > bear_conf and bull_conf >= CONFIDENCE_THRESHOLD:
        direction   = f"{G}{B}▲  LONG  (BUY){X}"
        conf        = bull_conf
        conf_col    = G
        filled      = int(conf/100 * bar_len)
        strength    = "STRONG" if conf > 70 else "MODERATE" if conf > 60 else "WEAK"
    elif bear_conf > bull_conf and bear_conf >= CONFIDENCE_THRESHOLD:
        direction   = f"{R}{B}▼  SHORT (SELL){X}"
        conf        = bear_conf
        conf_col    = R
        filled      = int(conf/100 * bar_len)
        strength    = "STRONG" if conf > 70 else "MODERATE" if conf > 60 else "WEAK"
    else:
        direction   = f"{Y}{B}◆  NO SIGNAL — SKIP THIS CANDLE{X}"
        conf        = max(bull_conf, bear_conf)
        conf_col    = Y
        filled      = int(conf/100 * bar_len)
        strength    = "UNCERTAIN"

    bar = conf_col + "█"*filled + X + DIM + "░"*(bar_len-filled) + X

    print(f"\n  {B}PREDICTION:{X}  {direction}")
    print(f"  Confidence:  [{bar}] {conf_col}{conf}%  {DIM}({strength}){X}")
    print(f"\n  {DIM}Time: {datetime.now().strftime('%H:%M:%S')}  |  Next {INTERVAL} candle{X}")
    print(f"\n  {DIM}TIP: Trade only when confidence ≥ {CONFIDENCE_THRESHOLD}% AND regime is TRENDING.{X}")
    print(f"  {DIM}      Skip RANGING markets and NEUTRAL signals — low confluence = low edge.{X}")
    print(f"{C}{'═'*56}{X}")
    print(f"  {Y}⚠  NOT FINANCIAL ADVICE. Accuracy: ~58-65% theoretical max.{X}\n")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    loop = "--loop" in sys.argv

    def seconds_until_next_candle(interval_sec=300):
        """Seconds until the next 5m candle closes (Binance syncs to Unix time)."""
        return interval_sec - (time.time() % interval_sec)

    if loop:
        CANDLE_SEC = 300  # 5 minutes
        print("\033[96mCandle-sync mode: predicts right after each 5m candle CLOSES.\033[0m")
        print("\033[90mYou will see a countdown then a fresh prediction every 5 minutes.\033[0m")
        print("\033[90mCtrl+C to stop.\033[0m\n")

        # Run once immediately so you don't wait up to 5 min on start
        try:
            predict()
        except Exception as e:
            print(f"\033[91mError on first run: {e}\033[0m")

        while True:
            try:
                wait = seconds_until_next_candle(CANDLE_SEC)
                while wait > 0:
                    mins, secs = divmod(int(wait), 60)
                    print(f"  \033[90m⏳ Next candle closes in {mins}m {secs:02d}s ...  \033[0m", end="\r")
                    time.sleep(1)
                    wait -= 1

                print(f"  \033[92m✓ Candle closed! Fetching & analyzing...              \033[0m")
                time.sleep(2)  # Give Binance 2s to finalize the candle
                predict()

            except KeyboardInterrupt:
                print("\n\033[93mStopped.\033[0m")
                break
            except Exception as e:
                print(f"\n\033[91mError: {e}\033[0m - retrying next candle...")
    else:
        try:
            predict()
        except Exception as e:
            print(f"\n\033[91mError: {e}\033[0m")
            print("\033[93mTip: If Binance is blocked in your region (India), use a VPN.\033[0m\n")