"""Download NASA SVS animation 3912 "Global Sea Surface Currents and Temperature" (ECCO2 model) once.

    python download_ocean.py            # about 1 frame per simulated day (345 frames, ~1 GB download)
    python download_ocean.py --step 2   # every 2nd day (fewer frames, faster)

The set is fixed (model run 2007-03-25 to 2008-03-03), so this only needs to run once; frames already
downloaded are skipped. Frames come from the folder WITHOUT the colour bar (orig), so nothing is painted
on the globe; the colour bar is shown in the page's legend instead. Saved as
"Ocean Currents (ECCO2)/ecco2_YYYY-MM-DD.jpg". Then run: python build_ocean.py

Source: NASA/Goddard Space Flight Center Scientific Visualization Studio, https://svs.gsfc.nasa.gov/3912
(model data: ECCO2, MIT/JPL; scientists Hong Zhang and Dimitris Menemenlis).
"""
import os
import re
import sys
import time
import datetime as dt
from io import BytesIO

import requests
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(BASE_DIR, "Ocean Currents (ECCO2)")
LIST_URL = "https://svs.gsfc.nasa.gov/vis/a000000/a003900/a003912/frames/2048x1024_1x1_30p/orig/"
START = dt.date(2007, 3, 25)                 # first and last simulated day (SVS page 3912)
END = dt.date(2008, 3, 3)
JPEG_QUALITY = 92                            # stored sources; build_ocean.py makes the globe frames from them
POLITE_DELAY = 0.3                           # seconds between downloads, to be kind to NASA's servers


def frame_list(session):
    html = session.get(LIST_URL, timeout=60).text
    names = sorted(set(re.findall(r'flat_global_ecco2_2028x1024\.(\d+)\.tif', html)), key=int)
    if len(names) < 100:
        raise SystemExit("Could not read the NASA frame list. Check your internet connection or the page " + LIST_URL)
    return [int(n) for n in names]


def main():
    step = int(sys.argv[sys.argv.index("--step") + 1]) if "--step" in sys.argv else 1
    os.makedirs(FOLDER, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "EmoEarth/1.0 (education project)"
    nums = frame_list(s)
    days = (END - START).days
    print(f"NASA has {len(nums)} frames ({nums[0]} to {nums[-1]}) for {days + 1} days; taking 1 per {step} day(s).")
    todo = []
    for d in range(0, days + 1, step):
        date = START + dt.timedelta(days=d)
        num = nums[round(d * (len(nums) - 1) / days)]          # frames are evenly spaced in time
        out = os.path.join(FOLDER, f"ecco2_{date.isoformat()}.jpg")
        if not os.path.exists(out):
            todo.append((date, num, out))
    print(f"{len(todo)} to download, {(days // step + 1) - len(todo)} already here.")
    for k, (date, num, out) in enumerate(todo, 1):
        url = f"{LIST_URL}flat_global_ecco2_2028x1024.{num}.tif"
        for attempt in range(4):
            try:
                r = s.get(url, timeout=120)
                r.raise_for_status()
                img = Image.open(BytesIO(r.content)).convert("RGB")
                img.save(out + ".tmp", format="JPEG", quality=JPEG_QUALITY)
                os.replace(out + ".tmp", out)
                break
            except Exception as e:
                if attempt == 3:
                    print(f"  {date}: failed ({e}); run the script again later to retry.")
                else:
                    time.sleep(3 * (attempt + 1))
        if k % 10 == 0 or k == len(todo):
            print(f"  {k}/{len(todo)}  ({date})")
        time.sleep(POLITE_DELAY)
    print("Done. Next: python build_ocean.py")


if __name__ == "__main__":
    main()
