#!/usr/bin/env python3
"""
Alpha Auto Agent v5.0
XAUUSD (Twelve Data REAL) + BTCUSDT (Binance REAL)
Features:
- TP/SL hit alerts on Telegram
- Morning + Evening market view (IST)
- Strategy-based analysis
- 38.2% Liquidity Sweep
"""

import requests
import time
import datetime

# =======================================
# CONFIGURATION
# =======================================
BOT_TOKEN         = "8807619711:AAEKh0KabxZwHizYel5I3yrTwrqACdZXsow"
TWELVE_DATA_KEY   = "6df2ea47705646f2aaf14fec76fc8b8b"
CHAT_ID           = "8867873147"
SCAN_INTERVAL_MIN = 5
MIN_SCORE         = 70
COOLDOWN_HOURS    = 2

# Morning view IST = 09:00 = 03:30 GMT
# Evening view IST = 18:00 = 12:30 GMT
MORNING_VIEW_HOUR_GMT = 3
MORNING_VIEW_MIN_GMT  = 30
EVENING_VIEW_HOUR_GMT = 12
EVENING_VIEW_MIN_GMT  = 30
# =======================================

ASSETS = {
    "XAUUSD": {"sl": 6.5,  "vol_min": 2.0, "is_gold": True},
    "BTCUSD": {"sl": 175,  "vol_min": 3.0, "is_gold": False, "sym": "BTCUSDT"},
}

last_signal      = {"XAUUSD": 0, "BTCUSD": 0}
active_trades    = {}   # Tracks open trades for TP/SL alerts
scan_count       = 0
sig_count        = 0
morning_sent     = False
evening_sent     = False
last_view_date   = None

# =======================================
# LOGGING
# =======================================
def log(msg, level="INFO"):
    t = datetime.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{t} GMT] [{level}] {msg}")

# =======================================
# SESSION
# =======================================
def get_session():
    now = datetime.datetime.utcnow()
    h   = now.hour + now.minute / 60
    day = now.weekday()
    if day >= 5:
        return {"name": "Weekend",           "good": False}
    if 0  <= h <  7:
        return {"name": "Asian",             "good": False}
    if 7  <= h < 10:
        return {"name": "London Open",       "good": True}
    if 10 <= h < 12:
        return {"name": "London Mid",        "good": True}
    if 12 <= h < 15:
        return {"name": "London-NY Overlap", "good": True}
    if 15 <= h < 17:
        return {"name": "NY Open",           "good": True}
    if 17 <= h < 20:
        return {"name": "NY Mid",            "good": day != 4}
    return {"name": "Closed",                "good": False}

# =======================================
# FETCH CANDLES
# =======================================
def fetch_gold(interval, limit=60):
    interval_map = {
        "5m": "5min", "15m": "15min",
        "1h": "1h",   "4h": "4h",   "1d": "1day"
    }
    td_int = interval_map.get(interval, "5min")
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol":     "XAU/USD",
                "interval":   td_int,
                "outputsize": limit,
                "apikey":     TWELVE_DATA_KEY,
            },
            timeout=12)
        data = r.json()
        if data.get("status") == "error":
            log(f"Twelve Data: {data.get('message')}", "ERROR")
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
                            str(v.get("volume", "1000")), ts+60000])
        log(f"Gold candles: {len(candles)} ({td_int})", "INFO")
        return candles
    except Exception as e:
        log(f"Twelve Data error: {e}", "ERROR")
        return None

def fetch_btc(interval, limit=60):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": interval, "limit": limit},
            timeout=10)
        data = r.json()
        return data if isinstance(data, list) and len(data) > 0 else None
    except Exception as e:
        log(f"Binance error: {e}", "ERROR")
        return None

def get_candles(asset_key, interval, limit=60):
    return fetch_gold(interval, limit) if ASSETS[asset_key]["is_gold"] \
           else fetch_btc(interval, limit)

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
# MTF TREND
# =======================================
def get_mtf_trend(asset_key):
    scores = []
    for interval in ["1d", "4h", "1h"]:
        candles = get_candles(asset_key, interval, 30)
        if not candles or len(candles) < 15:
            continue
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
        scores.append(1 if bull > bear else -1 if bear > bull else 0)
    if not scores:
        return "NEUTRAL", 0
    total = sum(scores)
    if total >= 2:    return "STRONG_BUY", total
    elif total == 1:  return "BUY", total
    elif total <= -2: return "STRONG_SELL", total
    elif total == -1: return "SELL", total
    return "NEUTRAL", 0

# =======================================
# SWEEP + CHOCH
# =======================================
def detect_sweep(candles, fib382, trend, atr_val):
    if len(candles) < 6:
        return False, "Not enough data"
    recent  = candles[-8:]
    vols    = [float(c[5]) for c in recent]
    avg_vol = sum(vols[:-2]) / max(len(vols)-2, 1)
    buf     = atr_val * 0.3
    best    = 0
    detail  = "No sweep"
    found   = False
    for i in range(len(recent)-1):
        h   = float(recent[i][2])
        l   = float(recent[i][3])
        vol = float(recent[i][5])
        vr  = vol / avg_vol if avg_vol > 0 else 1
        nxt = float(recent[i+1][4])
        if trend == "BUY":
            if l < fib382-buf and nxt > fib382:
                wick = fib382 - l
                s = min(100, int(wick/atr_val*60 + vr*15))
                if s > best:
                    best=s; found=True
                    detail = f"Wick {wick:.2f} below zone, Vol {vr:.1f}x"
        else:
            if h > fib382+buf and nxt < fib382:
                wick = h - fib382
                s = min(100, int(wick/atr_val*60 + vr*15))
                if s > best:
                    best=s; found=True
                    detail = f"Wick {wick:.2f} above zone, Vol {vr:.1f}x"
    return found, detail

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
        if hl and bh:   return True, "Higher Low + Break of High"
        if hl:          return True, "Higher Low formed"
        if ecb:         return True, "EMA 20 Bullish Cross"
        return False, "No CHOCH"
    else:
        lh = max(highs[-3:]) < max(highs[-6:-3])
        bl = min(lows[-3:]) < min(lows[-6:-3])
        if lh and bl:   return True, "Lower High + Break of Low"
        if lh:          return True, "Lower High formed"
        if ecs:         return True, "EMA 20 Bearish Cross"
        return False, "No CHOCH"

# =======================================
# NEWS CHECK
# =======================================
def check_news():
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8)
        if r.status_code != 200:
            return True, "Safe"
        now = datetime.datetime.utcnow()
        for ev in r.json():
            if ev.get("impact") != "High":
                continue
            if ev.get("currency") not in ["USD", "XAU"]:
                continue
            try:
                ev_str = ev.get("date","") + " " + ev.get("time","12:00am")
                ev_dt  = datetime.datetime.strptime(ev_str, "%Y-%m-%d %I:%M%p")
                diff   = (ev_dt - now).total_seconds() / 60
                if -30 <= diff <= 30:
                    return False, f"{ev.get('title')} ({int(diff)}min)"
            except:
                continue
        return True, "Safe"
    except:
        return True, "Safe"

# =======================================
# ANALYZE
# =======================================
def analyze(asset_key):
    cfg   = ASSETS[asset_key]
    c1h   = get_candles(asset_key, "1h", 60)
    c5m   = get_candles(asset_key, "5m", 60)
    if not c1h or not c5m:
        return None

    price            = float(c5m[-1][4])
    mtf_trend, mtf_s = get_mtf_trend(asset_key)
    if mtf_trend == "NEUTRAL":
        return None

    trend  = "BUY" if "BUY" in mtf_trend else "SELL"
    highs  = [float(c[2]) for c in c1h[-25:]]
    lows   = [float(c[3]) for c in c1h[-25:]]
    sh, sl = max(highs), min(lows)
    rng    = sh - sl
    if rng == 0:
        return None

    fib382   = (sh - rng*0.382) if trend=="BUY" else (sl + rng*0.382)
    fib236   = (sh - rng*0.236) if trend=="BUY" else (sl + rng*0.236)
    atr_val  = calc_atr(c1h, 14) or rng*0.02
    closes5m = [float(c[4]) for c in c5m]
    ema20    = calc_ema(closes5m, 20) or price
    vols     = [float(c[5]) for c in c5m]
    avg_vol  = sum(vols[-20:-1])/19 if len(vols)>=20 else sum(vols[:-1])/max(len(vols)-1,1)
    vol_r    = vols[-1]/avg_vol if avg_vol > 0 else 0
    last     = c5m[-1]
    o, c_    = float(last[1]), float(last[4])
    h_, l_   = float(last[2]), float(last[3])
    csize    = h_ - l_
    body_pct = (abs(c_-o)/csize*100) if csize > 0 else 0
    session  = get_session()
    buf      = atr_val * 1.5
    near382  = abs(price-fib382) <= buf
    near236  = abs(price-fib236) <= buf
    near_any = near382 or near236
    zone_nm  = "38.2%" if near382 else "23.6%"
    sweep_ok, sweep_det = detect_sweep(c5m, fib382, trend, atr_val)
    choch_ok, choch_det = detect_choch(c5m, trend, ema20)
    ema_ok   = (c_ > ema20*0.999) if trend=="BUY" else (c_ < ema20*1.001)
    news_ok, news_det   = check_news()
    not_fri  = not (datetime.datetime.utcnow().weekday()==4 and
                    datetime.datetime.utcnow().hour>=15)

    checks = [
        {"label": "MTF Trend (D+4H+1H)", "pass": abs(mtf_s)>=1, "w": 2},
        {"label": "Good Session",         "pass": session["good"], "w": 2},
        {"label": "Near 38.2% Zone",      "pass": near_any,       "w": 2},
        {"label": "Liquidity Sweep",      "pass": sweep_ok,       "w": 2},
        {"label": "CHOCH Confirmed",      "pass": choch_ok,       "w": 1},
        {"label": "Full Body 60%+",       "pass": body_pct>=60,   "w": 1},
        {"label": "Volume Spike",         "pass": vol_r>=cfg["vol_min"], "w": 1},
        {"label": "EMA 20 Aligned",       "pass": ema_ok,         "w": 1},
        {"label": "No High News",         "pass": news_ok,        "w": 1},
        {"label": "Not Friday Close",     "pass": not_fri,        "w": 1},
    ]
    total_w  = sum(c["w"] for c in checks)
    passed_w = sum(c["w"] for c in checks if c["pass"])
    score    = round(passed_w/total_w*100)
    if not all(c["pass"] for c in checks if c["w"]==2):
        score = min(score, 65)

    sl_amt = cfg["sl"]
    entry  = price
    if trend == "BUY":
        sl_p = round(entry-sl_amt, 2)
        tp1  = round(entry+sl_amt*3, 2)
        tp2  = round(entry+sl_amt*4, 2)
        tp3  = round(entry+sl_amt*6, 2)
    else:
        sl_p = round(entry+sl_amt, 2)
        tp1  = round(entry-sl_amt*3, 2)
        tp2  = round(entry-sl_amt*4, 2)
        tp3  = round(entry-sl_amt*6, 2)

    return {
        "asset": asset_key, "trend": trend,
        "mtf_trend": mtf_trend, "score": score,
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
# CHECK TP/SL HIT
# =======================================
def check_tp_sl_hits():
    """Check if any active trade hit TP or SL"""
    if not active_trades:
        return
    for trade_id, trade in list(active_trades.items()):
        asset   = trade["asset"]
        c5m     = get_candles(asset, "5m", 5)
        if not c5m:
            continue
        cur_hi  = max(float(c[2]) for c in c5m[-3:])
        cur_lo  = min(float(c[3]) for c in c5m[-3:])
        sym     = "XAUUSD" if asset=="XAUUSD" else "BTCUSDT"
        cur_price = float(c5m[-1][4])

        if trade["trend"] == "BUY":
            if cur_lo <= trade["sl_p"]:
                msg = build_alert_msg(trade, "SL_HIT", cur_price)
                send(msg)
                del active_trades[trade_id]
                log(f"{asset} SL HIT at {cur_price}", "INFO")
            elif cur_hi >= trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"] = True
                msg = build_alert_msg(trade, "TP1_HIT", trade["tp1"])
                send(msg)
                log(f"{asset} TP1 HIT at {trade['tp1']}", "SUCCESS")
            elif cur_hi >= trade["tp2"] and not trade.get("tp2_hit"):
                trade["tp2_hit"] = True
                msg = build_alert_msg(trade, "TP2_HIT", trade["tp2"])
                send(msg)
                log(f"{asset} TP2 HIT at {trade['tp2']}", "SUCCESS")
            elif cur_hi >= trade["tp3"]:
                msg = build_alert_msg(trade, "TP3_HIT", trade["tp3"])
                send(msg)
                del active_trades[trade_id]
                log(f"{asset} TP3 HIT at {trade['tp3']}", "SUCCESS")
        else:
            if cur_hi >= trade["sl_p"]:
                msg = build_alert_msg(trade, "SL_HIT", cur_price)
                send(msg)
                del active_trades[trade_id]
                log(f"{asset} SL HIT at {cur_price}", "INFO")
            elif cur_lo <= trade["tp1"] and not trade.get("tp1_hit"):
                trade["tp1_hit"] = True
                msg = build_alert_msg(trade, "TP1_HIT", trade["tp1"])
                send(msg)
                log(f"{asset} TP1 HIT at {trade['tp1']}", "SUCCESS")
            elif cur_lo <= trade["tp2"] and not trade.get("tp2_hit"):
                trade["tp2_hit"] = True
                msg = build_alert_msg(trade, "TP2_HIT", trade["tp2"])
                send(msg)
                log(f"{asset} TP2 HIT at {trade['tp2']}", "SUCCESS")
            elif cur_lo <= trade["tp3"]:
                msg = build_alert_msg(trade, "TP3_HIT", trade["tp3"])
                send(msg)
                del active_trades[trade_id]
                log(f"{asset} TP3 HIT at {trade['tp3']}", "SUCCESS")

def build_alert_msg(trade, alert_type, price):
    sym = "XAUUSD" if trade["asset"]=="XAUUSD" else "BTCUSDT"
    alert_msgs = {
        "TP1_HIT": f"TP1 HIT - {sym}\n\nTP1 {trade['tp1']} reached!\nClose 50% position now\nMove SL to breakeven: {trade['entry']}\n\nEntry was: {trade['entry']}\nProfit: +${round(abs(trade['tp1']-trade['entry']) * 1, 2)}\n\n@Alphagoldsigna",
        "TP2_HIT": f"TP2 HIT - {sym}\n\nTP2 {trade['tp2']} reached!\nTrail remaining 50%\nExcellent trade!\n\nEntry was: {trade['entry']}\n\n@Alphagoldsigna",
        "TP3_HIT": f"TP3 HIT - {sym}\n\nTP3 {trade['tp3']} reached!\nFull target achieved!\nClose remaining position\n\nEntry was: {trade['entry']}\n\n@Alphagoldsigna",
        "SL_HIT":  f"SL HIT - {sym}\n\nSL {trade['sl_p']} hit at {price}\nMax loss: ${trade['sl_amt']}\nPart of trading - next setup coming!\n\nEntry was: {trade['entry']}\n\n@Alphagoldsigna",
    }
    return alert_msgs.get(alert_type, "Alert")

# =======================================
# MORNING + EVENING MARKET VIEW
# =======================================
def build_market_view(time_of_day):
    """Build morning/evening market analysis for both assets"""
    lines = []
    ist_time = (datetime.datetime.utcnow() +
                datetime.timedelta(hours=5, minutes=30)).strftime("%I:%M %p")

    header = "GOOD MORNING" if time_of_day == "morning" else "GOOD EVENING"
    lines.append(f"{header} - Market View")
    lines.append(f"Time: {ist_time} IST")
    lines.append("=" * 25)

    for asset_key in ASSETS:
        sym  = "XAUUSD" if asset_key=="XAUUSD" else "BTCUSDT"
        c1h  = get_candles(asset_key, "1h", 60)
        c4h  = get_candles(asset_key, "4h", 30)
        c1d  = get_candles(asset_key, "1d", 10)

        if not c1h:
            lines.append(f"\n{sym}: Data unavailable")
            continue

        # Current price
        price = float(c1h[-1][4])

        # MTF Trend
        mtf_trend, mtf_s = get_mtf_trend(asset_key)

        # Fib levels
        highs = [float(c[2]) for c in c1h[-20:]]
        lows  = [float(c[3]) for c in c1h[-20:]]
        sh, sl = max(highs), min(lows)
        rng   = sh - sl
        fib382 = sh - rng*0.382
        fib236 = sh - rng*0.236

        # EMA
        closes = [float(c[4]) for c in c1h]
        ema20  = calc_ema(closes, 20) or price
        ema50  = calc_ema(closes, 50) or price

        # ATR
        atr_val = calc_atr(c1h, 14) or 1

        # Price vs EMA
        above_ema = price > ema20

        # Session
        sess = get_session()

        # Direction bias
        if "STRONG_BUY" in mtf_trend:
            bias     = "STRONG BULLISH"
            strategy = "Look for BUY setups at 38.2% zone"
            action   = "Buy dips, especially at " + str(round(fib382, 2))
        elif "BUY" in mtf_trend:
            bias     = "BULLISH"
            strategy = "Prefer BUY setups"
            action   = "Buy on pullback to " + str(round(fib382, 2))
        elif "STRONG_SELL" in mtf_trend:
            bias     = "STRONG BEARISH"
            strategy = "Look for SELL setups at 38.2% zone"
            action   = "Sell rallies, especially at " + str(round(fib382, 2))
        elif "SELL" in mtf_trend:
            bias     = "BEARISH"
            strategy = "Prefer SELL setups"
            action   = "Sell on rally to " + str(round(fib382, 2))
        else:
            bias     = "NEUTRAL"
            strategy = "Wait for clear direction"
            action   = "No trade - sideways market"

        lines.append(f"\n{sym} Analysis")
        lines.append("-" * 20)
        lines.append(f"Price    : {price}")
        lines.append(f"Trend    : {bias}")
        lines.append(f"EMA 20   : {round(ema20, 2)}")
        lines.append(f"EMA 50   : {round(ema50, 2)}")
        lines.append(f"38.2% Zone: {round(fib382, 2)}")
        lines.append(f"23.6% Zone: {round(fib236, 2)}")
        lines.append(f"ATR      : {round(atr_val, 2)}")
        lines.append(f"Strategy : {strategy}")
        lines.append(f"Action   : {action}")

        # Key levels
        lines.append(f"Support  : {round(sl, 2)}")
        lines.append(f"Resistance: {round(sh, 2)}")

    lines.append("\n" + "=" * 25)
    lines.append("Strategy: 38.2% Liquidity Sweep")
    lines.append("Wait for sweep + confirmation")
    lines.append("Min Score: 70% for entry")
    lines.append("@Alphagoldsigna")
    lines.append("Alpha Agent v5.0")
    return "\n".join(lines)

def check_and_send_market_view():
    """Send morning and evening market view at scheduled times"""
    global morning_sent, evening_sent, last_view_date
    now     = datetime.datetime.utcnow()
    today   = now.date()

    # Reset flags at midnight
    if last_view_date != today:
        morning_sent   = False
        evening_sent   = False
        last_view_date = today

    h, m = now.hour, now.minute

    # Morning view at 03:30 GMT = 09:00 IST
    if h == MORNING_VIEW_HOUR_GMT and m >= MORNING_VIEW_MIN_GMT and not morning_sent:
        log("Sending morning market view...", "INFO")
        msg = build_market_view("morning")
        if send(msg):
            morning_sent = True
            log("Morning view sent!", "SUCCESS")

    # Evening view at 12:30 GMT = 18:00 IST
    if h == EVENING_VIEW_HOUR_GMT and m >= EVENING_VIEW_MIN_GMT and not evening_sent:
        log("Sending evening market view...", "INFO")
        msg = build_market_view("evening")
        if send(msg):
            evening_sent = True
            log("Evening view sent!", "SUCCESS")

# =======================================
# BUILD SIGNAL MESSAGE
# =======================================
def build_msg(d):
    stars = "***" if d["score"]>=85 else "**" if d["score"]>=70 else "*"
    trap  = "Sellers Trap" if d["trend"]=="BUY" else "Buyers Trap"
    sym   = "XAUUSD" if d["asset"]=="XAUUSD" else "BTCUSDT"
    news  = "Safe" if d["news_ok"] else "Risk"
    passed = "\n".join("  OK " + c["label"] for c in d["checks"] if c["pass"])

    if d["trend"] == "BUY":
        logic = "\n".join([
            f"1. {d['mtf_trend']} trend Daily+4H+1H confirmed.",
            f"2. 1H sharp bullish impulse. Fib zone: {d['fib382']}.",
            f"3. Sellers swept liquidity below zone ({trap})!",
            f"4. Smart money trapped sellers - buying started.",
            f"5. CHOCH: {d['choch_det']}",
            f"6. Strong {d['body_pct']}% body candle above EMA {d['ema20']}.",
            f"7. Volume {d['vol_r']}x spike - institutional buying.",
            f"8. Session: {d['session']['name']} - prime time.",
        ])
    else:
        logic = "\n".join([
            f"1. {d['mtf_trend']} trend Daily+4H+1H confirmed.",
            f"2. 1H sharp bearish impulse. Fib zone: {d['fib382']}.",
            f"3. Buyers swept liquidity above zone ({trap})!",
            f"4. Smart money trapped buyers - selling started.",
            f"5. CHOCH: {d['choch_det']}",
            f"6. Strong {d['body_pct']}% body candle below EMA {d['ema20']}.",
            f"7. Volume {d['vol_r']}x spike - institutional selling.",
            f"8. Session: {d['session']['name']} - prime time.",
        ])

    lines = [
        f"{sym} {d['trend']} SIGNAL {stars}",
        "=" * 22,
        f"Entry   : {d['entry']}",
        f"SL      : {d['sl_p']} (${d['sl_amt']})",
        f"TP1     : {d['tp1']} (1:3) Close 50%",
        f"TP2     : {d['tp2']} (1:4) Trail 50%",
        f"TP3     : {d['tp3']} (1:6) Extended",
        "=" * 22,
        f"Trend   : {d['mtf_trend']}",
        f"Setup   : {trap} @ {d['zone_nm']}",
        f"Zone    : {d['fib382']}",
        f"Swing   : {d['sl_level']} to {d['sh']}",
        f"Volume  : {d['vol_r']}x avg",
        f"Candle  : {d['body_pct']}% body",
        f"ATR     : {d['atr']}",
        f"Session : {d['session']['name']}",
        f"News    : {news}",
        "=" * 22,
        "TRADE LOGIC:",
        logic,
        "=" * 22,
        "CONDITIONS MET:",
        passed,
        "=" * 22,
        f"Score   : {d['score']}% {stars}",
        f"Max SL  : ${d['sl_amt']} only",
        "TP1 hit = Close 50% + Move SL to entry",
        "TP2 hit = Trail remaining 50%",
        "@Alphagoldsigna",
        "Alpha Agent v5.0",
    ]
    return "\n".join(lines)

# =======================================
# SEND TELEGRAM
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
        log(f"Telegram: {d.get('description')}", "ERROR")
        return False
    except Exception as e:
        log(f"Send error: {e}", "ERROR")
        return False

# =======================================
# STARTUP
# =======================================
def startup():
    send("\n".join([
        "Alpha Auto Agent v5.0 LIVE!",
        "",
        "NEW FEATURES:",
        "- XAUUSD Real Candles (Twelve Data)",
        "- BTCUSDT Real Candles (Binance)",
        "- TP1/TP2/TP3 Hit Alerts",
        "- SL Hit Alert",
        "- Morning View 9:00 AM IST",
        "- Evening View 6:00 PM IST",
        "- MTF Trend Daily+4H+1H",
        "- News Filter",
        "",
        "Scan: Every 5 min",
        "Min Score: 70%",
        "",
        "@Alphagoldsigna",
    ]))

# =======================================
# MAIN LOOP
# =======================================
def main():
    global scan_count, sig_count
    log("=" * 40)
    log("ALPHA AUTO AGENT v5.0 STARTING")
    log("=" * 40)
    startup()

    while True:
        scan_count += 1
        log(f"=== SCAN #{scan_count} ===")

        # Check morning/evening view
        check_and_send_market_view()

        # Check TP/SL hits for active trades
        check_tp_sl_hits()

        # Signal scan
        sess = get_session()
        if not sess["good"]:
            log(f"Session: {sess['name']} - Waiting...")
            time.sleep(SCAN_INTERVAL_MIN * 60)
            continue

        for asset_key in ASSETS:
            try:
                data = analyze(asset_key)
                if not data:
                    log(f"{asset_key} - No setup")
                    continue

                log(f"{asset_key} | {data['trend']} | "
                    f"MTF:{data['mtf_trend']} | "
                    f"Score:{data['score']}% | "
                    f"Price:{data['entry']}")

                if data["score"] >= MIN_SCORE:
                    now = time.time()
                    if now - last_signal[asset_key] > COOLDOWN_HOURS * 3600:
                        if send(build_msg(data)):
                            last_signal[asset_key] = now
                            sig_count += 1
                            # Track trade for TP/SL alerts
                            trade_id = f"{asset_key}_{int(now)}"
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
                            }
                            log(f"Signal #{sig_count} sent + tracking started!", "SUCCESS")
                    else:
                        rem = int((COOLDOWN_HOURS*3600-(now-last_signal[asset_key]))/60)
                        log(f"{asset_key} cooldown: {rem}min left")
                else:
                    failed = [c["label"] for c in data["checks"] if not c["pass"]]
                    log(f"{asset_key} score {data['score']}% | "
                        f"Failed: {', '.join(failed[:3])}")

                time.sleep(3)

            except Exception as e:
                log(f"{asset_key} error: {e}", "ERROR")
                continue

        log(f"=== Scan #{scan_count} done | Signals:{sig_count} ===")
        time.sleep(SCAN_INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
