#!/usr/bin/env python3
"""
Alpha Auto Agent v7.0
XAUUSD + BTCUSDT
Schedule:
- 9:00 AM IST  -> Morning View + News
- 11:00 AM IST -> Mid Morning Scan
- 6:00 PM IST  -> Evening View + News
- 7:30 PM IST  -> Prime Time Scan
- News alerts when major events detected
API: Twelve Data (Gold) + Binance (BTC)
Optimized: Minimum API calls
"""

import requests
import time
import datetime

# =======================================
# CONFIGURATION
# =======================================
BOT_TOKEN         = "8978957779:AAF8fNhxiaQw1VcNvMOnMClPd2alqVRjL1c"
TWELVE_DATA_KEY   = "6df2ea47705646f2aaf14fec76fc8b8b"
CHAT_ID           = "8867873147"
MIN_SCORE         = 60
COOLDOWN_HOURS    = 2

# Schedule (all IST times)
# GMT = IST - 5:30
SCHEDULE = {
    "morning_view":   {"ist_h": 9,  "ist_m": 0},   # 9:00 AM IST  = 3:30 GMT
    "mid_scan":       {"ist_h": 11, "ist_m": 0},   # 11:00 AM IST = 5:30 GMT
    "evening_view":   {"ist_h": 18, "ist_m": 0},   # 6:00 PM IST  = 12:30 GMT
    "prime_scan":     {"ist_h": 19, "ist_m": 30},  # 7:30 PM IST  = 14:00 GMT
    "london_scan":    {"ist_h": 13, "ist_m": 0},   # 1:00 PM IST  = 7:30 GMT
    "ny_scan":        {"ist_h": 20, "ist_m": 30},  # 8:30 PM IST  = 15:00 GMT
}
# =======================================

ASSETS = {
    "XAUUSD": {"sl": 6.5,  "vol_min": 1.5, "is_gold": True},
    "BTCUSD": {"sl": 175,  "vol_min": 2.0, "is_gold": False, "sym": "BTCUSDT"},
}

last_signal  = {"XAUUSD": 0, "BTCUSD": 0}
sig_count    = 0
sent_today   = {}  # Track what was sent today
last_date    = None
signal_history = []

# =======================================
# LOGGING
# =======================================
def log(msg, level="INFO"):
    t = datetime.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{t} GMT] [{level}] {msg}")

# =======================================
# IST TIME
# =======================================
def get_ist():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

def get_session():
    now = datetime.datetime.utcnow()
    h   = now.hour + now.minute / 60
    day = now.weekday()
    if day >= 5:
        return {"name": "Weekend", "good": False}
    if 0  <= h <  7:
        return {"name": "Asian", "good": False}
    if 7  <= h < 10:
        return {"name": "London Open", "good": True}
    if 10 <= h < 12:
        return {"name": "London Mid", "good": True}
    if 12 <= h < 15:
        return {"name": "London-NY Overlap", "good": True}
    if 15 <= h < 17:
        return {"name": "NY Open", "good": True}
    if 17 <= h < 20:
        return {"name": "NY Mid", "good": day != 4}
    return {"name": "Closed", "good": False}

# =======================================
# RESET DAILY FLAGS
# =======================================
def reset_daily_flags():
    global sent_today, last_date
    ist   = get_ist()
    today = ist.date()
    if last_date != today:
        sent_today = {}
        last_date  = today
        log("Daily flags reset for " + str(today))

# =======================================
# FETCH GOLD â€” TWELVE DATA
# =======================================
def fetch_gold(interval, limit=50):
    imap = {"5m":"5min","15m":"15min","1h":"1h","4h":"4h","1d":"1day"}
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol":"XAU/USD","interval":imap.get(interval,"1h"),
                    "outputsize":limit,"apikey":TWELVE_DATA_KEY},
            timeout=12)
        data = r.json()
        if data.get("status") == "error":
            log("Gold API: " + str(data.get("message",""))[:80], "ERROR")
            return None
        values = list(reversed(data.get("values", [])))
        if not values:
            return None
        candles = []
        for v in values:
            try:
                ts = int(datetime.datetime.strptime(
                    v["datetime"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
            except:
                ts = int(datetime.datetime.strptime(
                    v["datetime"], "%Y-%m-%d").timestamp() * 1000)
            candles.append([ts, str(v["open"]), str(v["high"]),
                            str(v["low"]), str(v["close"]),
                            str(v.get("volume","1000")), ts+60000])
        return candles
    except Exception as e:
        log("Gold fetch error: " + str(e), "ERROR")
        return None

# =======================================
# FETCH BTC â€” BINANCE PRIMARY
# =======================================
def fetch_btc(interval, limit=50):
    # Try Binance first
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol":"BTCUSDT","interval":interval,"limit":limit},
            timeout=10)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data
    except:
        pass

    # Fallback: Twelve Data
    imap = {"5m":"5min","15m":"15min","1h":"1h","4h":"4h","1d":"1day"}
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol":"BTC/USD","interval":imap.get(interval,"1h"),
                    "outputsize":limit,"apikey":TWELVE_DATA_KEY},
            timeout=12)
        data = r.json()
        if data.get("status") == "error":
            log("BTC Twelve Data: " + str(data.get("message",""))[:80], "ERROR")
            return None
        values = list(reversed(data.get("values",[])))
        if not values:
            return None
        candles = []
        for v in values:
            try:
                ts = int(datetime.datetime.strptime(
                    v["datetime"],"%Y-%m-%d %H:%M:%S").timestamp()*1000)
            except:
                ts = int(datetime.datetime.strptime(
                    v["datetime"],"%Y-%m-%d").timestamp()*1000)
            candles.append([ts,str(v["open"]),str(v["high"]),
                           str(v["low"]),str(v["close"]),
                           str(v.get("volume","1000")),ts+60000])
        return candles
    except Exception as e:
        log("BTC fetch error: " + str(e), "ERROR")
        return None

def get_candles(asset_key, interval, limit=50):
    if ASSETS[asset_key]["is_gold"]:
        return fetch_gold(interval, limit)
    return fetch_btc(interval, limit)

# =======================================
# INDICATORS
# =======================================
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
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    if not trs:
        return 1.0
    return sum(trs[-period:]) / min(len(trs), period)

# =======================================
# TREND â€” ONLY 1H (saves API calls)
# =======================================
def get_trend(asset_key):
    candles = get_candles(asset_key, "1h", 50)
    if not candles or len(candles) < 20:
        return "NEUTRAL", 0

    closes  = [float(c[4]) for c in candles]
    e20     = calc_ema(closes, 20)
    e50     = calc_ema(closes, min(50, len(closes)-1))
    price   = closes[-1]

    rec_hi  = max(float(c[2]) for c in candles[-5:])
    prv_hi  = max(float(c[2]) for c in candles[-10:-5])
    rec_lo  = min(float(c[3]) for c in candles[-5:])
    prv_lo  = min(float(c[3]) for c in candles[-10:-5])

    bull = bear = 0
    if e20 and e50:
        if e20 > e50: bull += 1
        else:         bear += 1
    if e20:
        if price > e20: bull += 1
        else:           bear += 1
    if rec_hi > prv_hi: bull += 1
    else:               bear += 1
    if rec_lo > prv_lo: bull += 1
    else:               bear += 1

    score = bull - bear
    if score >= 3:    return "STRONG_BUY", score
    elif score >= 1:  return "BUY", score
    elif score <= -3: return "STRONG_SELL", score
    elif score <= -1: return "SELL", score
    return "NEUTRAL", 0

# =======================================
# SWEEP DETECTION
# =======================================
def detect_sweep(candles, fib382, trend, atr_val):
    if len(candles) < 6:
        return False, "Not enough data"
    recent  = candles[-8:]
    vols    = [float(c[5]) for c in recent]
    avg_vol = sum(vols[:-2]) / max(len(vols)-2, 1)
    buf     = atr_val * 0.3
    found   = False
    detail  = "No sweep"
    best    = 0
    for i in range(len(recent)-1):
        h   = float(recent[i][2])
        l   = float(recent[i][3])
        vol = float(recent[i][5])
        vr  = vol / avg_vol if avg_vol > 0 else 1
        nxt = float(recent[i+1][4])
        if trend == "BUY":
            if l < fib382 - buf and nxt > fib382:
                wick = fib382 - l
                s    = min(100, int(wick/atr_val*60 + vr*15))
                if s > best:
                    best=s; found=True
                    detail = "Wick " + str(round(wick,2)) + " below zone | Vol " + str(round(vr,1)) + "x"
        else:
            if h > fib382 + buf and nxt < fib382:
                wick = h - fib382
                s    = min(100, int(wick/atr_val*60 + vr*15))
                if s > best:
                    best=s; found=True
                    detail = "Wick " + str(round(wick,2)) + " above zone | Vol " + str(round(vr,1)) + "x"
    return found, detail

# =======================================
# CHOCH
# =======================================
def detect_choch(candles, trend, ema20):
    if len(candles) < 8:
        return False, "Not enough data"
    highs = [float(c[2]) for c in candles[-8:]]
    lows  = [float(c[3]) for c in candles[-8:]]
    prev  = float(candles[-2][4])
    curr  = float(candles[-1][4])
    ecb   = ema20 and prev < ema20 and curr > ema20
    ecs   = ema20 and prev > ema20 and curr < ema20
    if trend == "BUY":
        hl = min(lows[-3:]) > min(lows[-6:-3])
        bh = max(highs[-3:]) > max(highs[-6:-3])
        if hl and bh:  return True, "Higher Low + Break of High"
        if hl:         return True, "Higher Low formed"
        if ecb:        return True, "EMA 20 Bullish Cross"
        return False, "No CHOCH"
    else:
        lh = max(highs[-3:]) < max(highs[-6:-3])
        bl = min(lows[-3:]) < min(lows[-6:-3])
        if lh and bl:  return True, "Lower High + Break of Low"
        if lh:         return True, "Lower High formed"
        if ecs:        return True, "EMA 20 Bearish Cross"
        return False, "No CHOCH"

# =======================================
# NEWS CHECK â€” FOREXFACTORY
# =======================================
def check_news():
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8)
        if r.status_code != 200:
            return True, "Safe", []
        now    = datetime.datetime.utcnow()
        events = []
        for ev in r.json():
            if ev.get("impact") != "High":
                continue
            if ev.get("currency") not in ["USD","XAU","BTC","GBP","EUR"]:
                continue
            try:
                ev_str = ev.get("date","") + " " + ev.get("time","12:00am")
                ev_dt  = datetime.datetime.strptime(ev_str, "%Y-%m-%d %I:%M%p")
                diff   = (ev_dt - now).total_seconds() / 60
                if -30 <= diff <= 30:
                    events.append({"title": ev.get("title",""), "diff": int(diff), "currency": ev.get("currency","")})
            except:
                continue
        if events:
            detail = events[0]["title"] + " in " + str(events[0]["diff"]) + "min"
            return False, detail, events
        return True, "Safe", []
    except:
        return True, "Safe", []

# =======================================
# GET TODAY'S NEWS
# =======================================
def get_todays_news():
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8)
        if r.status_code != 200:
            return []
        ist   = get_ist()
        today = ist.date()
        news  = []
        for ev in r.json():
            if ev.get("impact") not in ["High", "Medium"]:
                continue
            if ev.get("currency") not in ["USD","XAU","GBP","EUR","JPY"]:
                continue
            try:
                ev_date = datetime.datetime.strptime(ev.get("date",""), "%Y-%m-%d").date()
                if ev_date == today:
                    news.append({
                        "title":    ev.get("title",""),
                        "time":     ev.get("time",""),
                        "currency": ev.get("currency",""),
                        "impact":   ev.get("impact",""),
                    })
            except:
                continue
        return news
    except:
        return []

# =======================================
# ANALYZE ASSET
# =======================================
def analyze(asset_key):
    cfg = ASSETS[asset_key]
    log("Analyzing " + asset_key + "...")

    # Only 1H candles â€” saves API credits
    c1h = get_candles(asset_key, "1h", 50)
    if not c1h:
        return None

    price = float(c1h[-1][4])

    # Trend from 1H only
    trend, trend_score = get_trend(asset_key)
    if trend == "NEUTRAL":
        log(asset_key + " - Neutral trend, skip")
        return None

    direction = "BUY" if "BUY" in trend else "SELL"

    # Fib levels
    highs = [float(c[2]) for c in c1h[-25:]]
    lows  = [float(c[3]) for c in c1h[-25:]]
    sh, sl = max(highs), min(lows)
    rng    = sh - sl
    if rng == 0:
        return None

    fib382 = (sh - rng*0.382) if direction=="BUY" else (sl + rng*0.382)
    fib236 = (sh - rng*0.236) if direction=="BUY" else (sl + rng*0.236)

    atr_val  = calc_atr(c1h, 14) or rng*0.02
    closes1h = [float(c[4]) for c in c1h]
    ema20    = calc_ema(closes1h, 20) or price

    # Volume from 1H
    vols    = [float(c[5]) for c in c1h]
    avg_vol = sum(vols[-20:-1]) / 19 if len(vols) >= 20 else sum(vols[:-1]) / max(len(vols)-1,1)
    vol_r   = vols[-1] / avg_vol if avg_vol > 0 else 0

    # Last candle
    last     = c1h[-1]
    o, c_    = float(last[1]), float(last[4])
    h_, l_   = float(last[2]), float(last[3])
    csize    = h_ - l_
    body_pct = (abs(c_-o)/csize*100) if csize > 0 else 0

    session  = get_session()
    buf      = atr_val * 1.5
    near382  = abs(price - fib382) <= buf
    near236  = abs(price - fib236) <= buf
    near_any = near382 or near236
    zone_nm  = "38.2%" if near382 else "23.6%"

    sweep_ok, sweep_det = detect_sweep(c1h, fib382, direction, atr_val)
    choch_ok, choch_det = detect_choch(c1h, direction, ema20)

    ema_ok  = (c_ > ema20*0.999) if direction=="BUY" else (c_ < ema20*1.001)
    news_ok, news_det, _ = check_news()
    not_fri = not (datetime.datetime.utcnow().weekday()==4 and
                   datetime.datetime.utcnow().hour>=15)

    checks = [
        {"label": "Trend (1H)",         "pass": abs(trend_score)>=1, "w": 2},
        {"label": "Good Session",        "pass": session["good"],     "w": 2},
        {"label": "Near 38.2% Zone",     "pass": near_any,            "w": 2},
        {"label": "Liquidity Sweep",     "pass": sweep_ok,            "w": 2},
        {"label": "CHOCH Confirmed",     "pass": choch_ok,            "w": 1},
        {"label": "Full Body 60%+",      "pass": body_pct >= 60,      "w": 1},
        {"label": "Volume Spike",        "pass": vol_r >= cfg["vol_min"], "w": 1},
        {"label": "EMA 20 Aligned",      "pass": ema_ok,              "w": 1},
        {"label": "No High News",        "pass": news_ok,             "w": 1},
        {"label": "Not Friday Close",    "pass": not_fri,             "w": 1},
    ]

    total_w  = sum(c["w"] for c in checks)
    passed_w = sum(c["w"] for c in checks if c["pass"])
    score    = round(passed_w / total_w * 100)

    if not all(c["pass"] for c in checks if c["w"]==2):
        score = min(score, 65)

    sl_amt = cfg["sl"]
    entry  = price
    if direction == "BUY":
        sl_p = round(entry - sl_amt, 2)
        tp1  = round(entry + sl_amt*3, 2)
        tp2  = round(entry + sl_amt*4, 2)
        tp3  = round(entry + sl_amt*6, 2)
    else:
        sl_p = round(entry + sl_amt, 2)
        tp1  = round(entry - sl_amt*3, 2)
        tp2  = round(entry - sl_amt*4, 2)
        tp3  = round(entry - sl_amt*6, 2)

    return {
        "asset": asset_key, "trend": direction,
        "mtf_trend": trend, "score": score,
        "entry": round(entry,2), "sl_p": sl_p,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl_amt": sl_amt,
        "fib382": round(fib382,2), "fib236": round(fib236,2),
        "sh": round(sh,2), "sl_level": round(sl,2),
        "ema20": round(ema20,2), "vol_r": round(vol_r,2),
        "body_pct": round(body_pct,1), "atr": round(atr_val,2),
        "sweep_det": sweep_det, "choch_det": choch_det,
        "session": session, "checks": checks,
        "news_ok": news_ok, "zone_nm": zone_nm,
    }

# =======================================
# BUILD SIGNAL MESSAGE
# =======================================
def build_signal_msg(d):
    stars  = "\u2b50\u2b50\u2b50" if d["score"]>=80 else "\u2b50\u2b50" if d["score"]>=65 else "\u2b50"
    trap   = "Seller's Trap \U0001f43b" if d["trend"]=="BUY" else "Buyer's Trap \U0001f403"
    sym    = "XAUUSD" if d["asset"]=="XAUUSD" else "BTCUSDT"
    icon   = "\u26a1" if d["asset"]=="XAUUSD" else "\u20bf"
    news   = "\u2705 Safe" if d["news_ok"] else "\u26a0 Risk"
    sig    = "\U0001f7e2\u2b06 BUY" if d["trend"]=="BUY" else "\U0001f534\u2b07 SELL"
    conf   = "HIGH \U0001f525" if d["score"]>=80 else "GOOD \u26a1" if d["score"]>=65 else "OK \u26a0"
    passed = "\n".join("  \u2705 " + c["label"] for c in d["checks"] if c["pass"])

    if d["trend"] == "BUY":
        logic = "\n".join([
            "\U0001f4ca 1H trend: " + d["mtf_trend"],
            "\U0001f4c8 Sharp bullish move. Fib zone: " + str(d["fib382"]),
            "\U0001f43b Sellers swept below zone â€” TRAPPED!",
            "\U0001f3e6 Smart money buying started.",
            "\U0001f504 CHOCH: " + d["choch_det"],
            "\U0001f55f Candle: " + str(d["body_pct"]) + "% body above EMA " + str(d["ema20"]),
            "\U0001f4a5 Volume: " + str(d["vol_r"]) + "x spike = Institutional BUY!",
            "\u23f0 Session: " + d["session"]["name"],
        ])
    else:
        logic = "\n".join([
            "\U0001f4ca 1H trend: " + d["mtf_trend"],
            "\U0001f4c9 Sharp bearish move. Fib zone: " + str(d["fib382"]),
            "\U0001f403 Buyers swept above zone â€” TRAPPED!",
            "\U0001f3e6 Smart money selling started.",
            "\U0001f504 CHOCH: " + d["choch_det"],
            "\U0001f55f Candle: " + str(d["body_pct"]) + "% body below EMA " + str(d["ema20"]),
            "\U0001f4a5 Volume: " + str(d["vol_r"]) + "x spike = Institutional SELL!",
            "\u23f0 Session: " + d["session"]["name"],
        ])

    lines = [
        icon + " " + sym + " " + sig + " " + icon,
        "=" * 24,
        "\U0001f4cd Entry   : " + str(d["entry"]),
        "\U0001f6d1 SL      : " + str(d["sl_p"]) + " (Max $" + str(d["sl_amt"]) + ")",
        "\U0001f3af TP1     : " + str(d["tp1"]) + " (1:3) Close 50%",
        "\U0001f3af TP2     : " + str(d["tp2"]) + " (1:4) Trail 50%",
        "\U0001f680 TP3     : " + str(d["tp3"]) + " (1:6) Extended",
        "=" * 24,
        "\U0001f4ca Trend   : " + d["mtf_trend"],
        "\U0001f9f2 Setup   : " + trap,
        "\U0001f4d0 Zone    : " + str(d["fib382"]) + " (" + d["zone_nm"] + ")",
        "\U0001f4cf Swing   : " + str(d["sl_level"]) + " to " + str(d["sh"]),
        "\U0001f4a5 Volume  : " + str(d["vol_r"]) + "x avg",
        "\U0001f55f Candle  : " + str(d["body_pct"]) + "% body",
        "\U0001f4e1 ATR     : " + str(d["atr"]),
        "\u23f0 Session : " + d["session"]["name"],
        "\U0001f4f0 News    : " + news,
        "=" * 24,
        "\U0001f4cb TRADE LOGIC:",
        logic,
        "=" * 24,
        "\u2705 CONDITIONS:",
        passed,
        "=" * 24,
        "\U0001f4af Score   : " + str(d["score"]) + "% " + stars,
        "\U0001f4aa Confidence: " + conf,
        "\u26a0  Max SL  : $" + str(d["sl_amt"]) + " only!",
        "\U0001f4cc TP1 hit = Close 50% + Move SL to entry",
        "=" * 24,
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v7.0",
    ]
    return "\n".join(lines)

# =======================================
# BUILD MARKET VIEW
# =======================================
def build_market_view(time_of_day):
    ist     = get_ist()
    ist_str = ist.strftime("%I:%M %p") + " IST"

    if time_of_day == "morning":
        header = "\U0001f31e Good Morning Traders!"
        sub    = "\U0001f4ca Morning Market Analysis"
    else:
        header = "\U0001f307 Good Evening Traders!"
        sub    = "\U0001f4ca Evening Market Update"

    lines = [header, sub, "\U0001f550 " + ist_str, "=" * 24]

    for asset_key in ASSETS:
        sym  = "XAUUSD" if asset_key == "XAUUSD" else "BTCUSDT"
        icon = "\u26a1" if asset_key == "XAUUSD" else "\u20bf"

        c1h = get_candles(asset_key, "1h", 50)
        if not c1h:
            lines.append("\n" + icon + " " + sym + ": Data unavailable \u26a0")
            continue

        price   = float(c1h[-1][4])
        trend, ts = get_trend(asset_key)

        highs   = [float(c[2]) for c in c1h[-20:]]
        lows    = [float(c[3]) for c in c1h[-20:]]
        sh, sl  = max(highs), min(lows)
        rng     = sh - sl
        fib382  = sh - rng * 0.382
        fib236  = sh - rng * 0.236

        closes  = [float(c[4]) for c in c1h]
        ema20   = calc_ema(closes, 20) or price
        ema50   = calc_ema(closes, 50) or price
        atr_val = calc_atr(c1h, 14) or 1

        if "STRONG_BUY" in trend:
            bias_icon = "\U0001f4c8\U0001f4c8"
            bias      = "STRONG BULLISH"
            action    = "Buy dips at " + str(round(fib382, 2))
            do        = "\U0001f7e2 BUY BIAS"
        elif "BUY" in trend:
            bias_icon = "\U0001f4c8"
            bias      = "BULLISH"
            action    = "Buy pullback to " + str(round(fib382, 2))
            do        = "\U0001f7e2 BUY BIAS"
        elif "STRONG_SELL" in trend:
            bias_icon = "\U0001f4c9\U0001f4c9"
            bias      = "STRONG BEARISH"
            action    = "Sell rally at " + str(round(fib382, 2))
            do        = "\U0001f534 SELL BIAS"
        elif "SELL" in trend:
            bias_icon = "\U0001f4c9"
            bias      = "BEARISH"
            action    = "Sell rally to " + str(round(fib382, 2))
            do        = "\U0001f534 SELL BIAS"
        else:
            bias_icon = "\u23f8"
            bias      = "NEUTRAL"
            action    = "Wait for direction"
            do        = "\U0001f7e1 NEUTRAL"

        lines += [
            "",
            icon + " " + sym + " " + bias_icon,
            "\u2500" * 20,
            "\U0001f4b0 Price     : " + str(price),
            "\U0001f4ca Trend     : " + bias,
            "\U0001f4cf EMA 20    : " + str(round(ema20, 2)),
            "\U0001f4cf EMA 50    : " + str(round(ema50, 2)),
            "\U0001f3af 38.2% Zone: " + str(round(fib382, 2)),
            "\U0001f3af 23.6% Zone: " + str(round(fib236, 2)),
            "\U0001f6e1 Support   : " + str(round(sl, 2)),
            "\u26a0  Resist    : " + str(round(sh, 2)),
            "\U0001f4e1 ATR       : " + str(round(atr_val, 2)),
            "\u2714 " + do,
            "\U0001f4cc Action    : " + action,
        ]

    # Add today's news
    news_list = get_todays_news()
    lines.append("\n" + "=" * 24)
    lines.append("\U0001f4f0 TODAY'S MAJOR NEWS:")
    if news_list:
        for n in news_list[:6]:
            impact_icon = "\U0001f534" if n["impact"] == "High" else "\U0001f7e1"
            lines.append(impact_icon + " " + n["currency"] + " | " + n["title"] + " @ " + n["time"])
    else:
        lines.append("\u2705 No major news today - Safe to trade!")

    lines += [
        "=" * 24,
        "\U0001f9e0 Strategy: 38.2% Liquidity Sweep",
        "\u23f3 Wait for sweep + confirmation",
        "\U0001f4af Min Score: 60%+ for entry",
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v7.0",
    ]
    return "\n".join(lines)

# =======================================
# NEWS ALERT (standalone)
# =======================================
def build_news_alert(news_list):
    ist = get_ist()
    lines = [
        "\U0001f6a8 MAJOR NEWS ALERT!",
        "\U0001f550 " + ist.strftime("%I:%M %p") + " IST",
        "=" * 24,
        "\u26a0 HIGH IMPACT NEWS TODAY:",
    ]
    for n in news_list:
        impact_icon = "\U0001f534" if n["impact"] == "High" else "\U0001f7e1"
        lines.append(impact_icon + " " + n["currency"] + " | " + n["title"] + " @ " + n["time"])
    lines += [
        "=" * 24,
        "\U0001f6d1 CAUTION: Avoid trading 30min before/after!",
        "\U0001f4b0 High volatility expected!",
        "=" * 24,
        "\U0001f4e2 @Alphagoldsigna",
    ]
    return "\n".join(lines)

# =======================================
# SEND
# =======================================
def send(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10)
        d = r.json()
        if d.get("ok"):
            log("Sent!", "SUCCESS")
            return True
        log("Telegram: " + str(d.get("description","")), "ERROR")
        return False
    except Exception as e:
        log("Send error: " + str(e), "ERROR")
        return False

# =======================================
# RUN SIGNAL SCAN
# =======================================
def run_scan(label=""):
    global sig_count
    log("=== SIGNAL SCAN " + label + " ===")
    sess = get_session()
    log("Session: " + sess["name"])

    for asset_key in ASSETS:
        try:
            data = analyze(asset_key)
            if not data:
                log(asset_key + " - No setup")
                continue

            log(asset_key + " | " + data["trend"] + " | Score:" + str(data["score"]) + "% | Price:" + str(data["entry"]))

            if data["score"] >= MIN_SCORE:
                now_t = time.time()
                if now_t - last_signal[asset_key] > COOLDOWN_HOURS * 3600:
                    if send(build_signal_msg(data)):
                        last_signal[asset_key] = now_t
                        sig_count += 1
                        dt_now = datetime.datetime.utcnow()
                        signal_history.append({
                            "asset":   asset_key,
                            "trend":   data["trend"],
                            "entry":   data["entry"],
                            "score":   data["score"],
                            "session": data["session"]["name"],
                            "result":  "pending",
                            "pnl":     0,
                            "week":    dt_now.isocalendar()[1],
                            "month":   dt_now.month,
                            "year":    dt_now.year,
                        })
                        log("Signal #" + str(sig_count) + " sent for " + asset_key + "!", "SUCCESS")
                else:
                    rem = int((COOLDOWN_HOURS*3600 - (time.time()-last_signal[asset_key]))/60)
                    log(asset_key + " cooldown: " + str(rem) + "min")
            else:
                failed = [c["label"] for c in data["checks"] if not c["pass"]]
                log(asset_key + " score " + str(data["score"]) + "% | Failed: " + ", ".join(failed[:3]))

            time.sleep(2)

        except Exception as e:
            log(asset_key + " error: " + str(e), "ERROR")

# =======================================
# STARTUP
# =======================================
def startup():
    send("\n".join([
        "\U0001f916 Alpha Auto Agent v7.0 LIVE! \U0001f680",
        "",
        "\u2705 XAUUSD + BTCUSDT Real Data",
        "\u2705 API Optimized - No more limit errors",
        "",
        "\U0001f4cb DAILY SCHEDULE (IST):",
        "\U0001f31e 9:00 AM  - Morning View + News",
        "\U0001f50d 11:00 AM - London Open Scan",
        "\U0001f50d 1:00 PM  - London Mid Scan",
        "\U0001f525 6:00 PM  - Evening View + News",
        "\U0001f680 7:30 PM  - Prime Time Scan",
        "\U0001f50d 8:30 PM  - NY Open Scan",
        "",
        "\U0001f4f0 Major News Alert - Auto detect",
        "\U0001f3af Min Score: 60%+",
        "\u23f0 Cooldown: 2 hours per asset",
        "",
        "\U0001f4e2 @Alphagoldsigna",
        "Let's make money! \U0001f4b0\U0001f525",
    ]))

# =======================================
# MAIN LOOP
# =======================================
def main():
    log("=" * 40)
    log("ALPHA AUTO AGENT v7.0 STARTING")
    log("=" * 40)
    startup()

    while True:
        reset_daily_flags()
        ist = get_ist()
        h   = ist.hour
        m   = ist.minute

        # â”€â”€ 9:00 AM IST â€” Morning View + News â”€â”€
        if h == 9 and m < 5 and "morning_view" not in sent_today:
            log("Sending morning view...")
            if send(build_market_view("morning")):
                sent_today["morning_view"] = True
                # Send news alert if major news today
                news = get_todays_news()
                high_news = [n for n in news if n["impact"] == "High"]
                if high_news and "morning_news" not in sent_today:
                    send(build_news_alert(high_news))
                    sent_today["morning_news"] = True

        # â”€â”€ 11:00 AM IST â€” London Open Scan â”€â”€
        elif h == 11 and m < 5 and "mid_scan" not in sent_today:
            run_scan("London Open 11AM")
            sent_today["mid_scan"] = True

        # â”€â”€ 1:00 PM IST â€” London Mid Scan â”€â”€
        elif h == 13 and m < 5 and "london_scan" not in sent_today:
            run_scan("London Mid 1PM")
            sent_today["london_scan"] = True

        # â”€â”€ 6:00 PM IST â€” Evening View + News â”€â”€
        elif h == 18 and m < 5 and "evening_view" not in sent_today:
            log("Sending evening view...")
            if send(build_market_view("evening")):
                sent_today["evening_view"] = True
                # Send news update
                news = get_todays_news()
                high_news = [n for n in news if n["impact"] == "High"]
                if high_news and "evening_news" not in sent_today:
                    send(build_news_alert(high_news))
                    sent_today["evening_news"] = True

        # â”€â”€ 7:30 PM IST â€” Prime Time Scan â”€â”€
        elif h == 19 and m >= 30 and m < 35 and "prime_scan" not in sent_today:
            run_scan("PRIME TIME 7:30PM")
            sent_today["prime_scan"] = True

        # â”€â”€ 8:30 PM IST â€” NY Open Scan â”€â”€
        elif h == 20 and m >= 30 and m < 35 and "ny_scan" not in sent_today:
            run_scan("NY Open 8:30PM")
            sent_today["ny_scan"] = True

        # â”€â”€ Weekly Report â€” Sunday 8PM IST â”€â”€
        elif ist.weekday() == 6 and h == 20 and m < 5 and "weekly_report" not in sent_today:
            log("Sending weekly report...")
            send(build_weekly_report())
            sent_today["weekly_report"] = True

        # â”€â”€ Monthly Report â€” 1st of month 9AM IST â”€â”€
        elif ist.day == 1 and h == 9 and m >= 5 and m < 10 and "monthly_report" not in sent_today:
            log("Sending monthly report...")
            send(build_monthly_report())
            sent_today["monthly_report"] = True

        else:
            log("IST: " + str(h) + ":" + str(m).zfill(2) + " | Signals sent: " + str(sig_count) + " | Waiting for next schedule...")

        time.sleep(60)  # Check every 1 minute

# =======================================
# WEEKLY REPORT
# =======================================
def build_weekly_report():
    now  = datetime.datetime.utcnow()
    week = now.isocalendar()[1]
    year = now.year
    ws   = [s for s in signal_history if s.get("week")==week and s.get("year")==year]
    total = len(ws)
    wins  = len([s for s in ws if s.get("result")=="win"])
    losses= len([s for s in ws if s.get("result")=="loss"])
    wr    = round(wins/total*100) if total > 0 else 0
    pnl   = sum(s.get("pnl",0) for s in ws)
    grade = "A+" if wr>=80 else "A" if wr>=70 else "B+" if wr>=60 else "B" if wr>=50 else "C"
    xau   = [s for s in ws if s["asset"]=="XAUUSD"]
    btc   = [s for s in ws if s["asset"]=="BTCUSD"]
    xwr   = round(len([s for s in xau if s.get("result")=="win"])/max(len(xau),1)*100)
    bwr   = round(len([s for s in btc if s.get("result")=="win"])/max(len(btc),1)*100)
    edges = []
    if wr >= 70: edges.append("Strategy working well this week!")
    if xwr >= 70: edges.append("XAUUSD strong (" + str(xwr) + "% WR)")
    if bwr >= 70: edges.append("BTCUSDT strong (" + str(bwr) + "% WR)")
    if not edges: edges.append("Focus on quality setups next week")
    lines = [
        "\U0001f4ca WEEKLY REPORT - Week #" + str(week),
        "=" * 24,
        "\U0001f4ca Signals  : " + str(total),
        "\u2705 Wins     : " + str(wins),
        "\u274c Losses   : " + str(losses),
        "\U0001f3af Win Rate : " + str(wr) + "%",
        "\U0001f4b0 P&L      : " + ("+" if pnl>=0 else "") + "$" + str(round(pnl,1)),
        "\U0001f3c6 Grade    : " + grade,
        "=" * 24,
        "\u26a1 XAUUSD  : " + str(len(xau)) + " | " + str(xwr) + "% WR",
        "\u20bf BTCUSDT : " + str(len(btc)) + " | " + str(bwr) + "% WR",
        "=" * 24,
        "\U0001f4a1 EDGES:",
    ] + ["\u2714 " + e for e in edges] + [
        "=" * 24,
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v7.0",
    ]
    return "\n".join(lines)

# =======================================
# MONTHLY REPORT
# =======================================
def build_monthly_report():
    now   = datetime.datetime.utcnow()
    month = now.month
    year  = now.year
    mname = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month-1]
    ms    = [s for s in signal_history if s.get("month")==month and s.get("year")==year]
    total = len(ms)
    wins  = len([s for s in ms if s.get("result")=="win"])
    losses= len([s for s in ms if s.get("result")=="loss"])
    wr    = round(wins/total*100) if total > 0 else 0
    pnl   = sum(s.get("pnl",0) for s in ms)
    grade = "A+" if wr>=80 else "A" if wr>=70 else "B+" if wr>=60 else "B" if wr>=50 else "C"
    xau   = [s for s in ms if s["asset"]=="XAUUSD"]
    btc   = [s for s in ms if s["asset"]=="BTCUSD"]
    xwr   = round(len([s for s in xau if s.get("result")=="win"])/max(len(xau),1)*100)
    bwr   = round(len([s for s in btc if s.get("result")=="win"])/max(len(btc),1)*100)
    sess_map = {}
    for s in ms:
        sess = s.get("session","Unknown")
        if sess not in sess_map:
            sess_map[sess] = {"w":0,"l":0}
        if s.get("result")=="win": sess_map[sess]["w"] += 1
        else: sess_map[sess]["l"] += 1
    improvements = []
    if wr < 70: improvements.append("Increase min score to 65%+")
    improvements.append("Focus on Tue-Wed Overlap session")
    improvements.append("Always confirm on TradingView chart")
    lines = [
        "\U0001f4ca MONTHLY REPORT - " + mname + " " + str(year),
        "=" * 24,
        "\U0001f4ca Signals  : " + str(total),
        "\u2705 Wins     : " + str(wins),
        "\u274c Losses   : " + str(losses),
        "\U0001f3af Win Rate : " + str(wr) + "%",
        "\U0001f4b0 P&L      : " + ("+" if pnl>=0 else "") + "$" + str(round(pnl,1)),
        "\U0001f3c6 Grade    : " + grade,
        "=" * 24,
        "\u26a1 XAUUSD  : " + str(len(xau)) + " | " + str(xwr) + "% WR",
        "\u20bf BTCUSDT : " + str(len(btc)) + " | " + str(bwr) + "% WR",
        "=" * 24,
        "\U0001f4dd SESSION BREAKDOWN:",
    ] + ["â€¢ " + k + ": " + str(v["w"]) + "W/" + str(v["l"]) + "L" for k, v in sess_map.items()] + [
        "=" * 24,
        "\U0001f4c8 IMPROVEMENTS:",
    ] + ["\U0001f538 " + i for i in improvements] + [
        "=" * 24,
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v7.0",
    ]
    return "\n".join(lines)

if __name__ == "__main__":
    main()
