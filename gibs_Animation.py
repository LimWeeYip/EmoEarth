import os
import time
import datetime as dt
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont

# ---------- 设置 ----------
START = dt.date(2026, 1, 1)
END = dt.date(2026, 5, 1)          # 包含这一天

# 图层：底图 + 温度数据 + 海岸线/国界
BASE_LAYER = "BlueMarble_NextGeneration"
DATA_LAYER = "AIRS_L3_Surface_Air_Temperature_Daily_Day"   # 近地表气温（日平均，白天）
REF_LAYER = "Reference_Features"
LAYERS = [BASE_LAYER, DATA_LAYER, REF_LAYER]

WIDTH, HEIGHT = 1000, 500          # 2:1，对应全球经纬度范围
FRAME_MS = 150                     # 每帧显示毫秒数
OUT_DIR = "frames"
OUT_GIF = "temperature_2026.gif"
# --------------------------

WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
os.makedirs(OUT_DIR, exist_ok=True)

try:
    FONT = ImageFont.load_default(size=26)   # Pillow >= 10.1
except TypeError:
    FONT = ImageFont.load_default()


def fetch_frame(day, retries=3):
    path = os.path.join(OUT_DIR, f"{day}.png")
    if os.path.exists(path):                 # 已下载过就跳过，方便中断后续跑
        return Image.open(path).convert("RGB")

    params = {
        "version": "1.3.0", "service": "WMS", "request": "GetMap",
        "layers": ",".join(LAYERS), "styles": "",
        "format": "image/png", "transparent": "TRUE",
        "crs": "EPSG:4326",
        "bbox": "-90,-180,90,180",           # WMS 1.3.0 + EPSG:4326：纬度在前
        "width": WIDTH, "height": HEIGHT,
        "time": day.isoformat(),
    }
    for attempt in range(retries):
        try:
            r = requests.get(WMS_URL, params=params, timeout=60)
            if r.ok and "image" in r.headers.get("Content-Type", ""):
                img = Image.open(BytesIO(r.content)).convert("RGB")
                img.save(path)
                return img
            print(f"  {day}: 服务器返回非图片 -> {r.text[:150]!r}")
            return None
        except requests.RequestException as e:
            print(f"  {day}: 第 {attempt + 1} 次失败 ({e})")
            time.sleep(2)
    return None


frames = []
day = START
while day <= END:
    print(f"下载 {day} ...")
    img = fetch_frame(day)
    if img is not None:
        draw = ImageDraw.Draw(img)
        label = day.strftime("%Y-%m-%d")
        draw.rectangle([10, 10, 150, 45], fill=(0, 0, 0))
        draw.text((18, 12), label, fill="white", font=FONT)
        frames.append(img)
    day += dt.timedelta(days=1)

if not frames:
    raise SystemExit("没有成功下载任何图像，请检查图层名称和日期。")

frames[0].save(
    OUT_GIF, save_all=True, append_images=frames[1:],
    duration=FRAME_MS, loop=0, optimize=True,
)
print(f"完成：{len(frames)} 帧 -> {OUT_GIF}")