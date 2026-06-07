#!/usr/bin/env python3
"""
Alpha Auto Agent v10.0 - COMPLETE & FINAL
XAUUSD: Twelve Data (primary) + Yahoo fallback
BTCUSDT: Binance + Bybit + Yahoo + Twelve Data fallbacks
TP1/TP2/TP3/SL Alerts
Morning 9AM + Evening 6PM views
Prime time 12:30PM-10:30PM IST har 15 min scan
Weekly Sunday 8PM + Monthly 1st 9AM reports
"""

import requests
import time
import datetime

# =======================================
# CONFIGURATION
# =======================================
BOT_TOKEN        = "8978957779:AAF8fNhxiaQw1VcNvMOnMClPd2alqVRjL1c"
TWELVE_DATA_KEY  = "6df2ea47705646f2aaf14fec76fc8b8b"
CHAT_ID          = "8867873147"
MIN_SCORE        = 70
COOLDOWN_HOURS   = 2
# =======================================

ASSETS = {
    "XAUUSD": {"sl": 6.5,  "vol_min": 1.5},
    "BTCUSD": {"sl": 175,  "vol_min": 2.0},
}

last_signal    = {"XAUUSD": 0, "BTCUSD": 0}
sig_count      = 0
sent_today     = {}
last_date      = None
last_scan_time = 0
signal_history = []
active_trades  = {}

_gold_cache      = None
_gold_cache_time = 0
_btc_cache       = None
_btc_cache_time  = 0

# =======================================
# LOGGING
# =======================================
def log(msg, level="INFO"):
    t = datetime.datetime.utcnow().strftime("%H:%M:%S")
    print("[" + t + " GMT] [" + level + "] " + msg)

# =======================================
# TIME
# =======================================
def get_ist():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

def get_session():
    now = datetime.datetime.utcnow()
    h   = now.hour + now.minute / 60
    day = now.weekday()
    if day >= 5:  return {"name": "Weekend",           "good": False}
    if h < 7:     return {"name": "Asian",             "good": False}
    if h < 10:    return {"name": "London Open",       "good": True}
    if h < 12:    return {"name": "London Mid",        "good": True}
    if h < 15:    return {"name": "London-NY Overlap", "good": True}
    if h < 17:    return {"name": "NY Open",           "good": True}
    if h < 20:    return {"name": "NY Mid",            "good": day != 4}
    return {"name": "Closed", "good": False}

def is_prime_time():
    ist = get_ist()
    h, m = ist.hour, ist.minute
    day  = ist.weekday()
    if day >= 5: return False
    after = (h == 12 and m >= 30) or h >= 13
    before = h < 22 or (h == 22 and m <= 30)
    return after and before

def reset_daily():
    global sent_today, last_date
    today = get_ist().date()
    if last_date != today:
        sent_today = {}
        last_date  = today
        log("Daily reset - " + str(today))

# =======================================
# FETCH GOLD - Twelve Data + Yahoo fallback
# =======================================
def fetch_gold_candles(limit=60):
    global _gold_cache, _gold_cache_time
    now_t = time.time()

    if _gold_cache and (now_t - _gold_cache_time) < 55 * 60:
        age = int((now_t - _gold_cache_time) / 60)
        log("Gold cache (" + str(age) + "min) | $" + str(float(_gold_cache[-1][4])))
        return _gold_cache[-limit:]

    # Primary: Twelve Data XAU/USD
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": "XAU/USD", "interval": "1h",
                    "outputsize": limit, "apikey": TWELVE_DATA_KEY},
            timeout=15)
        data = r.json()
        if data.get("status") != "error":
            values = list(reversed(data.get("values", [])))
            if len(values) >= 10:
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
                                    str(v.get("volume", "1000")), ts + 3600000])
                price = float(candles[-1][4])
                log("Gold Twelve Data: " + str(len(candles)) + " | $" + str(price))
                _gold_cache = candles
                _gold_cache_time = now_t
                return candles[-limit:]
    except Exception as e:
        log("Twelve Data Gold error: " + str(e), "WARN")

    # Fallback 1: Yahoo XAUUSD=X
    try:
        headers = {"User-Agent": "Mozilla/5.0 Chrome/91.0"}
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X",
            params={"interval": "1h", "range": "7d"},
            headers=headers, timeout=15)
        data   = r.json()
        result = data["chart"]["result"][0]
        ts     = result["timestamp"]
        q      = result["indicators"]["quote"][0]
        candles = []
        for i in range(len(ts)):
            o = q["open"][i]; h2 = q["high"][i]
            l = q["low"][i];  c  = q["close"][i]
            v = q.get("volume", [1000]*len(ts))[i]
            if None in (o, h2, l, c): continue
            t_ms = int(ts[i]) * 1000
            candles.append([t_ms,
                str(round(float(o),2)), str(round(float(h2),2)),
                str(round(float(l),2)), str(round(float(c),2)),
                str(int(v) if v else 1000), t_ms+3600000])
        if len(candles) >= 10:
            price = float(candles[-1][4])
            log("Gold Yahoo XAUUSD=X: " + str(len(candles)) + " | $" + str(price))
            _gold_cache = candles
            _gold_cache_time = now_t
            return candles[-limit:]
    except Exception as e:
        log("Yahoo XAUUSD=X error: " + str(e), "WARN")

    # Fallback 2: Yahoo GC=F
    try:
        headers = {"User-Agent": "Mozilla/5.0 Chrome/91.0"}
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
            params={"interval": "1h", "range": "7d"},
            headers=headers, timeout=15)
        data   = r.json()
        result = data["chart"]["result"][0]
        ts     = result["timestamp"]
        q      = result["indicators"]["quote"][0]
        candles = []
        for i in range(len(ts)):
            o = q["open"][i]; h2 = q["high"][i]
            l = q["low"][i];  c  = q["close"][i]
            v = q.get("volume", [1000]*len(ts))[i]
            if None in (o, h2, l, c): continue
            t_ms = int(ts[i]) * 1000
            candles.append([t_ms,
                str(round(float(o),2)), str(round(float(h2),2)),
                str(round(float(l),2)), str(round(float(c),2)),
                str(int(v) if v else 1000), t_ms+3600000])
        if len(candles) >= 10:
            price = float(candles[-1][4])
            log("Gold Yahoo GC=F: " + str(len(candles)) + " | $" + str(price))
            _gold_cache = candles
            _gold_cache_time = now_t
            return candles[-limit:]
    except Exception as e:
        log("Yahoo GC=F error: " + str(e), "WARN")

    if _gold_cache:
        log("Gold using old cache", "WARN")
        return _gold_cache[-limit:]

    log("Gold fetch FAILED!", "ERROR")
    return None

# =======================================
# FETCH BTC - 4 sources fallback
# =======================================
def fetch_btc_candles(limit=60):
    global _btc_cache, _btc_cache_time
    now_t = time.time()

    if _btc_cache and (now_t - _btc_cache_time) < 14 * 60:
        age = int((now_t - _btc_cache_time) / 60)
        log("BTC cache (" + str(age) + "min) | $" + str(float(_btc_cache[-1][4])))
        return _btc_cache

    # Primary: Binance
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1h", "limit": limit},
            timeout=10)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            price = float(data[-1][4])
            log("BTC Binance: " + str(len(data)) + " | $" + str(price))
            _btc_cache = data
            _btc_cache_time = now_t
            return data
    except Exception as e:
        log("Binance error: " + str(e), "WARN")

    # Fallback 1: Bybit
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/kline",
            params={"category": "linear", "symbol": "BTCUSDT",
                    "interval": "60", "limit": limit},
            timeout=10)
        data = r.json()
        if data.get("retCode") == 0:
            items = list(reversed(data["result"]["list"]))
            candles = []
            for item in items:
                candles.append([int(item[0]), item[1], item[2],
                                item[3], item[4], item[5], int(item[0])+3600000])
            if candles:
                price = float(candles[-1][4])
                log("BTC Bybit: " + str(len(candles)) + " | $" + str(price))
                _btc_cache = candles
                _btc_cache_time = now_t
                return candles
    except Exception as e:
        log("Bybit error: " + str(e), "WARN")

    # Fallback 2: Yahoo BTC-USD
    try:
        headers = {"User-Agent": "Mozilla/5.0 Chrome/91.0"}
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD",
            params={"interval": "1h", "range": "7d"},
            headers=headers, timeout=15)
        data   = r.json()
        result = data["chart"]["result"][0]
        ts     = result["timestamp"]
        q      = result["indicators"]["quote"][0]
        candles = []
        for i in range(len(ts)):
            o = q["open"][i]; h2 = q["high"][i]
            l = q["low"][i];  c  = q["close"][i]
            v = q.get("volume", [1000]*len(ts))[i]
            if None in (o, h2, l, c): continue
            t_ms = int(ts[i]) * 1000
            candles.append([t_ms,
                str(round(float(o),2)), str(round(float(h2),2)),
                str(round(float(l),2)), str(round(float(c),2)),
                str(int(v) if v else 1000), t_ms+3600000])
        if len(candles) >= 10:
            price = float(candles[-1][4])
            log("BTC Yahoo: " + str(len(candles)) + " | $" + str(price))
            _btc_cache = candles
            _btc_cache_time = now_t
            return candles
    except Exception as e:
        log("Yahoo BTC error: " + str(e), "WARN")

    # Fallback 3: Twelve Data BTC/USD
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": "BTC/USD", "interval": "1h",
                    "outputsize": limit, "apikey": TWELVE_DATA_KEY},
            timeout=15)
        data = r.json()
        if data.get("status") != "error":
            values = list(reversed(data.get("values", [])))
            if len(values) >= 10:
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
                                   str(v.get("volume", "1000")), ts+3600000])
                price = float(candles[-1][4])
                log("BTC Twelve Data: " + str(len(candles)) + " | $" + str(price))
                _btc_cache = candles
                _btc_cache_time = now_t
                return candles
    except Exception as e:
        log("Twelve Data BTC error: " + str(e), "WARN")

    if _btc_cache:
        log("BTC using old cache", "WARN")
        return _btc_cache

    log("BTC fetch FAILED!", "ERROR")
    return None

def get_candles(asset_key, limit=60):
    if asset_key == "XAUUSD":
        return fetch_gold_candles(limit)
    return fetch_btc_candles(limit)

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
    if not trs: return 1.0
    return sum(trs[-period:]) / min(len(trs), period)

def get_trend(candles):
    if not candles or len(candles) < 20:
        return "NEUTRAL", 0
    closes = [float(c[4]) for c in candles]
    e20    = calc_ema(closes, 20)
    e50    = calc_ema(closes, min(50, len(closes)-1))
    price  = closes[-1]
    rec_hi = max(float(c[2]) for c in candles[-5:])
    prv_hi = max(float(c[2]) for c in candles[-10:-5])
    rec_lo = min(float(c[3]) for c in candles[-5:])
    prv_lo = min(float(c[3]) for c in candles[-10:-5])
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
    s = bull - bear
    if s >= 3:    return "STRONG_BUY", s
    elif s >= 1:  return "BUY", s
    elif s <= -3: return "STRONG_SELL", s
    elif s <= -1: return "SELL", s
    return "NEUTRAL", 0

def detect_sweep(candles, fib382, direction, atr_val):
    if len(candles) < 6: return False, "Not enough data"
    recent  = candles[-8:]
    vols    = [float(c[5]) for c in recent]
    avg_vol = sum(vols[:-2]) / max(len(vols)-2, 1)
    buf     = atr_val * 0.3
    best    = 0; found = False; detail = "No sweep"
    for i in range(len(recent)-1):
        h2  = float(recent[i][2]); l = float(recent[i][3])
        vol = float(recent[i][5]); vr = vol/avg_vol if avg_vol > 0 else 1
        nxt = float(recent[i+1][4])
        if direction == "BUY":
            if l < fib382-buf and nxt > fib382:
                wick = fib382-l
                s = min(100, int(wick/atr_val*60 + vr*15))
                if s > best:
                    best=s; found=True
                    detail = "Wick "+str(round(wick,2))+" below | Vol "+str(round(vr,1))+"x"
        else:
            if h2 > fib382+buf and nxt < fib382:
                wick = h2-fib382
                s = min(100, int(wick/atr_val*60 + vr*15))
                if s > best:
                    best=s; found=True
                    detail = "Wick "+str(round(wick,2))+" above | Vol "+str(round(vr,1))+"x"
    return found, detail

def detect_choch(candles, direction, ema20):
    if len(candles) < 8: return False, "Not enough data"
    highs = [float(c[2]) for c in candles[-8:]]
    lows  = [float(c[3]) for c in candles[-8:]]
    prev  = float(candles[-2][4]); curr = float(candles[-1][4])
    ecb   = ema20 and prev < ema20 and curr > ema20
    ecs   = ema20 and prev > ema20 and curr < ema20
    if direction == "BUY":
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
# NEWS
# =======================================
def check_news():
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8)
        if r.status_code != 200: return True, "Safe"
        now = datetime.datetime.utcnow()
        for ev in r.json():
            if ev.get("impact") != "High": continue
            if ev.get("currency") not in ["USD","XAU","GBP","EUR"]: continue
            try:
                ev_str = ev.get("date","") + " " + ev.get("time","12:00am")
                ev_dt  = datetime.datetime.strptime(ev_str, "%Y-%m-%d %I:%M%p")
                diff   = (ev_dt - now).total_seconds() / 60
                if -30 <= diff <= 30:
                    return False, ev.get("title","") + " (" + str(int(diff)) + "min)"
            except: continue
        return True, "Safe"
    except:
        return True, "Safe"

def get_todays_news():
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8)
        if r.status_code != 200: return []
        ist   = get_ist()
        today = ist.date()
        news  = []
        for ev in r.json():
            if ev.get("impact") not in ["High","Medium"]: continue
            if ev.get("currency") not in ["USD","XAU","GBP","EUR","JPY"]: continue
            try:
                ev_date = datetime.datetime.strptime(ev.get("date",""), "%Y-%m-%d").date()
                if ev_date == today:
                    news.append({"title": ev.get("title",""), "time": ev.get("time",""),
                                 "currency": ev.get("currency",""), "impact": ev.get("impact","")})
            except: continue
        return news
    except:
        return []

# =======================================
# ANALYZE
# =======================================
def analyze(asset_key):
    cfg     = ASSETS[asset_key]
    candles = get_candles(asset_key, 60)
    if not candles:
        log(asset_key + " - No data", "ERROR")
        return None

    price = float(candles[-1][4])
    log(asset_key + " price: $" + str(price))

    trend, ts = get_trend(candles)
    if trend == "NEUTRAL":
        log(asset_key + " - Neutral, skip")
        return None

    direction = "BUY" if "BUY" in trend else "SELL"
    highs = [float(c[2]) for c in candles[-25:]]
    lows  = [float(c[3]) for c in candles[-25:]]
    sh, sl = max(highs), min(lows)
    rng    = sh - sl
    if rng == 0: return None

    fib382 = (sh-rng*0.382) if direction=="BUY" else (sl+rng*0.382)
    fib236 = (sh-rng*0.236) if direction=="BUY" else (sl+rng*0.236)
    atr_v  = calc_atr(candles, 14) or rng*0.02
    closes = [float(c[4]) for c in candles]
    ema20  = calc_ema(closes, 20) or price

    vols    = [float(c[5]) for c in candles]
    avg_vol = sum(vols[-20:-1])/19 if len(vols)>=20 else sum(vols[:-1])/max(len(vols)-1,1)
    vol_r   = vols[-1]/avg_vol if avg_vol > 0 else 0

    last = candles[-1]
    o, c_ = float(last[1]), float(last[4])
    h_, l_ = float(last[2]), float(last[3])
    csize = h_-l_
    body_pct = (abs(c_-o)/csize*100) if csize > 0 else 0

    session = get_session()
    buf     = atr_v * 1.5
    near382 = abs(price-fib382) <= buf
    near236 = abs(price-fib236) <= buf
    near_any= near382 or near236
    zone_nm = "38.2%" if near382 else "23.6%"

    sweep_ok, sweep_det = detect_sweep(candles, fib382, direction, atr_v)
    choch_ok, choch_det = detect_choch(candles, direction, ema20)
    ema_ok  = (c_ > ema20*0.999) if direction=="BUY" else (c_ < ema20*1.001)
    news_ok, news_det   = check_news()
    not_fri = not (datetime.datetime.utcnow().weekday()==4 and datetime.datetime.utcnow().hour>=15)

    checks = [
        {"label": "Trend (1H)",      "pass": abs(ts)>=1,           "w": 2},
        {"label": "Good Session",     "pass": session["good"],      "w": 2},
        {"label": "Near 38.2% Zone",  "pass": near_any,             "w": 2},
        {"label": "Liquidity Sweep",  "pass": sweep_ok,             "w": 2},
        {"label": "CHOCH Confirmed",  "pass": choch_ok,             "w": 1},
        {"label": "Full Body 60%+",   "pass": body_pct >= 60,       "w": 1},
        {"label": "Volume Spike",     "pass": vol_r >= cfg["vol_min"], "w": 1},
        {"label": "EMA 20 Aligned",   "pass": ema_ok,               "w": 1},
        {"label": "No High News",     "pass": news_ok,              "w": 1},
        {"label": "Not Friday Close", "pass": not_fri,              "w": 1},
    ]

    tw = sum(c["w"] for c in checks)
    pw = sum(c["w"] for c in checks if c["pass"])
    score = round(pw/tw*100)
    if not all(c["pass"] for c in checks if c["w"]==2):
        score = min(score, 65)

    sl_amt = cfg["sl"]
    entry  = price
    if direction == "BUY":
        sl_p=round(entry-sl_amt,2); tp1=round(entry+sl_amt*3,2)
        tp2=round(entry+sl_amt*4,2); tp3=round(entry+sl_amt*6,2)
    else:
        sl_p=round(entry+sl_amt,2); tp1=round(entry-sl_amt*3,2)
        tp2=round(entry-sl_amt*4,2); tp3=round(entry-sl_amt*6,2)

    return {
        "asset": asset_key, "trend": direction, "mtf_trend": trend,
        "score": score, "entry": round(entry,2), "sl_p": sl_p,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl_amt": sl_amt,
        "fib382": round(fib382,2), "fib236": round(fib236,2),
        "sh": round(sh,2), "sl_level": round(sl,2),
        "ema20": round(ema20,2), "vol_r": round(vol_r,2),
        "body_pct": round(body_pct,1), "atr": round(atr_v,2),
        "sweep_det": sweep_det, "choch_det": choch_det,
        "session": session, "checks": checks,
        "news_ok": news_ok, "zone_nm": zone_nm,
    }

# =======================================
# TP/SL HIT DETECTION
# =======================================
def check_tp_sl():
    if not active_trades: return
    for trade_id in list(active_trades.keys()):
        try:
            trade   = active_trades[trade_id]
            asset   = trade["asset"]
            candles = get_candles(asset, 10)
            if not candles: continue
            cur_hi = max(float(c[2]) for c in candles[-3:])
            cur_lo = min(float(c[3]) for c in candles[-3:])
            cur    = float(candles[-1][4])
            sym    = "XAUUSD" if asset=="XAUUSD" else "BTCUSDT"
            icon   = "\u26a1" if asset=="XAUUSD" else "\u20bf"

            if trade["trend"] == "BUY":
                if cur_lo <= trade["sl_p"]:
                    send("\n".join([
                        icon+" "+sym+" SL HIT \U0001f6d1",
                        "="*22,
                        "\U0001f4cd Entry : "+str(trade["entry"]),
                        "\U0001f6d1 SL hit: "+str(trade["sl_p"])+" @ $"+str(cur),
                        "\U0001f4b8 Loss  : -$"+str(trade["sl_amt"])+" (controlled!)",
                        "="*22,
                        "\u26a0 Part of trading - stay disciplined!",
                        "\U0001f4aa Next setup coming soon!",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
                    del active_trades[trade_id]
                elif cur_hi >= trade["tp3"] and not trade.get("tp3_hit"):
                    send("\n".join([
                        icon+" "+sym+" TP3 HIT! \U0001f3c6",
                        "="*22,
                        "\U0001f680 TP3 : "+str(trade["tp3"])+" HIT!",
                        "\u2705 Close FULL position!",
                        "FULL TARGET ACHIEVED! \U0001f525\U0001f525\U0001f525",
                        "\U0001f3c6 Perfect trade! \U0001f4aa",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
                    del active_trades[trade_id]
                elif cur_hi >= trade["tp2"] and not trade.get("tp2_hit"):
                    trade["tp2_hit"] = True
                    send("\n".join([
                        icon+" "+sym+" TP2 HIT! \U0001f929",
                        "="*22,
                        "\U0001f4cd Entry : "+str(trade["entry"]),
                        "\U0001f3af TP2   : "+str(trade["tp2"])+" HIT!",
                        "="*22,
                        "\u2705 Trail remaining 50%!",
                        "\U0001f680 TP3 open: "+str(trade["tp3"]),
                        "Amazing trade! \U0001f911",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
                elif cur_hi >= trade["tp1"] and not trade.get("tp1_hit"):
                    trade["tp1_hit"] = True
                    profit = round(abs(trade["tp1"]-trade["entry"]), 2)
                    send("\n".join([
                        icon+" "+sym+" TP1 HIT! \U0001f3af",
                        "="*22,
                        "\U0001f4cd Entry  : "+str(trade["entry"]),
                        "\U0001f3af TP1    : "+str(trade["tp1"])+" HIT!",
                        "\U0001f4b0 Profit : +$"+str(profit),
                        "="*22,
                        "\u2705 Close 50% position NOW!",
                        "\U0001f6e1 Move SL to entry: "+str(trade["entry"]),
                        "\U0001f3af TP2 next: "+str(trade["tp2"]),
                        "\U0001f680 TP3 next: "+str(trade["tp3"]),
                        "Excellent! Keep trailing! \U0001f525",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
            else:  # SELL
                if cur_hi >= trade["sl_p"]:
                    send("\n".join([
                        icon+" "+sym+" SL HIT \U0001f6d1",
                        "="*22,
                        "\U0001f4cd Entry : "+str(trade["entry"]),
                        "\U0001f6d1 SL hit: "+str(trade["sl_p"])+" @ $"+str(cur),
                        "\U0001f4b8 Loss  : -$"+str(trade["sl_amt"])+" (controlled!)",
                        "="*22,
                        "\u26a0 Part of trading - stay disciplined!",
                        "\U0001f4aa Next setup coming soon!",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
                    del active_trades[trade_id]
                elif cur_lo <= trade["tp3"] and not trade.get("tp3_hit"):
                    send("\n".join([
                        icon+" "+sym+" TP3 HIT! \U0001f3c6",
                        "="*22,
                        "\U0001f680 TP3 : "+str(trade["tp3"])+" HIT!",
                        "\u2705 Close FULL position!",
                        "FULL TARGET ACHIEVED! \U0001f525\U0001f525\U0001f525",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
                    del active_trades[trade_id]
                elif cur_lo <= trade["tp2"] and not trade.get("tp2_hit"):
                    trade["tp2_hit"] = True
                    send("\n".join([
                        icon+" "+sym+" TP2 HIT! \U0001f929",
                        "="*22,
                        "\U0001f4cd Entry : "+str(trade["entry"]),
                        "\U0001f3af TP2   : "+str(trade["tp2"])+" HIT!",
                        "="*22,
                        "\u2705 Trail remaining 50%!",
                        "\U0001f680 TP3 open: "+str(trade["tp3"]),
                        "Amazing trade! \U0001f911",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
                elif cur_lo <= trade["tp1"] and not trade.get("tp1_hit"):
                    trade["tp1_hit"] = True
                    profit = round(abs(trade["tp1"]-trade["entry"]), 2)
                    send("\n".join([
                        icon+" "+sym+" TP1 HIT! \U0001f3af",
                        "="*22,
                        "\U0001f4cd Entry  : "+str(trade["entry"]),
                        "\U0001f3af TP1    : "+str(trade["tp1"])+" HIT!",
                        "\U0001f4b0 Profit : +$"+str(profit),
                        "="*22,
                        "\u2705 Close 50% position NOW!",
                        "\U0001f6e1 Move SL to entry: "+str(trade["entry"]),
                        "\U0001f3af TP2 next: "+str(trade["tp2"]),
                        "\U0001f680 TP3 next: "+str(trade["tp3"]),
                        "Excellent! Keep trailing! \U0001f525",
                        "\U0001f4e2 @Alphagoldsigna",
                    ]))
        except Exception as e:
            log("TP/SL check error: " + str(e), "ERROR")

# =======================================
# BUILD MESSAGES
# =======================================
def build_signal(d):
    stars = "\u2b50\u2b50\u2b50" if d["score"]>=80 else "\u2b50\u2b50" if d["score"]>=65 else "\u2b50"
    trap  = "Seller's Trap \U0001f43b" if d["trend"]=="BUY" else "Buyer's Trap \U0001f403"
    sym   = "XAUUSD" if d["asset"]=="XAUUSD" else "BTCUSDT"
    icon  = "\u26a1" if d["asset"]=="XAUUSD" else "\u20bf"
    sig   = "\U0001f7e2\u2b06 BUY" if d["trend"]=="BUY" else "\U0001f534\u2b07 SELL"
    news  = "\u2705 Safe" if d["news_ok"] else "\u26a0 Risk"
    conf  = "HIGH \U0001f525" if d["score"]>=80 else "GOOD \u26a1" if d["score"]>=65 else "OK \u26a0"
    passed= "\n".join("  \u2705 "+c["label"] for c in d["checks"] if c["pass"])
    if d["trend"] == "BUY":
        logic = "\n".join([
            "\U0001f4ca 1H: "+d["mtf_trend"],
            "\U0001f4c8 Sharp bullish impulse. Zone: "+str(d["fib382"]),
            "\U0001f43b Sellers swept below zone TRAPPED!",
            "\U0001f3e6 Smart money BUY started",
            "\U0001f504 CHOCH: "+d["choch_det"],
            "\U0001f55f "+str(d["body_pct"])+"% body candle above EMA "+str(d["ema20"]),
            "\U0001f4a5 Volume "+str(d["vol_r"])+"x = Institutional BUY!",
            "\u23f0 Session: "+d["session"]["name"],
        ])
    else:
        logic = "\n".join([
            "\U0001f4ca 1H: "+d["mtf_trend"],
            "\U0001f4c9 Sharp bearish impulse. Zone: "+str(d["fib382"]),
            "\U0001f403 Buyers swept above zone TRAPPED!",
            "\U0001f3e6 Smart money SELL started",
            "\U0001f504 CHOCH: "+d["choch_det"],
            "\U0001f55f "+str(d["body_pct"])+"% body candle below EMA "+str(d["ema20"]),
            "\U0001f4a5 Volume "+str(d["vol_r"])+"x = Institutional SELL!",
            "\u23f0 Session: "+d["session"]["name"],
        ])
    return "\n".join([
        icon+" "+sym+" "+sig+" "+icon,
        "="*24,
        "\U0001f4cd Entry   : "+str(d["entry"]),
        "\U0001f6d1 SL      : "+str(d["sl_p"])+" (Max $"+str(d["sl_amt"])+")",
        "\U0001f3af TP1     : "+str(d["tp1"])+" (1:3) \u2192 Close 50%",
        "\U0001f3af TP2     : "+str(d["tp2"])+" (1:4) \u2192 Trail 50%",
        "\U0001f680 TP3     : "+str(d["tp3"])+" (1:6) \u2192 Extended",
        "="*24,
        "\U0001f9f2 Setup   : "+trap,
        "\U0001f4d0 Zone    : "+str(d["fib382"])+" ("+d["zone_nm"]+")",
        "\U0001f4cf Swing   : "+str(d["sl_level"])+" to "+str(d["sh"]),
        "\U0001f4a5 Volume  : "+str(d["vol_r"])+"x avg",
        "\U0001f55f Candle  : "+str(d["body_pct"])+"% body",
        "\U0001f4e1 ATR     : "+str(d["atr"]),
        "\u23f0 Session : "+d["session"]["name"],
        "\U0001f4f0 News    : "+news,
        "="*24,
        "\U0001f4cb TRADE LOGIC:",
        logic,
        "="*24,
        "\u2705 CONDITIONS:",
        passed,
        "="*24,
        "\U0001f4af Score   : "+str(d["score"])+"% "+stars,
        "\U0001f4aa Confidence: "+conf,
        "\u26a0  Max SL  : $"+str(d["sl_amt"])+" only!",
        "\U0001f4cc TP1 hit \u2192 Close 50% + Move SL to entry",
        "="*24,
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v10.0",
    ])

def build_view(time_of_day):
    ist = get_ist()
    if time_of_day == "morning":
        hdr = "\U0001f31e Good Morning Traders!"
        sub = "\U0001f4ca Morning Market Analysis"
    else:
        hdr = "\U0001f307 Good Evening Traders!"
        sub = "\U0001f4ca Evening Market Update"
    lines = [hdr, sub, "\U0001f550 "+ist.strftime("%I:%M %p")+" IST", "="*24]
    for asset_key in ASSETS:
        sym  = "XAUUSD" if asset_key=="XAUUSD" else "BTCUSDT"
        icon = "\u26a1" if asset_key=="XAUUSD" else "\u20bf"
        candles = get_candles(asset_key, 60)
        if not candles:
            lines += ["", icon+" "+sym+": Data unavailable \u26a0"]
            continue
        price = float(candles[-1][4])
        trend, ts = get_trend(candles)
        highs = [float(c[2]) for c in candles[-20:]]
        lows  = [float(c[3]) for c in candles[-20:]]
        sh, sl = max(highs), min(lows)
        rng    = sh - sl
        fib382 = sh - rng*0.382; fib236 = sh - rng*0.236
        closes = [float(c[4]) for c in candles]
        ema20  = calc_ema(closes, 20) or price
        ema50  = calc_ema(closes, 50) or price
        atr_v  = calc_atr(candles, 14) or 1
        if "STRONG_BUY" in trend:
            b_icon = "ðŸ“ˆðŸ“ˆ"; bias = "STRONG BULLISH"
            action="Buy dips at "+str(round(fib382,2)); do="\U0001f7e2 STRONG BUY BIAS"
        elif "BUY" in trend:
            b_icon="\U0001f4c8"; bias="BULLISH"
            action="Buy pullback to "+str(round(fib382,2)); do="\U0001f7e2 BUY BIAS"
        elif "STRONG_SELL" in trend:
            b_icon="\U0001f4c9\U0001f4c9"; bias="STRONG BEARISH"
            action="Sell rally at "+str(round(fib382,2)); do="\U0001f534 STRONG SELL BIAS"
        elif "SELL" in trend:
            b_icon="\U0001f4c9"; bias="BEARISH"
            action="Sell rally to "+str(round(fib382,2)); do="\U0001f534 SELL BIAS"
        else:
            b_icon="\u23f8"; bias="NEUTRAL"
            action="Wait for direction"; do="\U0001f7e1 NEUTRAL"
        lines += [
            "", icon+" "+sym+" "+b_icon, "\u2500"*20,
            "\U0001f4b0 Price     : "+str(price),
            "\U0001f4ca Trend     : "+bias,
            "\U0001f4cf EMA 20    : "+str(round(ema20,2)),
            "\U0001f4cf EMA 50    : "+str(round(ema50,2)),
            "\U0001f3af 38.2% Zone: "+str(round(fib382,2)),
            "\U0001f3af 23.6% Zone: "+str(round(fib236,2)),
            "\U0001f6e1 Support   : "+str(round(sl,2)),
            "\u26a0  Resistance: "+str(round(sh,2)),
            "\U0001f4e1 ATR       : "+str(round(atr_v,2)),
            "\u2714 "+do,
            "\U0001f4cc Action    : "+action,
        ]
    news_list = get_todays_news()
    lines += ["", "="*24, "\U0001f4f0 TODAY'S MAJOR NEWS:"]
    if news_list:
        for n in news_list[:6]:
            imp = "\U0001f534" if n["impact"]=="High" else "\U0001f7e1"
            lines.append(imp+" "+n["currency"]+" | "+n["title"]+" @ "+n["time"])
    else:
        lines.append("\u2705 No major news today!")
    lines += ["="*24, "\U0001f9e0 Strategy: 38.2% Liquidity Sweep",
              "\u23f3 Wait for sweep + confirmation",
              "\U0001f4e2 @Alphagoldsigna", "\U0001f916 Alpha Agent v10.0"]
    return "\n".join(lines)

def build_news_alert(news_list):
    ist = get_ist()
    lines = ["\U0001f6a8 MAJOR NEWS ALERT!", "\U0001f550 "+ist.strftime("%I:%M %p")+" IST", "="*24]
    for n in news_list:
        imp = "\U0001f534" if n["impact"]=="High" else "\U0001f7e1"
        lines.append(imp+" "+n["currency"]+" | "+n["title"]+" @ "+n["time"])
    lines += ["="*24, "\U0001f6d1 Avoid 30min before/after!",
              "\U0001f4b0 High volatility expected!", "\U0001f4e2 @Alphagoldsigna"]
    return "\n".join(lines)

def build_weekly():
    now  = datetime.datetime.utcnow()
    week = now.isocalendar()[1]
    ws   = [s for s in signal_history if s.get("week")==week and s.get("year")==now.year]
    total= len(ws); wins=len([s for s in ws if s.get("result")=="win"])
    losses=len([s for s in ws if s.get("result")=="loss"])
    wr   = round(wins/total*100) if total > 0 else 0
    pnl  = sum(s.get("pnl",0) for s in ws)
    grade= "A+" if wr>=80 else "A" if wr>=70 else "B+" if wr>=60 else "B" if wr>=50 else "C"
    xau  = [s for s in ws if s["asset"]=="XAUUSD"]
    btc  = [s for s in ws if s["asset"]=="BTCUSD"]
    xwr  = round(len([s for s in xau if s.get("result")=="win"])/max(len(xau),1)*100)
    bwr  = round(len([s for s in btc if s.get("result")=="win"])/max(len(btc),1)*100)
    edges= []
    if wr>=70: edges.append("Strategy working well!")
    if xwr>=70: edges.append("XAUUSD strong ("+str(xwr)+"%)")
    if bwr>=70: edges.append("BTCUSDT strong ("+str(bwr)+"%)")
    if not edges: edges.append("Focus on quality setups next week")
    return "\n".join([
        "\U0001f4ca WEEKLY REPORT - Week #"+str(week),
        "="*24,
        "\U0001f4ca Signals : "+str(total),
        "\u2705 Wins    : "+str(wins),
        "\u274c Losses  : "+str(losses),
        "\U0001f3af Win Rate: "+str(wr)+"%",
        "\U0001f4b0 P&L     : "+("+$" if pnl>=0 else "-$")+str(abs(round(pnl,1))),
        "\U0001f3c6 Grade   : "+grade,
        "="*24,
        "\u26a1 XAUUSD : "+str(len(xau))+" | "+str(xwr)+"%",
        "\u20bf BTC    : "+str(len(btc))+" | "+str(bwr)+"%",
        "="*24,
        "\U0001f4a1 EDGES:",
    ]+["\u2714 "+e for e in edges]+[
        "="*24,
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v10.0",
    ])

def build_monthly():
    now   = datetime.datetime.utcnow()
    mname = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][now.month-1]
    ms    = [s for s in signal_history if s.get("month")==now.month and s.get("year")==now.year]
    total = len(ms); wins=len([s for s in ms if s.get("result")=="win"])
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
        if sess not in sess_map: sess_map[sess] = {"w":0,"l":0}
        if s.get("result")=="win": sess_map[sess]["w"]+=1
        else: sess_map[sess]["l"]+=1
    return "\n".join([
        "\U0001f4ca MONTHLY REPORT - "+mname+" "+str(now.year),
        "="*24,
        "\U0001f4ca Signals : "+str(total),
        "\u2705 Wins    : "+str(wins),
        "\u274c Losses  : "+str(losses),
        "\U0001f3af Win Rate: "+str(wr)+"%",
        "\U0001f4b0 P&L     : "+("+$" if pnl>=0 else "-$")+str(abs(round(pnl,1))),
        "\U0001f3c6 Grade   : "+grade,
        "="*24,
        "\u26a1 XAUUSD : "+str(len(xau))+" | "+str(xwr)+"%",
        "\u20bf BTC    : "+str(len(btc))+" | "+str(bwr)+"%",
        "="*24,
        "\U0001f4dd SESSIONS:",
    ]+["â€¢ "+k+": "+str(v["w"])+"W/"+str(v["l"])+"L" for k,v in sess_map.items()]+[
        "="*24,
        "\U0001f4e2 @Alphagoldsigna",
        "\U0001f916 Alpha Agent v10.0",
    ])

# =======================================
# SEND
# =======================================
def send(msg):
    try:
        r = requests.post(
            "https://api.telegram.org/bot"+BOT_TOKEN+"/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10)
        d = r.json()
        if d.get("ok"):
            log("Sent!", "SUCCESS")
            return True
        log("Telegram: "+str(d.get("description","")), "ERROR")
        return False
    except Exception as e:
        log("Send error: "+str(e), "ERROR")
        return False

# =======================================
# SCAN
# =======================================
def run_scan(label=""):
    global sig_count
    log("=== SCAN "+label+" ===")
    for asset_key in ASSETS:
        try:
            data = analyze(asset_key)
            if not data:
                log(asset_key+" - No setup")
                continue
            log(asset_key+" | "+data["trend"]+" | Score:"+str(data["score"])+"% | $"+str(data["entry"]))
            if data["score"] >= MIN_SCORE:
                now_t = time.time()
                if now_t - last_signal[asset_key] > COOLDOWN_HOURS*3600:
                    if send(build_signal(data)):
                        last_signal[asset_key] = now_t
                        sig_count += 1
                        trade_id = asset_key+"_"+str(int(now_t))
                        active_trades[trade_id] = {
                            "asset":   asset_key,
                            "trend":   data["trend"],
                            "entry":   data["entry"],
                            "sl_p":    data["sl_p"],
                            "tp1":     data["tp1"],
                            "tp2":     data["tp2"],
                            "tp3":     data["tp3"],
                            "sl_amt":  data["sl_amt"],
                            "tp1_hit": False,
                            "tp2_hit": False,
                            "tp3_hit": False,
                        }
                        dt = datetime.datetime.utcnow()
                        signal_history.append({
                            "asset":   asset_key, "trend": data["trend"],
                            "entry":   data["entry"], "score": data["score"],
                            "session": data["session"]["name"],
                            "result":  "pending", "pnl": 0,
                            "week":    dt.isocalendar()[1],
                            "month":   dt.month, "year": dt.year,
                        })
                        log("Signal #"+str(sig_count)+" + TP/SL tracking started!", "SUCCESS")
                else:
                    rem = int((COOLDOWN_HOURS*3600-(time.time()-last_signal[asset_key]))/60)
                    log(asset_key+" cooldown: "+str(rem)+"min")
            else:
                failed = [c["label"] for c in data["checks"] if not c["pass"]]
                log(asset_key+" "+str(data["score"])+"% | Failed: "+", ".join(failed[:3]))
            time.sleep(2)
        except Exception as e:
            log(asset_key+" error: "+str(e), "ERROR")

# =======================================
# STARTUP
# =======================================
def startup():
    send("\n".join([
        "\U0001f916 Alpha Auto Agent v10.0 LIVE! \U0001f680",
        "",
        "\u2705 Gold: Twelve Data + Yahoo fallback",
        "\u2705 BTC: Binance + Bybit + Yahoo + TD",
        "\u2705 TP1/TP2/TP3 + SL Alerts ACTIVE!",
        "\u2705 NO API LIMITS!",
        "",
        "\U0001f4cb SCHEDULE (IST):",
        "\U0001f31e 9:00 AM    - Morning View + News",
        "\U0001f525 12:30 PM   - Prime Time START",
        "\U0001f50d Every 15min - Signal Scan",
        "\U0001f307 6:00 PM    - Evening View + News",
        "\U0001f50d Continue   - 15min scans till 10:30 PM",
        "\U0001f4ca Sunday 8PM - Weekly Report",
        "\U0001f4ca 1st Month  - Monthly Report",
        "",
        "\U0001f3af Min Score: 70%+",
        "\u23f0 Cooldown: 2hr per asset",
        "\U0001f4e2 @Alphagoldsigna",
        "Let's go! \U0001f4b0\U0001f525",
    ]))

# =======================================
# MAIN LOOP
# =======================================
def main():
    global last_scan_time
    log("="*40)
    log("ALPHA AUTO AGENT v10.0 STARTING")
    log("Gold: TD+Yahoo | BTC: Binance+Bybit+Yahoo+TD")
    log("Prime Time: 12:30PM-10:30PM IST | 15min scan")
    log("TP1/TP2/TP3/SL Alerts ACTIVE")
    log("="*40)
    startup()

    while True:
        try:
            reset_daily()
            ist   = get_ist()
            h, m  = ist.hour, ist.minute
            now_t = time.time()

            # Morning View 9:00 AM
            if h==9 and m<5 and "morning" not in sent_today:
                send(build_view("morning"))
                sent_today["morning"] = True
                news = [n for n in get_todays_news() if n["impact"]=="High"]
                if news: send(build_news_alert(news))
                sent_today["morning_news"] = True
                log("Morning view sent!")

            # Evening View 6:00 PM
            elif h==18 and m<5 and "evening" not in sent_today:
                send(build_view("evening"))
                sent_today["evening"] = True
                news = [n for n in get_todays_news() if n["impact"]=="High"]
                if news: send(build_news_alert(news))
                sent_today["evening_news"] = True
                log("Evening view sent!")

            # Weekly Report Sunday 8PM
            elif ist.weekday()==6 and h==20 and m<5 and "weekly" not in sent_today:
                send(build_weekly())
                sent_today["weekly"] = True
                log("Weekly report sent!")

            # Monthly Report 1st of month 9AM
            elif ist.day==1 and h==9 and 5<=m<10 and "monthly" not in sent_today:
                send(build_monthly())
                sent_today["monthly"] = True
                log("Monthly report sent!")

            # Prime Time: 12:30 PM to 10:30 PM IST - Har 15 min
            if is_prime_time():
                # Check TP/SL hits
                check_tp_sl()

                if now_t - last_scan_time >= 15*60:
                    sess  = get_session()
                    label = str(h)+":"+str(m).zfill(2)+" IST | "+sess["name"]
                    run_scan(label)
                    last_scan_time = now_t
                else:
                    rem = int((15*60-(now_t-last_scan_time))/60)
                    log("IST "+str(h)+":"+str(m).zfill(2)+" | Next scan: "+str(rem)+"min | Signals:"+str(sig_count))
            else:
                # Outside prime time - still check TP/SL
                if active_trades:
                    check_tp_sl()
                log("IST "+str(h)+":"+str(m).zfill(2)+" | Not prime time | Signals:"+str(sig_count))

        except Exception as e:
            log("Error: "+str(e), "ERROR")

        time.sleep(60)

if __name__ == "__main__":
    main()
