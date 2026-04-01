"""
BTC 5-Minute Direction Predictor
=================================
Uses live Binance data + 5 technical indicators to predict
the next 5-minute candle direction.

Install requirements:
    pip install requests pandas numpy

Run:
    python btc_predictor.py
    python btc_predictor.py --loop   (refreshes every 60s)
"""

import requests
import numpy as np
import sys
import time
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SYMBOL   = "BTCUSDT"
INTERVAL = "5m"
LIMIT    = 50

# Try multiple endpoints (some may be blocked by region)
ENDPOINTS = [
    f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
    f"https://api1.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
    f"https://api2.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
    f"https://api3.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}",
]

# ─── COLORS ───────────────────────────────────────────────────────────────────
G  = "\033[92m"   # green
R  = "\033[91m"   # red
Y  = "\033[93m"   # yellow
C  = "\033[96m"   # cyan
W  = "\033[97m"   # white
DIM= "\033[90m"   # dim
B  = "\033[1m"    # bold
X  = "\033[0m"    # reset

# ─── FETCH DATA ───────────────────────────────────────────────────────────────
def fetch_candles():
    for url in ENDPOINTS:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                candles = [{
                    "o": float(c[1]),
                    "h": float(c[2]),
                    "l": float(c[3]),
                    "c": float(c[4]),
                    "v": float(c[5]),
                } for c in data]
                return candles
        except Exception:
            continue
    raise ConnectionError("❌ Could not reach Binance. Check internet/VPN.")

# ─── INDICATORS ───────────────────────────────────────────────────────────────
def ema_array(values, period):
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result

def calc_rsi(closes, period=14):
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_g  = np.mean(gains[:period])
    avg_l  = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_l)

def calc_vwap(candles):
    tp_vol = sum(((c["h"] + c["l"] + c["c"]) / 3) * c["v"] for c in candles)
    vol    = sum(c["v"] for c in candles)
    return tp_vol / vol

def signal_label(sig):
    if sig == "BULL": return f"{G}▲ BULL{X}"
    if sig == "BEAR": return f"{R}▼ BEAR{X}"
    return f"{Y}◆ HOLD{X}"

# ─── MAIN PREDICTION ──────────────────────────────────────────────────────────
def predict():
    print(f"\n{C}{'─'*52}{X}")
    print(f"{B}{C}  BTC 5-MIN PREDICTOR  {DIM}powered by Binance{X}")
    print(f"{C}{'─'*52}{X}")
    print(f"{DIM}  Fetching data...{X}", end="\r")

    candles = fetch_candles()
    closes  = [c["c"] for c in candles]
    last    = candles[-1]
    prev    = candles[-2]

    # Price info
    price   = last["c"]
    chg_pct = (price - prev["c"]) / prev["c"] * 100
    chg_col = G if chg_pct >= 0 else R
    print(f"  {W}BTC/USDT:{X}  {B}${price:,.2f}{X}  {chg_col}({chg_pct:+.3f}%){X}          ")
    print(f"  {DIM}H: ${last['h']:,.2f}  L: ${last['l']:,.2f}  Vol: {last['v']:.2f} BTC{X}")
    print()

    signals = {}

    # 1. RSI
    rsi = calc_rsi(np.array(closes))
    if rsi < 35:   rsi_sig = "BULL"
    elif rsi > 65: rsi_sig = "BEAR"
    else:          rsi_sig = "HOLD"
    signals["RSI(14)"] = (rsi_sig, f"{rsi:.1f}")

    # 2. EMA Cross 9/21
    ema9  = ema_array(closes, 9)[-1]
    ema21 = ema_array(closes, 21)[-1]
    ema_sig = "BULL" if ema9 > ema21 else "BEAR" if ema9 < ema21 else "HOLD"
    signals["EMA 9/21"] = (ema_sig, f"{ema9:,.1f} / {ema21:,.1f}")

    # 3. MACD 12/26/9
    ema12  = ema_array(closes, 12)
    ema26  = ema_array(closes, 26)
    macd   = [a - b for a, b in zip(ema12, ema26)]
    signal = ema_array(macd, 9)
    hist   = macd[-1] - signal[-1]
    macd_sig = "BULL" if hist > 0 else "BEAR" if hist < 0 else "HOLD"
    signals["MACD"] = (macd_sig, f"hist={hist:.2f}")

    # 4. Price vs VWAP
    vwap    = calc_vwap(candles)
    vwap_sig = "BULL" if price > vwap else "BEAR" if price < vwap else "HOLD"
    signals["VWAP"] = (vwap_sig, f"vwap=${vwap:,.2f}")

    # 5. Candle body ratio
    body  = abs(last["c"] - last["o"])
    rng   = last["h"] - last["l"] or 0.0001
    ratio = body / rng
    if ratio > 0.6:
        candle_sig = "BULL" if last["c"] > last["o"] else "BEAR"
        pattern = "Strong candle"
    else:
        candle_sig = "HOLD"
        pattern = "Doji/indecision"
    signals["Candle"] = (candle_sig, pattern)

    # ── Print indicator table ──
    print(f"  {B}{'INDICATOR':<14} {'VALUE':<22} SIGNAL{X}")
    print(f"  {'─'*46}")
    bull = bear = hold = 0
    for name, (sig, val) in signals.items():
        if sig == "BULL": bull += 1
        elif sig == "BEAR": bear += 1
        else: hold += 1
        print(f"  {W}{name:<14}{X} {DIM}{val:<22}{X} {signal_label(sig)}")

    # ── Final verdict ──
    print(f"\n  {DIM}Votes → {G}▲ Bull: {bull}{X}  {Y}◆ Hold: {hold}{X}  {R}▼ Bear: {bear}{X}")
    print(f"  {'─'*46}")

    total = bull + bear + hold * 0.5
    if bull > bear:
        direction = f"{G}{B}▲  LONG  (BUY){X}"
        conf = round(bull / total * 100)
        conf_col = G
    elif bear > bull:
        direction = f"{R}{B}▼  SHORT (SELL){X}"
        conf = round(bear / total * 100)
        conf_col = R
    else:
        direction = f"{Y}{B}◆  NEUTRAL — SKIP{X}"
        conf = 50
        conf_col = Y

    bar_len = 30
    filled  = int(conf / 100 * bar_len)
    bar     = conf_col + "█" * filled + X + DIM + "░" * (bar_len - filled) + X

    print(f"\n  {B}PREDICTION:{X}  {direction}")
    print(f"  Confidence:   [{bar}] {conf_col}{conf}%{X}")
    print(f"\n  {DIM}Time: {datetime.now().strftime('%H:%M:%S')}  —  Next candle ~{INTERVAL}{X}")
    print(f"{C}{'─'*52}{X}\n")

    print(f"  {Y}⚠  NOT FINANCIAL ADVICE. Use at your own risk.{X}")
    print(f"  {DIM}Accuracy: ~55-60% at best. Markets are random.{X}\n")

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    loop = "--loop" in sys.argv

    if loop:
        print(f"{C}Running in loop mode — refreshes every 60 seconds. Ctrl+C to stop.{X}")
        while True:
            try:
                predict()
            except Exception as e:
                print(f"{R}Error: {e}{X}")
            time.sleep(60)
    else:
        try:
            predict()
        except Exception as e:
            print(f"\n{R}Error: {e}{X}")
            print(f"{Y}Tip: If Binance is blocked in your region (India), use a VPN.{X}\n")
