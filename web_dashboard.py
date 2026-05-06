from datetime import datetime

import numpy as np
import requests
from flask import Flask, jsonify, render_template

import btc_predictor_v2 as core

app = Flask(__name__)


def _fetch_candles_with_time():
    """Fetch candles with timestamp, reusing predictor endpoints."""
    for url in core.ENDPOINTS:
        try:
            response = requests.get(url, timeout=8)
            if response.status_code == 200:
                data = response.json()
                candles = []
                for item in data:
                    candles.append(
                        {
                            "ts": int(item[0]),
                            "o": float(item[1]),
                            "h": float(item[2]),
                            "l": float(item[3]),
                            "c": float(item[4]),
                            "v": float(item[5]),
                        }
                    )
                return candles
        except Exception:
            continue
    raise ConnectionError("Cannot reach Binance endpoints")


def _build_signals(candles):
    closes = [c["c"] for c in candles]
    vols = [c["v"] for c in candles]
    last = candles[-1]

    results = {}

    rsi = core.calc_rsi(np.array(closes))
    if rsi < 30:
        rsi_sig, rsi_note = "BULL", "oversold (<30)"
    elif rsi < 45:
        rsi_sig, rsi_note = "BULL", "leaning bullish"
    elif rsi > 70:
        rsi_sig, rsi_note = "BEAR", "overbought (>70)"
    elif rsi > 55:
        rsi_sig, rsi_note = "BEAR", "leaning bearish"
    else:
        rsi_sig, rsi_note = "HOLD", "neutral zone"
    results["RSI"] = {"signal": rsi_sig, "detail": f"{rsi:.1f} - {rsi_note}"}

    ema9 = core.ema_array(closes, 9)
    ema21 = core.ema_array(closes, 21)
    cross_now = ema9[-1] - ema21[-1]
    cross_prev = ema9[-2] - ema21[-2]
    if cross_now > 0 and cross_prev <= 0:
        ema_sig, ema_note = "BULL", "fresh bullish crossover"
    elif cross_now < 0 and cross_prev >= 0:
        ema_sig, ema_note = "BEAR", "fresh bearish crossover"
    elif cross_now > 0:
        ema_sig, ema_note = "BULL", f"above (gap={cross_now:.1f})"
    elif cross_now < 0:
        ema_sig, ema_note = "BEAR", f"below (gap={abs(cross_now):.1f})"
    else:
        ema_sig, ema_note = "HOLD", "flat"
    results["EMA Cross"] = {"signal": ema_sig, "detail": ema_note}

    ema12 = core.ema_array(closes, 12)
    ema26 = core.ema_array(closes, 26)
    macd = [a - b for a, b in zip(ema12, ema26)]
    sig_line = core.ema_array(macd, 9)
    hist_now = macd[-1] - sig_line[-1]
    hist_prev = macd[-2] - sig_line[-2]
    if hist_now > 0 and hist_prev <= 0:
        macd_sig, macd_note = "BULL", f"bullish cross (hist={hist_now:.2f})"
    elif hist_now < 0 and hist_prev >= 0:
        macd_sig, macd_note = "BEAR", f"bearish cross (hist={hist_now:.2f})"
    elif hist_now > 0 and hist_now > hist_prev:
        macd_sig, macd_note = "BULL", f"rising hist={hist_now:.2f}"
    elif hist_now < 0 and hist_now < hist_prev:
        macd_sig, macd_note = "BEAR", f"falling hist={hist_now:.2f}"
    else:
        macd_sig, macd_note = "HOLD", f"hist={hist_now:.2f}"
    results["MACD"] = {"signal": macd_sig, "detail": macd_note}

    stoch_k, stoch_d = core.calc_stochastic(candles)
    if stoch_k < 20:
        stoch_sig, stoch_note = "BULL", f"oversold K={stoch_k:.1f}"
    elif stoch_k > 80:
        stoch_sig, stoch_note = "BEAR", f"overbought K={stoch_k:.1f}"
    elif stoch_k > stoch_d and stoch_k < 80:
        stoch_sig, stoch_note = "BULL", f"K>D bullish K={stoch_k:.1f}"
    elif stoch_k < stoch_d and stoch_k > 20:
        stoch_sig, stoch_note = "BEAR", f"K<D bearish K={stoch_k:.1f}"
    else:
        stoch_sig, stoch_note = "HOLD", f"K={stoch_k:.1f} D={stoch_d:.1f}"
    results["Stochastic"] = {"signal": stoch_sig, "detail": stoch_note}

    _, _, _, pct_b = core.calc_bollinger(closes)
    if pct_b < 0.05:
        bb_sig, bb_note = "BULL", "at lower band"
    elif pct_b > 0.95:
        bb_sig, bb_note = "BEAR", "at upper band"
    elif pct_b < 0.4:
        bb_sig, bb_note = "BULL", f"%B={pct_b:.2f} lower half"
    elif pct_b > 0.6:
        bb_sig, bb_note = "BEAR", f"%B={pct_b:.2f} upper half"
    else:
        bb_sig, bb_note = "HOLD", f"%B={pct_b:.2f} mid zone"
    results["Bollinger"] = {"signal": bb_sig, "detail": bb_note}

    vwap = core.calc_vwap(candles)
    vwap_dist = (last["c"] - vwap) / vwap * 100
    if last["c"] > vwap:
        vwap_sig, vwap_note = "BULL", f"above VWAP +{vwap_dist:.2f}%"
    else:
        vwap_sig, vwap_note = "BEAR", f"below VWAP {vwap_dist:.2f}%"
    results["VWAP"] = {"signal": vwap_sig, "detail": vwap_note}

    avg_vol = np.mean(vols[-20:])
    vol_ratio = last["v"] / avg_vol
    price_up = last["c"] > last["o"]
    if vol_ratio > 1.5 and price_up:
        vol_sig, vol_note = "BULL", f"high vol bullish ({vol_ratio:.1f}x)"
    elif vol_ratio > 1.5 and not price_up:
        vol_sig, vol_note = "BEAR", f"high vol bearish ({vol_ratio:.1f}x)"
    elif vol_ratio < 0.7:
        vol_sig, vol_note = "HOLD", f"low volume ({vol_ratio:.1f}x)"
    else:
        vol_sig = "BULL" if price_up else "BEAR"
        vol_note = f"normal vol ({vol_ratio:.1f}x)"
    results["Volume"] = {"signal": vol_sig, "detail": vol_note}

    atr = core.calc_atr(candles)
    momentum_score = 0.0
    for i in range(-3, 0):
        body = candles[i]["c"] - candles[i]["o"]
        momentum_score += body / atr
    if momentum_score > 0.3:
        atr_sig, atr_note = "BULL", f"positive momentum ({momentum_score:.2f})"
    elif momentum_score < -0.3:
        atr_sig, atr_note = "BEAR", f"negative momentum ({momentum_score:.2f})"
    else:
        atr_sig, atr_note = "HOLD", f"weak momentum ({momentum_score:.2f})"
    results["ATR Momentum"] = {"signal": atr_sig, "detail": atr_note}

    sma20, sma50, slope = core.trend_context(closes)
    if sma20 > sma50 and slope > 0.01:
        trend_sig, trend_note = "BULL", f"uptrend slope +{slope:.3f}%"
    elif sma20 < sma50 and slope < -0.01:
        trend_sig, trend_note = "BEAR", f"downtrend slope {slope:.3f}%"
    elif sma20 > sma50:
        trend_sig, trend_note = "BULL", f"weak uptrend slope {slope:.3f}%"
    elif sma20 < sma50:
        trend_sig, trend_note = "BEAR", f"weak downtrend slope {slope:.3f}%"
    else:
        trend_sig, trend_note = "HOLD", "no clear trend"
    results["Trend Context"] = {"signal": trend_sig, "detail": trend_note}

    willr = core.calc_williams_r(candles)
    if willr < -80:
        wr_sig, wr_note = "BULL", f"oversold %R={willr:.1f}"
    elif willr > -20:
        wr_sig, wr_note = "BEAR", f"overbought %R={willr:.1f}"
    elif willr < -50:
        wr_sig, wr_note = "BULL", f"%R={willr:.1f} lower half"
    else:
        wr_sig, wr_note = "BEAR", f"%R={willr:.1f} upper half"
    results["Williams %R"] = {"signal": wr_sig, "detail": wr_note}

    cci = core.calc_cci(candles)
    if cci < -100:
        cci_sig, cci_note = "BULL", f"oversold CCI={cci:.1f}"
    elif cci > 100:
        cci_sig, cci_note = "BEAR", f"overbought CCI={cci:.1f}"
    elif cci < -50:
        cci_sig, cci_note = "BULL", f"CCI={cci:.1f} mildly bullish"
    elif cci > 50:
        cci_sig, cci_note = "BEAR", f"CCI={cci:.1f} mildly bearish"
    else:
        cci_sig, cci_note = "HOLD", f"CCI={cci:.1f} neutral"
    results["CCI"] = {"signal": cci_sig, "detail": cci_note}

    mfi = core.calc_mfi(candles)
    if mfi < 20:
        mfi_sig, mfi_note = "BULL", f"oversold MFI={mfi:.1f}"
    elif mfi > 80:
        mfi_sig, mfi_note = "BEAR", f"overbought MFI={mfi:.1f}"
    elif mfi < 40:
        mfi_sig, mfi_note = "BULL", f"MFI={mfi:.1f} bullish bias"
    elif mfi > 60:
        mfi_sig, mfi_note = "BEAR", f"MFI={mfi:.1f} bearish bias"
    else:
        mfi_sig, mfi_note = "HOLD", f"MFI={mfi:.1f} neutral"
    results["MFI"] = {"signal": mfi_sig, "detail": mfi_note}

    _, obv_bull, obv_slope = core.calc_obv(candles)
    if obv_bull and obv_slope > 0:
        obv_sig, obv_note = "BULL", "OBV rising EMA9>21"
    elif not obv_bull and obv_slope < 0:
        obv_sig, obv_note = "BEAR", "OBV falling EMA9<21"
    elif obv_bull:
        obv_sig, obv_note = "BULL", "OBV above EMA21"
    else:
        obv_sig, obv_note = "BEAR", "OBV below EMA21"
    results["OBV"] = {"signal": obv_sig, "detail": obv_note}

    div_sig, div_note = core.detect_rsi_divergence(closes)
    results["RSI Divergence"] = {"signal": div_sig, "detail": div_note}

    try:
        candles_15m = core.fetch_candles_htf()
        closes_15m = [c["c"] for c in candles_15m]
        ema9_15m = core.ema_array(closes_15m, 9)
        ema21_15m = core.ema_array(closes_15m, 21)
        htf_gap = ema9_15m[-1] - ema21_15m[-1]
        htf_slope = (closes_15m[-1] - closes_15m[-5]) / closes_15m[-5] * 100
        if htf_gap > 0 and htf_slope > 0:
            htf_sig, htf_note = "BULL", f"15m uptrend +{htf_slope:.3f}%"
        elif htf_gap < 0 and htf_slope < 0:
            htf_sig, htf_note = "BEAR", f"15m downtrend {htf_slope:.3f}%"
        elif htf_gap > 0:
            htf_sig, htf_note = "BULL", f"15m weak bull {htf_slope:.3f}%"
        elif htf_gap < 0:
            htf_sig, htf_note = "BEAR", f"15m weak bear {htf_slope:.3f}%"
        else:
            htf_sig, htf_note = "HOLD", "15m flat"
    except Exception:
        htf_sig, htf_note = "HOLD", "15m data unavailable"
    results["HTF 15m"] = {"signal": htf_sig, "detail": htf_note}

    return results


def _score_signals(results):
    max_score = 0.0
    bull_score = 0.0
    bear_score = 0.0

    for name, payload in results.items():
        weight = core.WEIGHTS.get(name, 1.0)
        max_score += weight
        if payload["signal"] == "BULL":
            bull_score += weight
        elif payload["signal"] == "BEAR":
            bear_score += weight

    return bull_score, bear_score, max_score


def build_snapshot():
    candles = _fetch_candles_with_time()
    closes = [c["c"] for c in candles]
    last = candles[-1]
    prev = candles[-2]

    results = _build_signals(candles)
    adx_val, plus_di, minus_di = core.calc_adx(candles)

    if adx_val >= 25:
        regime = "TRENDING"
        adx_penalty = 1.0
    elif adx_val >= 18:
        regime = "WEAK_TREND"
        adx_penalty = 0.88
    else:
        regime = "RANGING"
        adx_penalty = 0.75

    bull_score, bear_score, max_score = _score_signals(results)
    bull_conf = round(bull_score / max_score * 100 * adx_penalty)
    bear_conf = round(bear_score / max_score * 100 * adx_penalty)

    if bull_conf > bear_conf and bull_conf >= core.CONFIDENCE_THRESHOLD:
        decision = "LONG"
        confidence = bull_conf
    elif bear_conf > bull_conf and bear_conf >= core.CONFIDENCE_THRESHOLD:
        decision = "SHORT"
        confidence = bear_conf
    else:
        decision = "SKIP"
        confidence = max(bull_conf, bear_conf)

    votes = {"bull": 0, "bear": 0, "hold": 0}
    for item in results.values():
        votes[item["signal"].lower()] += 1

    return {
        "symbol": core.SYMBOL,
        "interval": core.INTERVAL,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "price": {
            "current": last["c"],
            "change_pct": (last["c"] - prev["c"]) / prev["c"] * 100,
            "high": last["h"],
            "low": last["l"],
            "volume": last["v"],
        },
        "signal": {
            "decision": decision,
            "confidence": confidence,
            "bull_confidence": bull_conf,
            "bear_confidence": bear_conf,
            "threshold": core.CONFIDENCE_THRESHOLD,
            "regime": regime,
            "adx": round(adx_val, 2),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
            "votes": votes,
        },
        "indicators": results,
        "series": {
            "labels": [c["ts"] for c in candles[-120:]],
            "close": closes[-120:],
        },
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/predict")
def api_predict():
    try:
        return jsonify({"ok": True, "data": build_snapshot()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
