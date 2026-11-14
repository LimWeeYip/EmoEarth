import os
import time
import datetime as dt
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont


START = dt.date(2026, 1, 1)
END = dt.date(2026, 5, 1)
MISSING = (dt.date(2026, 1, 20), dt.date(2026, 1, 27))   # 该图层无数据的日期

DATA_LAYER = "AIRS_L3_Surface_Air_Temperature_Daily_Day"
BASE_LAYER = "BlueMarble_NextGeneration"
REF_LAYER = "Reference_Features"

K = 3                    # 前后各取几天来补空隙；还有空隙就加大
WIDTH, HEIGHT = 1000, 500
# --------------------------

WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
RAW_DIR, OUT_DIR = "frames_data", "frames_filled"
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

try:
    FONT = ImageFont.load_default(size=26)
except TypeError:
    FONT = ImageFont.load_default()


def get_layer(layer, day, path):
    """下载单个图层（带透明通道）。day 为 None 时不传 time。"""
    if os.path.exists(path):
        return Image.open(path).convert("RGBA")
    params = {
        "version": "1.3.0", "service": "WMS", "request": "GetMap",
        "layers": layer, "styles": "", "format": "image/png",
        "transparent": "TRUE", "crs": "EPSG:4326",
        "bbox": "-90,-180,90,180", "width": WIDTH, "height": HEIGHT,
    }
    if day:
        params["time"] = day.isoformat()
    for attempt in range(3):
        try:
            r = requests.get(WMS_URL, params=params, timeout=60)
            if r.ok and "image" in r.headers.get("Content-Type", ""):
                img = Image.open(BytesIO(r.content)).convert("RGBA")
                img.save(path)
                return img
            print(f"  {layer} {day}: {r.text[:120]!r}")
            return None
        except requests.RequestException as e:
            print(f"  第 {attempt + 1} 次失败: {e}")
            time.sleep(2)
    return None


# 1) 底图和边界线只下载一次
base = get_layer(BASE_LAYER, None, os.path.join(RAW_DIR, "base.png"))
ref = get_layer(REF_LAYER, None, os.path.join(RAW_DIR, "ref.png"))

# 2) 逐天下载"只有温度层"的透明图
dates, arrays = [], []
day = START
while day <= END:
    if not (MISSING[0] <= day <= MISSING[1]):
        print(f"下载 {day} ...")
        img = get_layer(DATA_LAYER, day, os.path.join(RAW_DIR, f"{day}.png"))
        if img is not None:
            dates.append(day)
            arrays.append(np.asarray(img))
    day += dt.timedelta(days=1)

# 3) 用前后 K 天补空隙，再叠回底图
for i, d in enumerate(dates):
    idx = [j for j, dj in enumerate(dates) if abs((dj - d).days) <= K]
    stack = np.stack([arrays[j] for j in idx]).astype(np.float32)   # m,H,W,4
    valid = (stack[..., 3] > 0)[..., None]                          # 有数据的像素
    cnt = valid.sum(axis=0)                                         # H,W,1
    rgb = (stack[..., :3] * valid).sum(axis=0) / np.maximum(cnt, 1)
    alpha = (cnt[..., 0] > 0) * 255
    filled = Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")

    frame = Image.alpha_composite(base, filled)
    frame = Image.alpha_composite(frame, ref).convert("RGB")

    draw = ImageDraw.Draw(frame)
    draw.rectangle([10, 10, 150, 45], fill=(0, 0, 0))
    draw.text((18, 12), d.isoformat(), fill="white", font=FONT)
    frame.save(os.path.join(OUT_DIR, f"{d}.png"))
    print(f"已处理 {d}")

print(f"完成：{len(dates)} 帧保存在 {OUT_DIR}/")