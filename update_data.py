"""Check NASA GIBS for new days, download them, and rebuild only what changed.

  python update_data.py              check once
  python update_data.py --every 6    keep checking every 6 hours (leave the terminal open)
  python update_data.py --force      rebuild frames/music even if nothing new arrived

app.py can also run this in the background:  python app.py --auto-update 6
"""
import os
import sys
import time
import filecmp
import threading
import datetime as dt
import xml.etree.ElementTree as ET
from io import BytesIO

import requests
from PIL import Image

import build_assets

# ---------- settings ----------
START = dt.date(2026, 1, 1)         # first day of the timeline
END = None                          # None = up to the newest day GIBS has. Or e.g. dt.date(2026, 6, 1) to stop there
LAYER = "MODIS_Terra_Ice_Surface_Temp_Day"
WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
WIDTH, HEIGHT = 2000, 1000
REFRESH_DAYS = 4                    # re-download the newest days every time: near-real-time data can be replaced later
POLITE_DELAY = 0.4                  # seconds between requests, to be kind to NASA's servers
# ------------------------------

LOG_PATH = os.path.join(build_assets.BASE_DIR, "update_log.txt")
STATE = {"updating": False, "message": "", "last_check": None}
_lock = threading.Lock()


def log(msg):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}"
    try:
        import applog                                # also into the app log (logs/emoearth.log)
        applog.log.info("Data update: %s", msg)
    except Exception:
        print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def available_dates():
    """Dates GIBS has for the layer (from GetCapabilities), or None if it could not be read."""
    try:
        r = requests.get(WMS_URL, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"}, timeout=120)
        root = ET.fromstring(r.content)
    except Exception as e:
        log(f"Could not read GIBS capabilities: {e}")
        return None
    ns = "{http://www.opengis.net/wms}"
    for layer in root.iter(ns + "Layer"):
        name = layer.find(ns + "Name")
        if name is not None and name.text == LAYER:
            dim = layer.find(ns + "Dimension")
            if dim is None or not dim.text:
                return None
            days = set()
            for seg in dim.text.split(","):
                parts = seg.strip().split("/")
                if len(parts) == 3:
                    a = dt.date.fromisoformat(parts[0][:10])
                    b = dt.date.fromisoformat(parts[1][:10])
                    d = a
                    while d <= b:
                        days.add(d)
                        d += dt.timedelta(days=1)
                elif len(parts) == 1 and parts[0]:
                    days.add(dt.date.fromisoformat(parts[0][:10]))
            return days
    log(f"Layer {LAYER} not found in GIBS capabilities.")
    return None


def fetch_day(day, retries=3):
    """Returns an RGB image on black, the string 'empty' if GIBS has no pixels for that day yet, or None on failure."""
    params = {
        "version": "1.3.0", "service": "WMS", "request": "GetMap",
        "layers": LAYER, "styles": "", "format": "image/png", "transparent": "TRUE",
        "crs": "EPSG:4326", "bbox": "-90,-180,90,180", "width": WIDTH, "height": HEIGHT,
        "time": day.isoformat(),
    }
    for attempt in range(retries):
        try:
            r = requests.get(WMS_URL, params=params, timeout=90)
            if r.ok and "image" in r.headers.get("Content-Type", ""):
                img = Image.open(BytesIO(r.content)).convert("RGBA")
                if img.getchannel("A").getextrema()[1] == 0:
                    return "empty"
                bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
                return Image.alpha_composite(bg, img).convert("RGB")
            return None
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    return None


def run_update(force_build=False):
    """Download new (and the newest few) days, then rebuild what changed. Returns a summary dict, or None if
    another update is already running."""
    if not _lock.acquire(blocking=False):
        return None
    try:
        STATE.update(updating=True, message="Checking GIBS for new data ...")
        days_ok = available_dates()
        if not days_ok:
            STATE["message"] = "Could not reach GIBS. Will try again later."
            return {"error": STATE["message"]}

        os.makedirs(build_assets.FOLDER, exist_ok=True)
        latest = max(days_ok)
        end = min(latest, END) if END else latest
        targets = sorted(d for d in days_ok if START <= d <= end)
        refresh_from = end - dt.timedelta(days=REFRESH_DAYS)

        added = changed = empty = failed = 0
        for k, d in enumerate(targets):
            path = os.path.join(build_assets.FOLDER, f"{LAYER}_{d}.png")
            exists = os.path.exists(path)
            if exists and d < refresh_from:
                continue
            STATE["message"] = f"Downloading {d} ..."
            img = fetch_day(d)
            time.sleep(POLITE_DELAY)
            if img is None:
                failed += 1
                continue
            if isinstance(img, str):
                empty += 1
                continue
            tmp = path + ".new"
            img.save(tmp, format="PNG")
            if exists and filecmp.cmp(path, tmp, shallow=False):
                os.remove(tmp)                        # identical to what we already have: keep the old file
            else:
                os.replace(tmp, path)
                if exists:
                    changed += 1
                else:
                    added += 1

        tl_ok = False
        try:
            import json
            with open(build_assets.TL_PATH) as f:
                tl_ok = "frames" in json.load(f)
        except Exception:
            tl_ok = False

        if added or changed or force_build or not tl_ok:
            STATE["message"] = "Rebuilding frames and music ..."
            build_assets.build()
            note = "Rebuilt"
        else:
            note = "No new data"
        msg = f"{note}. Latest day: {end}. New: {added}, refreshed: {changed}, not ready: {empty}, failed: {failed}."
        STATE["message"] = msg
        log(msg)
        return {"added": added, "changed": changed, "empty": empty, "failed": failed, "latest": str(end)}
    except Exception as e:
        STATE["message"] = f"Update failed: {e}"
        log(STATE["message"])
        return {"error": str(e)}
    finally:
        STATE["updating"] = False
        STATE["last_check"] = dt.datetime.now().isoformat(timespec="seconds")
        _lock.release()


def run_update_async():
    """Start an update in the background. False if one is already running."""
    if _lock.locked():
        return False
    threading.Thread(target=run_update, daemon=True).start()
    return True


def loop(hours):
    while True:
        run_update()
        time.sleep(max(0.1, hours) * 3600)


if __name__ == "__main__":
    if "--every" in sys.argv:
        loop(float(sys.argv[sys.argv.index("--every") + 1]))
    else:
        run_update(force_build="--force" in sys.argv)
