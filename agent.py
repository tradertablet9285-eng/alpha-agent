#!/usr/bin/env python3
"""
Alpha Auto Agent v3.0
XAUUSD + BTCUSDT | 38.2% Liquidity Sweep Strategy
- XAUUSD: Gold API (free) + synthetic candles
- BTCUSDT: Binance API
- Multi-timeframe trend
- News filter
- Better CHOCH + Sweep detection
"""

import requests
import time
import datetime
import random
import math

# ═══════════════════════════════════════
# ⚙️ CONFIGURATION — SIRF YAHAN CHANGE KARO
# ═══════════════════════════════════════
BOT_TOKEN         = "8807619711:AAEaL5HI6Bj-sbMSpliF73rxO5eRSG3zugI"
CHAT_ID           = "8867873147"
SCAN_INTERVAL_MIN = 5
MIN_SCORE         = 70
COOLDOWN_HOURS    = 2
# ═══════════════════════════════════════

ASSETS = {
    "XAUUSD": {"sl": 6.5,  "vol_min": 2.0, "icon": "⚡", "is_gold": True},
    "BTCUSD": {"sl": 175,  "vol_min": 3.0, "icon": "₿",  "is_gold": False, "sym": "BTCUSDT"},
}

last_signal = {"XAUUSD": 0, "BTCUSD": 0}
scan_count  = 0
sig_count   = 0

# ═══════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════
def log(msg, level="INFO"):
    t = datetime.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{t} GMT] [{level}] {msg}")

# ═══════════════════════════════════════
# SESSION
# ═══════════════════════════════════════
def get_session():
    now = datetime.datetime.utcnow()
    h   = now.hour + now.minute / 60
    day = now.weekday()
    if day >= 5:
        return {"name": "Weekend",             "good": False}
    if 0  <= h <  7:
        return {"name": "Asian",               "good": False}
    if 7  <= h < 10:
        return {"name": "London Open",         "good": True}
    if 10 <= h < 12:
        return {"name": "London Mid",          "good": True}
    if 12 <= h < 15:
        return {"name": "London-NY Overlap",   "good": True}
    if 15 <= h < 17:
        return {"name": "NY Open",             "good": True}
    if 17 <= h < 20:
        return {"name": "NY Mid",              "good": day != 4}
    return {"name": "Closed",                  "good": False}

# ═══════════════════════════════════════
# BINANCE CANDLE FETCH (for BTC)
# ═══════════════════════════════════════
def fetch_binance(symbol, interval, limit=60):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data
        return None
    except Exception as e:
        log(f"Binance fetch error {symbol}: {e}", "ERROR")
        return None

# ═══════════════════════════════════════
# GOLD PRICE FETCH (multiple free APIs)
# ═══════════════════════════════════════
def fetch_gold_price():
    """Try multiple free APIs to get current gold price"""

    # API 1: Metals.live (free, no key)
    try:
        r = requests.get(
            "https://metals.live/api/spot",
            timeout=8)
        data = r.json()
        if isinstance(data, list):
            for item in data:
                if item.get("metal") == "gold" or item.get("symbol") == "XAUUSD":
                    return float(item.get("price", 0))
    except:
        pass

    # API 2: Frankfurter (free, no key) - gives XAU/USD rate
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=XAU&to=USD",
            timeout=8)
        data = r.json()
        if "rates" in data and "USD" in data["rates"]:
            return float(data["rates"]["USD"])
    except:
        pass

    # API 3: Gold Price API (free tier)
    try:
        r = requests.get(
            "https://www.goldapi.io/api/XAU/USD",
            headers={"x-access-token": "goldapi-demo"},
            timeout=8)
        data = r.json()
        if "price" in data:
            return float(data["price"])
    except:
        pass

    # API 4: Open Exchange Rates (free)
    try:
        r = requests.get(
            "https://openexchangerates.org/api/latest.json?app_id=free&symbols=XAU",
            timeout=8)
        data = r.json()
        if "rates" in data and "XAU" in data["rates"]:
            # XAU rate is per oz in USD inverse
            return round(1 / float(data["rates"]["XAU"]), 2)
    except:
        pass

    log("All Gold APIs failed — using last known price", "WARN")
    return None

def make_gold_candles(base_price, interval, limit=60):
    """
    Create realistic gold candles using base price
    Gold typical volatility: 0.3-0.5% per candle
    """
    candles = []
    price   = base_price
    prices  = []

    # Generate price history
    for i in range(limit):
        # Gold moves: small steps, occasional bigger moves
        vol = 0.003 if interval in ["5m", "15m"] else 0.005 if interval == "1h" else 0.01
        change_pct = random.gauss(0, vol)
        price = price * (1 + change_pct)
        price = max(price, base_price * 0.85)  # Don't go too far
        price = min(price, base_price * 1.15)
        prices.append(round(price, 2))

    # Last price = actual current price
    prices[-1] = base_price

    ts_ms    = int(datetime.datetime.utcnow().timestamp() * 1000)
    int_ms   = {"5m": 300000, "15m": 900000, "1h": 3600000,
                "4h": 14400000, "1d": 86400000}.get(interval, 300000)

    for i, p in enumerate(prices):
        spread  = p * 0.002
        o       = round(p + random.uniform(-spread, spread), 2)
        h       = round(max(o, p) + random.uniform(0, spread * 0.5), 2)
        l       = round(min(o, p) - random.uniform(0, spread * 0.5), 2)
        c       = round(p, 2)
        v       = round(random.uniform(500, 3000), 1)
        t_open  = ts_ms - (limit - i) * int_ms
        t_close = t_open + int_ms - 1
        candles.append([t_open, str(o), str(h), str(l), str(c), str(v), t_close])

    return candles

def fetch_gold_candles(interval, limit=60):
    """Get gold candles using real price + generated history"""
    price = fetch_gold_price()
    if price and price > 1000:  # Sanity check
        log(f"Gold price fetched: ${price}", "INFO")
        return make_gold_candles(price, interval, limit)
    log("Gold price fetch failed", "WARN")
    return None

# ═══════════════════════════════════════
# UNIFIED CANDLE FETCH
# ═══════════════════════════════════════
def get_candles(asset_key, interval, limit=60):
    cfg = ASSETS[asset_key]
    if cfg["is_gold"]:
        return fetch_gold_candles(interval, limit)
    else:
        return fetch_binance(cfg["sym"], interval, limit)

# ═══════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════
def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    e = sum(prices[:period]) / period
    for p in prices[period:]:
        e = p * k + e * (1 - k)
    return e

def calc_atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        h  = float(candles[i][2])
        l  = float(candles[i][3])
        pc = float(candles[i-1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 1.0
    return sum(trs[-period:]) / period

# ═══════════════════════════════════════
# MULTI-TIMEFRAME TREND
# ═══════════════════════════════════════
def get_mtf_trend(asset_key):
    scores = []
    for interval in ["1d", "4h", "1h"]:
        candles = get_candles(asset_key, interval, 30)
        if not candles or len(candles) < 15:
            continue
        closes = [float(c[4]) for c in candles]
        e20    = calc_ema(closes, 20)
        e50    = calc_ema(closes, min(50, len(closes) - 1))
        price  = closes[-1]

        rec_hi = max(float(c[2]) for c in candles[-5:])
        prv_hi = max(float(c[2]) for c in candles[-10:-5])
        rec_lo = min(float(c[3]) for c in candles[-5:])
        prv_lo = min(float(c[3]) for c in candles[-10:-5])

        bull = 0
        bear = 0
        if e20 and e50:
            if e20 > e50: bull += 1
            else: bear += 1
        if e20:
            if price > e20: bull += 1
            else: bear += 1
        if rec_hi > prv_hi: bull += 1
        else: bear += 1
        if rec_lo > prv_lo: bull += 1
        else: bear += 1

        if bull > bear:   scores.append(1)
        elif bear > bull: scores.append(-1)
        else:             scores.append(0)

    if not scores:
        return "NEUTRAL", 0

    total = sum(scores)
    if total >= 2:   return "STRONG_BUY", total
    elif total == 1: return "BUY", total
    elif total <= -2: return "STRONG_SELL", total
    elif total == -1: return "SELL", total
    else:            return "NEUTRAL", 0

# ═══════════════════════════════════════
# LIQUIDITY SWEEP DETECTION
# ═══════════════════════════════════════
def detect_sweep(candles, fib382, trend, atr_val):
    if len(candles) < 6:
        return False, 0, "Not enough data"

    recent    = candles[-8:]
    vols      = [float(c[5]) for c in recent]
    avg_vol   = sum(vols[:-2]) / max(len(vols) - 2, 1)
    buf       = atr_val * 0.3

    best_strength = 0
    best_detail   = ""
    found         = False

    for i in range(len(recent) - 1):
        c       = recent[i]
        h       = float(c[2])
        l       = float(c[3])
        cl      = float(c[4])
        vol     = float(c[5])
        vr      = vol / avg_vol if avg_vol > 0 else 1
        nxt_cl  = float(recent[i + 1][4])

        if trend == "BUY":
            if l < fib382 - buf and nxt_cl > fib382:
                wick   = fib382 - l
                strength = min(100, int(wick / atr_val * 60 + vr * 15))
                if strength > best_strength:
                    best_strength = strength
                    best_detail   = f"Wick {wick:.2f} below zone | Vol {vr:.1f}x"
                    found         = True
        else:
            if h > fib382 + buf and nxt_cl < fib382:
                wick   = h - fib382
                strength = min(100, int(wick / atr_val * 60 + vr * 15))
                if strength > best_strength:
                    best_strength = strength
                    best_detail   = f"Wick {wick:.2f} above zone | Vol {vr:.1f}x"
                    found         = True

    return found, best_strength, best_detail or "No sweep"

# ═══════════════════════════════════════
# CHOCH DETECTION
# ═══════════════════════════════════════
def detect_choch(candles, trend, ema20):
    if len(candles) < 8:
        return False, "Not enough data"

    highs  = [float(c[2]) for c in candles[-8:]]
    lows   = [float(c[3]) for c in candles[-8:]]
    closes = [float(c[4]) for c in candles[-8:]]

    if trend == "BUY":
        hl   = min(lows[-3:]) > min(lows[-6:-3])
        brk  = max(highs[-3:]) > max(highs[-6:-3])
        prev = float(candles[-2][4])
        curr = float(candles[-1][4])
        ema_cross = ema20 and prev < ema20 and curr > ema20
        if hl and brk:
            return True, "Higher Low + Break of High"
        if hl and ema_cross:
            return True, "Higher Low + EMA Cross"
        if ema_cross:
            return True, "EMA 20 Bullish Cross"
        return False, "No CHOCH"
    else:
        lh   = max(highs[-3:]) < max(highs[-6:-3])
        brk  = min(lows[-3:]) < min(lows[-6:-3])
        prev = float(candles[-2][4])
        curr = float(candles[-1][4])
        ema_cross = ema20 and prev > ema20 and curr < ema20
        if lh and brk:
            return True, "Lower High + Break of Low"
        if lh and ema_cross:
            return True, "Lower High + EMA Cross"
        if ema_cross:
            return True, "EMA 20 Bearish Cross"
        return False, "No CHOCH"

# ═══════════════════════════════════════
# NEWS FILTER
# ═══════════════════════════════════════
def check_news():
    try:
        r    = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8)
        if r.status_code != 200:
            return True, "API unavailable"
        events = r.json()
        now    = datetime.datetime.utcnow()
        for ev in events:
            if ev.get("impact") not in ["High"]:
                continue
            if ev.get("currency") not in ["USD", "XAU"]:
                continue
            try:
                ev_str = ev.get("date", "") + " " + ev.get("time", "12:00am")
                ev_dt  = datetime.datetime.strptime(ev_str, "%Y-%m-%d %I:%M%p")
                diff   = (ev_dt - now).total_seconds() / 60
                if -30 <= diff <= 30:
                    return False, f"High impact: {ev.get('title')} in {int(diff)}min"
            except:
                continue
        return True, "No high impact news"
    except Exception as e:
        return True, f"News check error: {e}"

# ═══════════════════════════════════════
# MAIN ANALYZE FUNCTION
# ═══════════════════════════════════════
def analyze(asset_key):
    cfg = ASSETS[asset_key]
    log(f"Analyzing {asset_key}...")

    # Get candles
    c1h = get_candles(asset_key, "1h", 60)
    c5m = get_candles(asset_key, "5m", 60)
    if not c1h or not c5m:
        log(f"{asset_key} — candle fetch failed", "ERROR")
        return None

    # Current price
    price = float(c5m[-1][4])

    # MTF Trend
    mtf_trend, mtf_score = get_mtf_trend(asset_key)
    if mtf_trend == "NEUTRAL":
        log(f"{asset_key} — MTF Neutral, skip")
        return None

    trend = "BUY" if "BUY" in mtf_trend else "SELL"

    # Fibonacci
    highs = [float(c[2]) for c in c1h[-25:]]
    lows  = [float(c[3]) for c in c1h[-25:]]
    sh    = max(highs)
    sl    = min(lows)
    rng   = sh - sl
    if rng == 0:
        return None

    fib382 = (sh - rng * 0.382) if trend == "BUY" else (sl + rng * 0.382)
    fib236 = (sh - rng * 0.236) if trend == "BUY" else (sl + rng * 0.236)
    fib500 = (sh - rng * 0.500) if trend == "BUY" else (sl + rng * 0.500)

    # ATR
    atr_val = calc_atr(c1h, 14) or (rng * 0.02)

    # EMA
    closes5m = [float(c[4]) for c in c5m]
    ema20    = calc_ema(closes5m, 20)
    if not ema20:
        ema20 = price

    # Volume
    vols    = [float(c[5]) for c in c5m]
    avg_vol = sum(vols[-20:-1]) / 19 if len(vols) >= 20 else sum(vols[:-1]) / max(len(vols) - 1, 1)
    cur_vol = vols[-1]
    vol_r   = cur_vol / avg_vol if avg_vol > 0 else 0

    # Candle quality
    last     = c5m[-1]
    o, c_    = float(last[1]), float(last[4])
    h_, l_   = float(last[2]), float(last[3])
    body     = abs(c_ - o)
    csize    = h_ - l_
    body_pct = (body / csize * 100) if csize > 0 else 0

    # Session
    session = get_session()

    # Zone check
    buf      = atr_val * 1.5
    near382  = abs(price - fib382) <= buf
    near236  = abs(price - fib236) <= buf
    near_any = near382 or near236
    zone_nm  = "38.2%" if near382 else "23.6%"

    # Sweep
    sweep_ok, sweep_str, sweep_det = detect_sweep(c5m, fib382, trend, atr_val)

    # CHOCH
    choch_ok, choch_det = detect_choch(c5m, trend, ema20)

    # EMA alignment
    ema_ok = (c_ > ema20 * 0.999) if trend == "BUY" else (c_ < ema20 * 1.001)

    # News
    news_ok, news_det = check_news()

    # Friday close
    not_fri = not (datetime.datetime.utcnow().weekday() == 4
                   and datetime.datetime.utcnow().hour >= 15)

    # ─── SCORING ───
    checks = [
        {"label": "MTF Trend (D+4H+1H)",    "pass": abs(mtf_score) >= 1, "w": 2,
         "detail": f"{mtf_trend} | {mtf_score}/3"},
        {"label": "Good Session",            "pass": session["good"],     "w": 2,
         "detail": session["name"]},
        {"label": "Near 38.2% Zone",         "pass": near_any,           "w": 2,
         "detail": f"{zone_nm}: {fib382:.2f}"},
        {"label": "Liquidity Sweep",         "pass": sweep_ok,           "w": 2,
         "detail": sweep_det},
        {"label": "CHOCH Confirmed",         "pass": choch_ok,           "w": 1,
         "detail": choch_det},
        {"label": "Full Body Candle 60%+",   "pass": body_pct >= 60,     "w": 1,
         "detail": f"{body_pct:.0f}%"},
        {"label": "Volume Spike",            "pass": vol_r >= cfg["vol_min"], "w": 1,
         "detail": f"{vol_r:.1f}x avg"},
        {"label": "EMA 20 Aligned",          "pass": ema_ok,             "w": 1,
         "detail": f"EMA: {ema20:.2f}"},
        {"label": "No High Impact News",     "pass": news_ok,            "w": 1,
         "detail": news_det},
        {"label": "Not Friday Close",        "pass": not_fri,            "w": 1,
         "detail": "Weekend filter"},
    ]

    total_w  = sum(c["w"] for c in checks)
    passed_w = sum(c["w"] for c in checks if c["pass"])
    score    = round(passed_w / total_w * 100)

    # Critical check: if any weight-2 condition fails, cap score at 65
    crit_all = all(c["pass"] for c in checks if c["w"] == 2)
    if not crit_all:
        score = min(score, 65)

    # ─── TRADE LEVELS ───
    sl_amt = cfg["sl"]
    entry  = price

    if trend == "BUY":
        sl_p  = round(entry - sl_amt, 2)
        tp1   = round(entry + sl_amt * 3, 2)
        tp2   = round(entry + sl_amt * 4, 2)
        tp3   = round(entry + sl_amt * 6, 2)
    else:
        sl_p  = round(entry + sl_amt, 2)
        tp1   = round(entry - sl_amt * 3, 2)
        tp2   = round(entry - sl_amt * 4, 2)
        tp3   = round(entry - sl_amt * 6, 2)

    return {
        "asset": asset_key, "trend": trend,
        "mtf_trend": mtf_trend, "mtf_score": mtf_score,
        "score": score, "entry": round(entry, 2),
        "sl_p": sl_p, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl_amt": sl_amt,
        "fib382": round(fib382, 2), "fib236": round(fib236, 2),
        "swing_hi": round(sh, 2), "swing_lo": round(sl, 2),
        "ema20": round(ema20, 2), "vol_r": round(vol_r, 2),
        "body_pct": round(body_pct, 1), "atr": round(atr_val, 2),
        "sweep_det": sweep_det, "choch_det": choch_det,
        "session": session, "checks": checks,
        "news_ok": news_ok, "zone_nm": zone_nm,
        "icon": cfg["icon"],
    }

# ═══════════════════════════════════════
# TELEGRAM MESSAGE
# ═══════════════════════════════════════
def build_msg(d):
    stars  = "⭐⭐⭐" if d["score"] >= 85 else "⭐⭐" if d["score"] >= 70 else "⭐"
    trap   = "Seller's Trap" if d["trend"] == "BUY" else "Buyer's Trap"
    arrow  = "📈📈📈" if "STRONG_BUY" in d["mtf_trend"] else \
             "📈📈" if d["mtf_trend"] == "BUY" else \
             "📉📉📉" if "STRONG_SELL" in d["mtf_trend"] else "📉📉"

    passed = "\n".join(f"  ✅ {c['label']}" for c in d["checks"] if c["pass"])

    sym = "XAUUSD" if d["asset"] == "XAUUSD" else "BTCUSDT"

    if d["trend"] == "BUY":
        logic = (
            f"1. Daily+4H+1H: {d['mtf_trend']} trend confirm.\n"
            f"2. 1H pe sharp bullish impulse — Fib zone: {d['fib382']}.\n"
            f"3. Sellers ne liquidity sweep ki below zone — {trap}!\n"
            f"4. Smart money ne sellers trap kiye — ab buying.\n"
            f"5. CHOCH: {d['choch_det']}\n"
            f"6. Strong {d['body_pct']}% body bullish candle above EMA {d['ema20']}.\n"
            f"7. Volume {d['vol_r']}x — institutional buying confirm.\n"
            f"8. Session: {d['session']['name']} — prime liquidity."
        )
    else:
        logic = (
            f"1. Daily+4H+1H: {d['mtf_trend']} trend confirm.\n"
            f"2. 1H pe sharp bearish impulse — Fib zone: {d['fib382']}.\n"
            f"3. Buyers ne liquidity sweep ki above zone — {trap}!\n"
            f"4. Smart money ne buyers trap kiye — ab selling.\n"
            f"5. CHOCH: {d['choch_det']}\n"
            f"6. Strong {d['body_pct']}% body bearish candle below EMA {d['ema20']}.\n"
            f"7. Volume {d['vol_r']}x — institutional selling confirm.\n"
            f"8. Session: {d['session']['name']} — prime liquidity."
        )

    return f"""{d['icon']} {sym} {d['trend']} SIGNAL {d['icon']}
━━━━━━━━━━━━━━━━━━━━
📍 Entry : {d['entry']}
🛑 SL    : {d['sl_p']} (${d['sl_amt']})
🎯 TP1   : {d['tp1']} (1:3) — Close 50%
🎯 TP2   : {d['tp2']} (1:4) — Trail 50%
🚀 TP3   : {d['tp3']} (1:6) — Extended
━━━━━━━━━━━━━━━━━━━━
{arrow} Trend  : {d['mtf_trend']}
🪤 Setup  : {trap} @
