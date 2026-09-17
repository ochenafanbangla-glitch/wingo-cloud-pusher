#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   AI MASTER PRO — Termux Scraper (Mobile Part)          ║
║   কাজ: ফেচ করো → Render-এ পুশ করো → শেষ               ║
║   কোনো ক্যালকুলেশন নেই, শুধু ডেটা ট্রান্সপোর্ট       ║
╚══════════════════════════════════════════════════════════╝

দরকারি লাইব্রেরি ইনস্টল (Termux-এ একবার):
    pip install requests

চালানো:
    python termux_scraper.py
"""

import requests
import time
import logging
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════
#  CONFIG — এই দুটো লাইন শুধু পরিবর্তন করতে হবে
# ═══════════════════════════════════════════════════════════════

RENDER_URL   = "https://ai-master-pro.onrender.com/receive_data"
PUSH_SECRET  = "bdg_termux_2026_secret"   # Render-এর সাথে SAME রাখতে হবে

# ═══════════════════════════════════════════════════════════════
#  GAME API (পরিবর্তন দরকার নেই)
# ═══════════════════════════════════════════════════════════════

GAME_API_URL = (
    "https://draw.ar-lottery01.com/WinGo/WinGo_30S/"
    "GetHistoryIssuePage.json?typeId=30&pageSize=10&pageNo=1&language=0"
)

POLL_INTERVAL = 5       # ৩০s গেম → ৫s poll → max ৫s দেরি (ছিল ২৮s!)
FETCH_TIMEOUT = 8       # গেম সার্ভার timeout
PUSH_TIMEOUT  = 6       # Render push timeout
MAX_RETRIES   = 2       # ২ retry — fast response দরকার, বেশি wait না

# ═══════════════════════════════════════════════════════════════
#  HEADERS — Lead Architect-এর আসল মোবাইল ডিভাইস
# ═══════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
    "Referer":         "https://draw.ar-lottery01.com/",
    "Origin":          "https://draw.ar-lottery01.com",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

# ═══════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("termux")


# ═══════════════════════════════════════════════════════════════
#  FETCH — গেম সার্ভার থেকে raw JSON নিয়ে আসো
# ═══════════════════════════════════════════════════════════════

def fetch_game_data() -> dict | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                GAME_API_URL,
                headers=HEADERS,
                timeout=FETCH_TIMEOUT,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                log.error(f"❌ Fetch HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")
        except requests.exceptions.Timeout:
            log.warning(f"⏳ Fetch timeout (attempt {attempt}/{MAX_RETRIES})")
        except requests.exceptions.ConnectionError as e:
            log.warning(f"🔌 Connection error: {e} (attempt {attempt}/{MAX_RETRIES})")
        except Exception as e:
            log.error(f"💥 Fetch unexpected error: {e}")
            break

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)   # 2s → 4s backoff

    return None


# ═══════════════════════════════════════════════════════════════
#  PUSH — Render সার্ভারে POST করো
# ═══════════════════════════════════════════════════════════════

def push_to_render(raw_data: dict) -> bool:
    payload = {
        "secret":    PUSH_SECRET,
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "raw":       raw_data,
    }
    try:
        resp = requests.post(
            RENDER_URL,
            json=payload,
            timeout=PUSH_TIMEOUT,
        )
        if resp.status_code == 200:
            result = resp.json()
            period  = result.get("period", "?")
            number  = result.get("number", "?")
            status  = result.get("status", "ok")
            log.info(f"✅ Pushed → Period: ...{str(period)[-6:]} | N={number} | {status}")
            return True
        elif resp.status_code == 208:
            log.info("↩️  Duplicate period — Render already has this result")
            return True
        else:
            log.error(f"❌ Push failed: HTTP {resp.status_code} | {resp.text[:120]}")
            return False
    except requests.exceptions.Timeout:
        log.warning("⏳ Push timeout — Render আস্তে উত্তর দিচ্ছে")
        return False
    except Exception as e:
        log.error(f"💥 Push error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════

def extract_latest_period(raw: dict) -> str | None:
    """Raw JSON থেকে সবচেয়ে নতুন period ID বের করো"""
    try:
        items = (
            raw.get('data', {}).get('list')
            or raw.get('data', {}).get('records')
            or raw.get('list')
            or []
        )
        if items:
            return str(items[0].get('issueNumber') or items[0].get('issue') or '')
    except Exception:
        pass
    return None


def main():
    log.info("=" * 55)
    log.info("   AI MASTER PRO — Termux Mobile Scraper")
    log.info(f"   Render URL : {RENDER_URL}")
    log.info(f"   Poll       : every {POLL_INTERVAL}s (fast mode)")
    log.info("=" * 55)

    # ── Render connectivity check (startup) ─────────────────────
    try:
        ping = requests.get(RENDER_URL.replace("/receive_data", "/ping"), timeout=8)
        if ping.status_code == 200:
            log.info(f"🟢 Render server alive: {ping.json().get('status', 'ok')}")
        else:
            log.warning(f"⚠️  Render ping: HTTP {ping.status_code} — তবুও চালু থাকব")
    except Exception as e:
        log.warning(f"⚠️  Render ping failed: {e} — তবুও চালু থাকব")

    last_pushed_period  = None   # শেষ যে period push হয়েছে
    consecutive_failures = 0

    while True:
        tick_start = time.time()

        # ── Fetch ──────────────────────────────────────────────
        raw = fetch_game_data()

        if raw:
            consecutive_failures = 0
            latest_period = extract_latest_period(raw)

            if latest_period and latest_period != last_pushed_period:
                # ✅ নতুন period এসেছে → এখনই push করো
                log.info(f"🆕 New period: ...{latest_period[-6:]} → pushing immediately")
                if push_to_render(raw):
                    last_pushed_period = latest_period
            else:
                # পুরনো period → push দরকার নেই (Render-এও duplicate block আছে)
                log.debug(f"↩️  Same period ...{str(latest_period)[-6:]} — skip push")
        else:
            consecutive_failures += 1
            log.error(f"🚨 Fetch failed | consecutive: {consecutive_failures}")
            if consecutive_failures >= 10:
                log.critical("🛑 ১০ বার পরপর ফেচ ব্যর্থ! নেটওয়ার্ক চেক করুন।")

        # ── Sleep ──────────────────────────────────────────────
        elapsed   = time.time() - tick_start
        sleep_for = max(0.5, POLL_INTERVAL - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("⛔ Termux scraper stopped by user (Ctrl+C)")
