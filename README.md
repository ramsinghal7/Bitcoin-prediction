# BTC 5-Minute Direction Predictor

A lightweight Python project for short-term BTC/USDT direction analysis using Binance market data and technical indicators.

This repository includes two versions:
- **btc_predictor.py**: Simple, fast, 5-indicator baseline predictor.
- **btc_predictor_v2.py**: Advanced, weighted 16-indicator predictor with ADX regime filtering and 15m higher-timeframe confirmation.

## Disclaimer

This project is for educational and research purposes only.
It is **not financial advice**. Trading crypto is risky and you can lose money.

---

## Features

### Version 1 (btc_predictor.py)
- Pulls recent 5-minute BTC/USDT candles from Binance
- Uses 5 indicators:
  - RSI(14)
  - EMA 9/21 cross
  - MACD histogram
  - VWAP position
  - Candle body strength
- Vote-based final signal: LONG / SHORT / NEUTRAL
- Optional loop mode (refresh every 60 seconds)

### Version 2 (btc_predictor_v2.py)
- Pulls deeper 5-minute candle history for stronger calculations
- Uses **16 weighted signals**, including:
  - RSI + RSI Divergence
  - EMA cross
  - MACD
  - Stochastic
  - Williams %R
  - CCI
  - MFI
  - Bollinger bands
  - VWAP
  - OBV trend
  - Volume confirmation
  - ATR momentum
  - Candle pattern context
  - Trend context (SMA 20/50)
  - HTF 15m trend confirmation
- ADX-based market regime filter (Trending / Weak Trend / Ranging)
- Confidence threshold gating (default: 58%)
- Candle-synced loop mode (predicts after each 5-minute candle close)

---

## Requirements

- Python 3.9+
- pip
- Internet access to Binance API endpoints

Install dependencies:

```bash
pip install requests numpy
```

---

## How to Run

### 1) Baseline Predictor

Single run:

```bash
python btc_predictor.py
```

Loop mode (updates every 60s):

```bash
python btc_predictor.py --loop
```

### 2) Advanced Predictor

Single run:

```bash
python btc_predictor_v2.py
```

Candle-synced loop mode:

```bash
python btc_predictor_v2.py --loop
```

---

## Output Interpretation

Both scripts print:
- Current BTC/USDT stats
- Indicator-level signals (Bull / Bear / Hold)
- Final directional suggestion
- Confidence estimate

General idea:
- Higher confidence + strong indicator agreement may indicate better confluence
- Low confidence / neutral output usually means no clear edge

For v2, best practice in the script itself is to prefer signals when:
- Confidence >= 58%
- Market regime is TRENDING (based on ADX)

---

## Quick Comparison

| Aspect | btc_predictor.py | btc_predictor_v2.py |
|---|---|---|
| Complexity | Beginner-friendly | Advanced |
| Indicator count | 5 | 16 (weighted) |
| Trend regime filter | No | Yes (ADX) |
| Higher timeframe check | No | Yes (15m) |
| Loop behavior | Every 60s | Candle-synced (5m close) |
| Best for | Fast signal checks | More robust confluence analysis |

---

## Troubleshooting

- **Binance blocked in your region?** Use a VPN if required by local restrictions.
- **No signal in v2?** This can be normal when confidence is below threshold or market is ranging.
- **Connection errors?** Retry after a moment; script already tries multiple Binance endpoints.

---

## Project Structure

```text
.
├── btc_predictor.py
├── btc_predictor_v2.py
└── README.md
```

---

## Notes for GitHub

Suggested repository tags:
- python
- crypto
- bitcoin
- technical-analysis
- trading-bot
- binance
- algorithmic-trading

By:
RAM SINGHAL

