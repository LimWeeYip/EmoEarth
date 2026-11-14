"""Download NASA SVS animation 5436 "DYAMOND Global Carbon Dioxide" (Science On a Sphere version) once.

    python download_co2.py             # 4 frames a day (every 6 hours): about 195 frames, ~4 GB to download
    python download_co2.py --every 12  # every 12 hours instead (about 100 frames)

The set is fixed: NASA GEOS model run, 14 January to 3 March 2020, one frame per hour (1176 frames of
8192 x 4096 pixels, ~20 MB each). Each picked frame is shrunk to 2048 x 1024 and saved as
"Carbon Dioxide (DYAMOND)/co2_YYYY-MM-DDTHH.jpg"; frames already here are skipped, so it can be stopped
and run again. Then run: python build_co2.py

Source: NASA/Goddard Space Flight Center Scientific Visualization Studio, https://svs.gsfc.nasa.gov/5436
(Science On a Sphere version of https://svs.gsfc.nasa.gov/5196).
"""
import os
import re
import sys
import time
import datetime as dt
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

Image.MAX_IMAGE_PIXELS = None                       # NASA's frames are 8192 x 4096
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(BASE_DIR, "Carbon Dioxide (DYAMOND)")
ROOT = "https://svs.gsfc.nasa.gov/vis/a000000/a005400/a005436/"
LIST_URL = ROOT + "frames/8192x4096_2x1_30p/soscomp_1-29-2025a_pngs/"
STAMPS_URL = ROOT + "dyamond_timestamps.txt"        # one date per frame
SIZE = (2048, 1024)
JPEG_QUALITY = 92
WORKERS = 3                                         # parallel downloads (kept small, to be kind to NASA's servers)


def frame_times(session):
    """(frame number, UTC time) for every frame. Frames are hourly; a day with fewer than 24 frames is the
    first day (frames end at 23:00) or the last day (frames start at 00:00)."""
    names = sorted({int(n) for n in re.findall(r"soscomp_1-29-2025a\.(\d+)\.png", session.get(LIST_URL, timeout=60).text)})
    days = [dt.datetime.strptime(x.strip(), "%b %d, %Y") for x in session.get(STAMPS_URL, timeout=60).text.splitlines() if x.strip()]
    if len(names) < 100 or len(days) < len(names):
        raise SystemExit("Could not read NASA's frame list or timestamps. Check the internet connection.")
    count = {}
    for d in days:
        count[d] = count.get(d, 0) + 1
    out, seen = [], {}
    for k, num in enumerate(names):
        d = days[num - 1]
        j = seen.get(d, 0)
        seen[d] = j + 1
        hour = j + (24 - count[d] if d == days[0] else 0)
        out.append((num, d + dt.timedelta(hours=hour)))
    return out


def fetch(session, num, when, path):
    url = f"{LIST_URL}soscomp_1-29-2025a.{num:05d}.png"
    for attempt in range(4):
        try:
            r = session.get(url, timeout=180)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB").resize(SIZE, Image.LANCZOS)
            img.save(path + ".tmp", format="JPEG", quality=JPEG_QUALITY)
            os.replace(path + ".tmp", path)
            return True
        except Exception as e:
            if attempt == 3:
                print(f"  {when:%Y-%m-%d %H:00}: failed ({e}); run the script again later to retry.")
            time.sleep(3 * (attempt + 1))
    return False


def main():
    every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 6
    os.makedirs(FOLDER, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "EmoEarth/1.0 (education project)"
    frames = [(n, t) for n, t in frame_times(s) if t.hour % every == 0]
    todo = [(n, t, os.path.join(FOLDER, f"co2_{t:%Y-%m-%dT%H}.jpg")) for n, t in frames]
    todo = [x for x in todo if not os.path.exists(x[2])]
    print(f"{len(frames)} frames picked (every {every} hours, {frames[0][1]:%Y-%m-%d} to {frames[-1][1]:%Y-%m-%d}); "
          f"{len(todo)} to download.")
    done = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for ok in pool.map(lambda x: fetch(s, *x), todo):
            done += 1
            if done % 10 == 0 or done == len(todo):
                print(f"  {done}/{len(todo)}")
    print("Done. Next: python build_co2.py")


if __name__ == "__main__":
    main()
