import requests
import time
import datetime

BOT_TOKEN = "8807619711:AAEaL5HI6Bj-sbMSpliF73rxO5eRSG3zugI"
CHAT_ID   = "8867873147"
SCAN_INTERVAL_MINUTES = 15
MIN_SCORE = 70
COOLDOWN_HOURS = 2

ASSETS = {
    "XAUUSD": {"sym": "XAUUSDT", "sl": 6.5,  "vol_min": 2.0},
    "BTCUSD": {"sym": "BTCUSDT", "sl": 175,   "vol_min": 3.0},
}

last_signal = {"XAUUSD": 0, "BTCUSD": 0}

def log(msg):
    t = datetime.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{t}] {msg}")

def get_session():
    h = datetime.datetime.utcnow().hour
    d = datetime.datetime.utcnow().weekday()
    if d >= 5: return {"name": "Weekend", "good": False}
    if 0  <= h < 7:  return {"name": "Asian",   "good": False}
    if 7  <= h < 12: return {"name": "London",  "good": True}
    if 12 <= h < 15: return {"name": "Overlap", "good": True}
    if 15 <= h < 20: return {"name": "NY",      "good": d != 4}
    return {"name": "Closed", "good": False}

def fetch(symbol, interval, limit=50):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10)
        return r.json()
    except:
        return None

def ema(prices, period):
    if len(prices) < period: return None
    k = 2 / (period + 1)
    e = sum(prices[:period]) / period
    for p in prices[period:]:
        e = p * k + e * (1 - k)
    return e

def analyze(asset_key):
    cfg = ASSETS[asset_key]
    c1h = fetch(cfg["sym"], "1h", 50)
    c5m = fetch(cfg["sym"], "5m", 50)
    if not c1h or not c5m: return None

    price = float(c5m[-1][4])
    highs = [float(c[2]) for c in c1h[-20:]]
    lows  = [float(c[3]) for c in c1h[-20:]]
    sh, sl = max(highs), min(lows)
    rng = sh - sl

    trend = "BUY" if float(c1h[-1][4]) > float(c1h[-10][4]) else "SELL"
    fib = (sh - rng*0.382) if trend=="BUY" else (sl + rng*0.382)

    closes = [float(c[4]) for c in c5m]
    e20 = ema(closes, 20) or price

    vols = [float(c[5]) for c in c5m]
    avg_v = sum(vols[-20:-1]) / 19
    vol_r = vols[-1] / avg_v if avg_v > 0 else 0

    last = c5m[-1]
    o,c_,h,l = float(last[1]),float(last[4]),float(last[2]),float(last[3])
    body_pct = (abs(c_-o)/(h-l)*100) if (h-l)>0 else 0

    sess = get_session()
    buf = rng * 0.015
    near = abs(price - fib) <= buf * 4

    recent = c5m[-6:]
    if trend == "BUY":
        sweep = any(float(c[3]) < fib - fib*0.001 for c in recent[:-1]) and float(recent[-1][4]) > fib
    else:
        sweep = any(float(c[2]) > fib + fib*0.001 for c in recent[:-1]) and float(recent[-1][4]) < fib

    prev = float(c5m[-2][4])
    choch = (prev < e20 and c_ > e20) if trend=="BUY" else (prev > e20 and c_ < e20)
    ema_ok = c_ > e20*0.999 if trend=="BUY" else c_ < e20*1.001

    checks = [
        ("Good Session",      sess["good"]),
        ("Near 38.2% Zone",   near),
        ("Liquidity Sweep",   sweep),
        ("CHOCH Confirmed",   choch),
        ("Full Body 60%+",    body_pct >= 60),
        ("Volume Spike",      vol_r >= cfg["vol_min"]),
        ("EMA Aligned",       ema_ok),
    ]
    score = round(sum(1 for _,p in checks if p) / len(checks) * 100)

    e_p = round(price, 2)
    sl_p = round(e_p - cfg["sl"], 2) if trend=="BUY" else round(e_p + cfg["sl"], 2)
    tp1  = round(e_p + cfg["sl"]*3, 2) if trend=="BUY" else round(e_p - cfg["sl"]*3, 2)
    tp2  = round(e_p + cfg["sl"]*4, 2) if trend=="BUY" else round(e_p - cfg["sl"]*4, 2)

    return dict(asset=asset_key, trend=trend, score=score,
                entry=e_p, sl=sl_p, tp1=tp1, tp2=tp2,
                fib=round(fib,2), sh=round(sh,2), sw=round(sl,2),
                e20=round(e20,2), vol=round(vol_r,2),
                body=round(body_pct,1), sess=sess,
                checks=checks, sl_amt=cfg["sl"])

def build_msg(d):
    stars = "⭐⭐⭐" if d["score"]>=85 else "⭐⭐" if d["score"]>=70 else "⭐"
    passed = "\n".join(f"✅ {l}" for l,p in d["checks"] if p)
    sym = "⚡ XAUUSD" if d["asset"]=="XAUUSD" else "₿ BTCUSDT"
    trap = "Seller's Trap" if d["trend"]=="BUY" else "Buyer's Trap"
    if d["trend"] == "BUY":
        logic = f"1H pe sharp bullish move. 38.2% zone {d['fib']} pe {trap} — sellers swept liquidity neeche. Smart money ne sellers trap kiye. 5M pe strong bullish candle 20 EMA {d['e20']} ke upar. Volume {d['vol']}x spike = institutional buying confirm."
    else:
        logic = f"1H pe sharp bearish move. 38.2% zone {d['fib']} pe {trap} — buyers swept liquidity upar. Smart money ne buyers trap kiye. 5M pe strong bearish candle 20 EMA {d['e20']} ke neeche. Volume {d['vol']}x spike = institutional selling confirm."

    return f"""⚡ {sym} {d['trend']} SIGNAL ⚡
━━━━━━━━━━━━━━━━━━
📍 Entry   : {d['entry']}
🛑 SL      : {d['sl']} (${d['sl_amt']})
🎯 TP1     : {d['tp1']} (1:3) → 50% close
🎯 TP2     : {d['tp2']} (1:4) → Trail 50%
━━━━━━━━━━━━━━━━━━
📊 Trend   : {'📈 Bullish' if d['trend']=='BUY' else '📉 Bearish'} (1H)
🪤 Setup   : {trap} @ 38.2% Zone
📐 Fib     : {d['fib']}
💹 Volume  : {d['vol']}x avg
🕯️ Body   : {d['body']}%
⏰ Session : {d['sess']['name']}
━━━━━━━━━━━━━━━━━━
📋 LOGIC:
{logic}
━━━━━━━━━━━━━━━━━━
✅ CONDITIONS:
{passed}
━━━━━━━━━━━━━━━━━━
💪 Score: {d['score']}% {stars}
⚠️ Max SL: ${d['sl_amt']}
📢 @Alphagoldsigna"""

def send(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10)
        return r.json().get("ok", False)
    except:
        return False

def main():
    log("ALPHA AUTO AGENT STARTED!")
    send("🚀 Alpha Auto Agent ON!\nXAUUSD + BTCUSDT scanning har 15 min\n📢 @Alphagoldsigna")
    scan = 0
    while True:
        scan += 1
        log(f"━━ SCAN #{scan} ━━")
        for key in ASSETS:
            try:
                d = analyze(key)
                if not d:
                    log(f"{key} — data fetch failed")
                    continue
                log(f"{key} → {d['trend']} | Score:{d['score']}% | Price:{d['entry']} | {d['sess']['name']}")
                if d["score"] >= MIN_SCORE:
                    now = time.time()
                    if now - last_signal[key] > COOLDOWN_HOURS * 3600:
                        if send(build_msg(d)):
                            last_signal[key] = now
                            log(f"✅ {key} signal sent!")
                    else:
                        log(f"{key} cooldown active")
                else:
                    log(f"{key} score low — no signal")
                time.sleep(3)
            except Exception as e:
                log(f"{key} error: {e}")
        log(f"Next scan {SCAN_INTERVAL_MINUTES} min mein...")
        time.sleep(SCAN_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
