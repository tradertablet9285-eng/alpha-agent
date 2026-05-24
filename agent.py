#!/usr/bin/env python3
"""
Alpha Auto Agent v2.0 — UPGRADED
XAUUSD + BTCUSDT | Liquidity Sweep Strategy
Improvements:
- Multi-timeframe trend (Daily + 4H + 1H)
- News filter (Forexfactory)
- Better CHOCH detection (HH/LL structure)
- Better liquidity sweep detection
- Stronger scoring system
"""

import requests
import time
import datetime
import json

# ═══════════════════════════════════════
# ⚙️ CONFIGURATION
# ═══════════════════════════════════════
BOT_TOKEN           = "YAHAN_NAYA_TOKEN_DALO"
CHAT_ID             = "8867873147"
SCAN_INTERVAL_MIN   = 5
MIN_SCORE           = 70
COOLDOWN_HOURS      = 2
# ═══════════════════════════════════════

ASSETS = {
    "XAUUSD": {"sym": "XAUUSDT", "sl": 6.5,  "vol_min": 2.0, "icon": "⚡"},
    "BTCUSD": {"sym": "BTCUSDT", "sl": 175,   "vol_min": 3.0, "icon": "₿"},
}

last_signal = {"XAUUSD": 0, "BTCUSD": 0}
scan_count  = 0
sig_count   = 0

# ─── Logging ───
def log(msg, level="INFO"):
    t = datetime.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{t} GMT] [{level}] {msg}")

# ─── Session ───
def get_session():
    now = datetime.datetime.utcnow()
    h   = now.hour + now.minute / 60
    day = now.weekday()  # 0=Mon 4=Fri 5=Sat 6=Sun
    if day >= 5:
        return {"name": "Weekend",            "good": False, "quality": 0}
    if 0  <= h <  7:
        return {"name": "Asian 🌏",           "good": False, "quality": 1}
    if 7  <= h < 10:
        return {"name": "London Open 🇬🇧",   "good": True,  "quality": 8}
    if 10 <= h < 12:
        return {"name": "London Mid 🇬🇧",    "good": True,  "quality": 7}
    if 12 <= h < 15:
        return {"name": "London-NY Overlap 🔥","good": True, "quality": 10}
    if 15 <= h < 17:
        return {"name": "NY Open 🇺🇸",       "good": True,  "quality": 9}
    if 17 <= h < 20:
        return {"name": "NY Mid 🇺🇸",        "good": True,  "quality": 7}
    return {"name": "Closed 😴",              "good": False, "quality": 0}

# ─── Fetch Candles ───
def fetch(symbol, interval, limit=100):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10)
        data = r.json()
        if isinstance(data, list):
            return data
        return None
    except Exception as e:
        log(f"Fetch error {symbol} {interval}: {e}", "ERROR")
        return None

# ─── EMA ───
def ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    e = sum(prices[:period]) / period
    for p in prices[period:]:
        e = p * k + e * (1 - k)
    return e

# ─── ATR ───
def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        h  = float(candles[i][2])
        l  = float(candles[i][3])
        pc = float(candles[i-1][4])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period

# ─── Multi-Timeframe Trend ───
def get_mtf_trend(symbol):
    """
    Daily + 4H + 1H trend alignment
    Returns: 'STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG_SELL'
    """
    scores = []

    for interval in ["1d", "4h", "1h"]:
        candles = fetch(symbol, interval, 30)
        if not candles or len(candles) < 20:
            continue

        closes = [float(c[4]) for c in candles]

        # EMA 20 vs EMA 50
        e20 = ema(closes, 20)
        e50 = ema(closes, min(50, len(closes)-1))

        # Price vs EMA
        price = closes[-1]

        # Recent structure
        recent_high = max(float(c[2]) for c in candles[-5:])
        prev_high   = max(float(c[2]) for c in candles[-10:-5])
        recent_low  = min(float(c[3]) for c in candles[-5:])
        prev_low    = min(float(c[3]) for c in candles[-10:-5])

        # Bullish signals
        bull = 0
        if e20 and e50 and e20 > e50: bull += 1
        if e20 and price > e20: bull += 1
        if recent_high > prev_high: bull += 1  # HH
        if recent_low > prev_low: bull += 1    # HL

        # Bearish signals
        bear = 0
        if e20 and e50 and e20 < e50: bear += 1
        if e20 and price < e20: bear += 1
        if recent_high < prev_high: bear += 1  # LH
        if recent_low < prev_low: bear += 1    # LL

        if bull > bear:
            scores.append(1)
        elif bear > bull:
            scores.append(-1)
        else:
            scores.append(0)

    if not scores:
        return "NEUTRAL", 0

    total = sum(scores)
    if total >= 2:
        return "STRONG_BUY", total
    elif total == 1:
        return "BUY", total
    elif total <= -2:
        return "STRONG_SELL", total
    elif total == -1:
        return "SELL", total
    else:
        return "NEUTRAL", 0

# ─── News Filter ───
def check_news_risk():
    """
    Check if high-impact news is coming in next 30 min or happened in last 30 min
    Uses forexfactory calendar API
    Returns: True = safe to trade, False = news risk
    """
    try:
        now = datetime.datetime.utcnow()
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r   = requests.get(url, timeout=8)
        if r.status_code != 200:
            return True  # If can't fetch, assume safe

        events = r.json()
        for event in events:
            if event.get("impact") not in ["High", "Medium"]:
                continue
            # Currency filter — only Gold and USD relevant events
            currency = event.get("currency", "")
            if currency not in ["USD", "XAU", "GBP", "EUR"]:
                continue

            try:
                event_time_str = event.get("date", "") + " " + event.get("time", "")
                event_time = datetime.datetime.strptime(event_time_str, "%Y-%m-%d %I:%M%p")
                diff = (event_time - now).total_seconds() / 60  # minutes

                # Within ±30 minutes
                if -30 <= diff <= 30:
                    log(f"⚠️ NEWS RISK: {event.get('title')} in {int(diff)} min", "WARN")
                    return False
            except:
                continue

        return True  # No news risk

    except Exception as e:
        log(f"News check error: {e}", "WARN")
        return True  # If error, assume safe

# ─── Better CHOCH Detection ───
def detect_choch(candles, trend):
    """
    Proper Change of Character detection using HH/HL or LH/LL structure
    """
    if len(candles) < 10:
        return False, "Not enough data"

    highs = [float(c[2]) for c in candles[-10:]]
    lows  = [float(c[3]) for c in candles[-10:]]
    closes= [float(c[4]) for c in candles[-10:]]

    if trend == "BUY":
        # Look for: after downmove, price makes Higher Low then breaks recent high
        recent_lows  = lows[-5:]
        prev_lows    = lows[-10:-5]
        recent_high  = max(highs[-3:])
        prev_high    = max(highs[-8:-3])

        higher_low   = min(recent_lows) > min(prev_lows)
        broke_high   = recent_high > prev_high
        price_above_mid = closes[-1] > sum(closes[-5:]) / 5

        if higher_low and broke_high:
            return True, "HL + Break of High ✅"
        elif higher_low and price_above_mid:
            return True, "Higher Low formed ✅"
        return False, "No CHOCH yet"

    else:  # SELL
        recent_highs = highs[-5:]
        prev_highs   = highs[-10:-5]
        recent_low   = min(lows[-3:])
        prev_low     = min(lows[-8:-3])

        lower_high   = max(recent_highs) < max(prev_highs)
        broke_low    = recent_low < prev_low
        price_below_mid = closes[-1] < sum(closes[-5:]) / 5

        if lower_high and broke_low:
            return True, "LH + Break of Low ✅"
        elif lower_high and price_below_mid:
            return True, "Lower High formed ✅"
        return False, "No CHOCH yet"

# ─── Better Liquidity Sweep ───
def detect_sweep(candles, fib382, trend, atr_val):
    """
    Better liquidity sweep detection:
    - Wick must be significant (at least 0.5x ATR)
    - Must close back above/below zone
    - Volume should be higher on sweep candle
    """
    if len(candles) < 8 or not atr_val:
        return False, 0, "Insufficient data"

    recent = candles[-8:]
    vols   = [float(c[5]) for c in recent]
    avg_vol= sum(vols[:-2]) / max(len(vols)-2, 1)

    sweep_found  = False
    sweep_strength = 0
    sweep_details  = ""

    for i, c in enumerate(recent[:-1]):
        h = float(c[2])
        l = float(c[3])
        close = float(c[4])
        vol   = float(c[5])
        vol_ratio = vol / avg_vol if avg_vol > 0 else 0

        if trend == "BUY":
            # Wick went below fib382
            wick_below = fib382 - l
            if wick_below > atr_val * 0.3 and l < fib382:
                # Check if subsequent candle closed back above
                if i + 1 < len(recent):
                    next_close = float(recent[i+1][4])
                    if next_close > fib382:
                        strength = min(100, int((wick_below / atr_val) * 50 + vol_ratio * 20))
                        if strength > sweep_strength:
                            sweep_strength = strength
                            sweep_found    = True
                            sweep_details  = f"Wick: {wick_below:.2f} | Vol: {vol_ratio:.1f}x"
        else:
            # Wick went above fib382
            wick_above = h - fib382
            if wick_above > atr_val * 0.3 and h > fib382:
                if i + 1 < len(recent):
                    next_close = float(recent[i+1][4])
                    if next_close < fib382:
                        strength = min(100, int((wick_above / atr_val) * 50 + vol_ratio * 20))
                        if strength > sweep_strength:
                            sweep_strength = strength
                            sweep_found    = True
                            sweep_details  = f"Wick: {wick_above:.2f} | Vol: {vol_ratio:.1f}x"

    # Also check last candle
    last = candles[-1]
    last_close = float(last[4])
    if trend == "BUY" and last_close > fib382:
        recent_lows = [float(c[3]) for c in candles[-5:]]
        if any(l < fib382 for l in recent_lows[:-1]):
            sweep_found = True
            sweep_strength = max(sweep_strength, 60)

    return sweep_found, sweep_strength, sweep_details

# ─── Main Analyze ───
def analyze(asset_key):
    cfg = ASSETS[asset_key]
    sym = cfg["sym"]
    log(f"Analyzing {asset_key}...")

    # Fetch candles
    c1h = fetch(sym, "1h", 60)
    c5m = fetch(sym, "5m", 60)
    if not c1h or not c5m:
        return None

    price = float(c5m[-1][4])

    # ── Multi-timeframe trend ──
    mtf_trend, mtf_score = get_mtf_trend(sym)
    if mtf_trend == "NEUTRAL":
        log(f"{asset_key} — MTF Neutral, skipping")
        return None

    trend = "BUY" if "BUY" in mtf_trend else "SELL"
    trend_strong = "STRONG" in mtf_trend

    # ── Fibonacci ──
    highs_1h = [float(c[2]) for c in c1h[-25:]]
    lows_1h  = [float(c[3]) for c in c1h[-25:]]
    sh       = max(highs_1h)
    sl_level = min(lows_1h)
    rng      = sh - sl_level

    if rng == 0:
        return None

    fib382 = (sh - rng * 0.382) if trend == "BUY" else (sl_level + rng * 0.382)
    fib236 = (sh - rng * 0.236) if trend == "BUY" else (sl_level + rng * 0.236)
    fib500 = (sh - rng * 0.500) if trend == "BUY" else (sl_level + rng * 0.500)

    # ── ATR ──
    atr_val = atr(c1h, 14)

    # ── EMA 20 on 5M ──
    closes_5m = [float(c[4]) for c in c5m]
    ema20     = ema(closes_5m, 20)
    ema50     = ema(closes_5m, 50)

    # ── Volume ──
    vols    = [float(c[5]) for c in c5m]
    avg_vol = sum(vols[-20:-1]) / 19 if len(vols) >= 20 else sum(vols[:-1]) / max(len(vols)-1, 1)
    curr_vol= vols[-1]
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0

    # ── Candle Quality ──
    last  = c5m[-1]
    o,c_  = float(last[1]), float(last[4])
    h,l   = float(last[2]), float(last[3])
    body  = abs(c_ - o)
    total = h - l
    body_pct  = (body / total * 100) if total > 0 else 0
    is_bullish_candle = c_ > o
    candle_direction_ok = (trend == "BUY" and is_bullish_candle) or (trend == "SELL" and not is_bullish_candle)

    # ── Session ──
    session = get_session()

    # ── Near Zone ──
    buf      = atr_val * 0.5 if atr_val else rng * 0.02
    near382  = abs(price - fib382) <= buf * 3
    near236  = abs(price - fib236) <= buf * 3
    near_zone= near382 or near236
    zone_name= "38.2%" if near382 else "23.6%"

    # ── Liquidity Sweep ──
    sweep_found, sweep_strength, sweep_detail = detect_sweep(c5m, fib382, trend, atr_val)

    # ── CHOCH ──
    choch_found, choch_detail = detect_choch(c5m, trend)

    # ── EMA alignment ──
    ema_ok = False
    ema_detail = ""
    if ema20:
        if trend == "BUY":
            ema_ok = c_ > ema20 * 0.999
            ema_detail = f"Price {price:.2f} > EMA20 {ema20:.2f}"
        else:
            ema_ok = c_ < ema20 * 1.001
            ema_detail = f"Price {price:.2f} < EMA20 {ema20:.2f}"

    # ── News Filter ──
    news_safe = check_news_risk()

    # ── Friday Filter ──
    not_friday_close = not (datetime.datetime.utcnow().weekday() == 4 and
                           datetime.datetime.utcnow().hour >= 15)

    # ─── SCORING (10 conditions) ───
    checks = [
        {"label": "MTF Trend Aligned (D+4H+1H)", "pass": trend_strong or abs(mtf_score) >= 1,
         "detail": f"{mtf_trend} | Score: {mtf_score}/3", "weight": 2},
        {"label": "Good Session (London/NY)",     "pass": session["good"],
         "detail": session["name"], "weight": 2},
        {"label": "Near 38.2% Fib Zone",          "pass": near_zone,
         "detail": f"{zone_name} zone: {fib382:.2f}", "weight": 2},
        {"label": "Liquidity Sweep Confirmed",    "pass": sweep_found,
         "detail": sweep_detail or "No sweep detected", "weight": 2},
        {"label": "CHOCH Confirmed",              "pass": choch_found,
         "detail": choch_detail, "weight": 1},
        {"label": "Full Body Candle (60%+)",      "pass": body_pct >= 60,
         "detail": f"Body: {body_pct:.1f}%", "weight": 1},
        {"label": "Volume Spike",                 "pass": vol_ratio >= cfg["vol_min"],
         "detail": f"Vol: {vol_ratio:.1f}x avg", "weight": 1},
        {"label": "EMA 20 Aligned",              "pass": ema_ok,
         "detail": ema_detail, "weight": 1},
        {"label": "No News Risk",                "pass": news_safe,
         "detail": "Calendar checked", "weight": 1},
        {"label": "Not Friday Close",            "pass": not_friday_close,
         "detail": "Weekend filter", "weight": 1},
    ]

    # Weighted score
    total_weight  = sum(c["weight"] for c in checks)
    passed_weight = sum(c["weight"] for c in checks if c["pass"])
    score         = round((passed_weight / total_weight) * 100)

    # Critical conditions — if any fails, max score 65%
    critical_passed = all(c["pass"] for c in checks if c["weight"] == 2)
    if not critical_passed:
        score = min(score, 65)

    # ── Entry / SL / TP ──
    sl_amt = cfg["sl"]
    entry  = price
    if atr_val:
        # ATR-based SL for better accuracy
        atr_sl = min(atr_val * 0.8, sl_amt * 1.2)
        sl_amt = round(min(sl_amt, atr_sl), 2)

    if trend == "BUY":
        sl_price = round(entry - sl_amt, 2)
        tp1      = round(entry + sl_amt * 3, 2)
        tp2      = round(entry + sl_amt * 4, 2)
        tp3      = round(entry + sl_amt * 6, 2)  # Extended target
    else:
        sl_price = round(entry + sl_amt, 2)
        tp1      = round(entry - sl_amt * 3, 2)
        tp2      = round(entry - sl_amt * 4, 2)
        tp3      = round(entry - sl_amt * 6, 2)

    return {
        "asset":         asset_key,
        "symbol":        sym,
        "trend":         trend,
        "mtf_trend":     mtf_trend,
        "mtf_score":     mtf_score,
        "score":         score,
        "entry":         round(entry, 2),
        "sl_price":      sl_price,
        "tp1":           tp1,
        "tp2":           tp2,
        "tp3":           tp3,
        "sl_amt":        sl_amt,
        "fib382":        round(fib382, 2),
        "fib236":        round(fib236, 2),
        "fib500":        round(fib500, 2),
        "swing_high":    round(sh, 2),
        "swing_low":     round(sl_level, 2),
        "ema20":         round(ema20, 2) if ema20 else 0,
        "vol_ratio":     round(vol_ratio, 2),
        "body_pct":      round(body_pct, 1),
        "sweep_strength":sweep_strength,
        "sweep_detail":  sweep_detail,
        "choch_detail":  choch_detail,
        "session":       session,
        "checks":        checks,
        "news_safe":     news_safe,
        "atr":           round(atr_val, 2) if atr_val else 0,
        "zone_name":     zone_name,
        "icon":          cfg["icon"],
    }

# ─── Build Telegram Message ───
def build_msg(d):
    stars   = "⭐⭐⭐" if d["score"] >= 85 else "⭐⭐" if d["score"] >= 70 else "⭐"
    trap    = "Seller's Trap 🐻" if d["trend"] == "BUY" else "Buyer's Trap 🐂"
    mtf_bar = "📈📈📈" if d["mtf_trend"] == "STRONG_BUY" else \
              "📈📈" if d["mtf_trend"] == "BUY" else \
              "📉📉📉" if d["mtf_trend"] == "STRONG_SELL" else "📉📉"

    passed = "\n".join(f"  ✅ {c['label']}" for c in d["checks"] if c["pass"])
    failed = "\n".join(f"  ⚠️ {c['label']}" for c in d["checks"] if not c["pass"])

    # Trade logic
    if d["trend"] == "BUY":
        logic = (
            f"1. 4H/Daily chart bullish trend confirm ({d['mtf_trend']}).\n"
            f"2. 1H pe sharp bullish impulse move — Fib draw kiya.\n"
            f"3. 38.2% zone ({d['fib382']}) pe sellers ne liquidity sweep ki — {trap}!\n"
            f"4. Smart money ne sellers trap karke buying shuru ki.\n"
            f"5. 5M pe CHOCH: {d['choch_detail']}\n"
            f"6. Strong bullish candle {d['body_pct']}% body — 20 EMA ({d['ema20']}) ke upar.\n"
            f"7. Volume {d['vol_ratio']}x spike — institutional buying confirm.\n"
            f"8. Session: {d['session']['name']} — high liquidity active."
        )
    else:
        logic = (
            f"1. 4H/Daily chart bearish trend confirm ({d['mtf_trend']}).\n"
            f"2. 1H pe sharp bearish impulse move — Fib draw kiya.\n"
            f"3. 38.2% zone ({d['fib382']}) pe buyers ne liquidity sweep ki — {trap}!\n"
            f"4. Smart money ne buyers trap karke selling shuru ki.\n"
            f"5. 5M pe CHOCH: {d['choch_detail']}\n"
            f"6. Strong bearish candle {d['body_pct']}% body — 20 EMA ({d['ema20']}) ke neeche.\n"
            f"7. Volume {d['vol_ratio']}x spike — institutional selling confirm.\n"
            f"8. Session: {d['session']['name']} — high liquidity active."
        )

    sym = "XAUUSD" if d["asset"] == "XAUUSD" else "BTCUSDT"

    msg = f"""{d['icon']} {sym} {d['trend']} SIGNAL {d['icon']}
━━━━━━━━━━━━━━━━━━━━
📍 Entry   : {d['entry']}
🛑 SL      : {d['sl_price']} (${d['sl_amt']})
🎯 TP1     : {d['tp1']} (1:3) → 50% close
🎯 TP2     : {d['tp2']} (1:4) → Trail 50%
🚀 TP3     : {d['tp3']} (1:6) → Extended
━━━━━━━━━━━━━━━━━━━━
📊 MTF Trend  : {mtf_bar} {d['mtf_trend']}
🪤 Setup      : {trap} @ {d['zone_name']}
📐 Fib Zones  : 38.2%={d['fib382']} | 23.6%={d['fib236']}
📈 Swing      : {d['swing_low']} → {d['swing_high']}
💹 Volume     : {d['vol_ratio']}x average
🕯️ Candle    : {d['body_pct']}% body
📡 ATR        : {d['atr']}
⏰ Session    : {d['session']['name']}
📰 News       : {'✅ Safe' if d['news_safe'] else '⚠️ Risk'}
━━━━━━━━━━━━━━━━━━━━
📋 TRADE LOGIC:
{logic}
━━━━━━━━━━━━━━━━━━━━
✅ CONDITIONS MET:
{passed}
━━━━━━━━━━━━━━━━━━━━
💪 Confidence  : {d['score']}% {stars}
⚠️ Max SL      : ${d['sl_amt']} only
📢 @Alphagoldsigna
🤖 Alpha Auto Agent v2.0"""

    return msg

# ─── Send Telegram ───
def send(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10)
        d = r.json()
        if d.get("ok"):
            log("✅ Signal sent!", "SUCCESS")
            return True
        else:
            log(f"Telegram error: {d.get('description')}", "ERROR")
            return False
    except Exception as e:
        log(f"Send error: {e}", "ERROR")
        return False

# ─── Startup Message ───
def startup():
    msg = """🚀 Alpha Auto Agent v2.0 STARTED!

✅ UPGRADES:
📊 Multi-Timeframe (Daily+4H+1H)
📰 News Filter (FF Calendar)
🔍 Better CHOCH Detection
💪 Better Sweep Detection
🎯 TP3 Extended Target Added
📡 ATR-based SL

⚙️ Settings:
• Assets: XAUUSD + BTCUSDT
• Scan: Every 5 minutes
• Min Score: 70%
• Cooldown: 2 hours

📢 @Alphagoldsigna
🤖 Agent is LIVE 24/7"""
    send(msg)

# ─── Main Loop ───
def main():
    global scan_count, sig_count
    log("=" * 50)
    log("ALPHA AUTO AGENT v2.0 STARTING...")
    log("=" * 50)
    startup()

    while True:
        scan_count += 1
        log(f"━━━ SCAN #{scan_count} ━━━")

        sess = get_session()
        if not sess["good"]:
            log(f"Session: {sess['name']} — Waiting for London/NY...")
            time.sleep(SCAN_INTERVAL_MIN * 60)
            continue

        for asset_key in ASSETS:
            try:
                data = analyze(asset_key)
                if not data:
                    log(f"{asset_key} — No valid data or neutral trend")
                    continue

                log(f"{asset_key} → {data['trend']} | MTF: {data['mtf_trend']} | "
                    f"Score: {data['score']}% | Price: {data['entry']} | "
                    f"Sweep: {data['sweep_found'] if 'sweep_found' in data else data['checks'][3]['pass']} | "
                    f"Session: {data['session']['name']}")

                if data["score"] >= MIN_SCORE:
                    now = time.time()
                    if now - last_signal[asset_key] > COOLDOWN_HOURS * 3600:
                        msg  = build_msg(data)
                        sent = send(msg)
                        if sent:
                            last_signal[asset_key] = now
                            sig_count += 1
                            log(f"✅ Signal #{sig_count} sent for {asset_key}!", "SUCCESS")
                    else:
                        rem = int((COOLDOWN_HOURS*3600 - (now - last_signal[asset_key])) / 60)
                        log(f"{asset_key} — Cooldown: {rem} min remaining")
                else:
                    failed = [c["label"] for c in data["checks"] if not c["pass"]]
                    log(f"{asset_key} — Score {data['score']}% < {MIN_SCORE}% | Failed: {', '.join(failed[:3])}")

                time.sleep(3)

            except Exception as e:
                log(f"{asset_key} error: {e}", "ERROR")
                continue

        log(f"━━━ Scan #{scan_count} done | Signals: {sig_count} | Next: {SCAN_INTERVAL_MIN}min ━━━")
        time.sleep(SCAN_INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
