import os
import time
import datetime as dt
import xml.etree.ElementTree as ET
from io import BytesIO

import requests
from PIL import Image

# ---------- 设置 ----------
START = dt.date(2026, 1, 1)
END = dt.date(2026, 6, 1)           # 包含这一天

LAYER = "MODIS_Terra_Ice_Surface_Temp_Day"
OUT_DIR = "Ice Surface Temperature (Day)"

# 区域：
#   "global"    全球（和 Worldview 默认视图一样，冰面温度只出现在极地，其余透明）
#   "arctic"    北极（极射赤面投影，冰面更清楚）
#   "antarctic" 南极
REGION = "global"

ADD_BASEMAP = False                 # True：叠加 BlueMarble 底图和海岸线；False：不要底图，只有冰面温度层
BLACK_BACKGROUND = True             # True：没有数据的地方是黑色（和 Worldview 一样）；False：保存为透明背景
WIDTH, HEIGHT = 2000, 1000          # 全球 2:1；极地区域会自动改为正方形
FORMAT = "image/png"
# --------------------------

REGIONS = {
    "global": {
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
        "crs": "EPSG:4326",
        "bbox": "-90,-180,90,180",            # WMS 1.3.0 + EPSG:4326：纬度在前
        "size": (WIDTH, HEIGHT),
    },
    "arctic": {
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg3413/best/wms.cgi",
        "crs": "EPSG:3413",
        "bbox": "-4194304,-4194304,4194304,4194304",
        "size": (HEIGHT, HEIGHT),
    },
    "antarctic": {
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg3031/best/wms.cgi",
        "crs": "EPSG:3031",
        "bbox": "-4194304,-4194304,4194304,4194304",
        "size": (HEIGHT, HEIGHT),
    },
}
cfg = REGIONS[REGION]
os.makedirs(OUT_DIR, exist_ok=True)


def available_dates():
    """从 GetCapabilities 读取该图层有数据的日期；读不到就返回 None（不过滤）。"""
    try:
        r = requests.get(cfg["url"], params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"}, timeout=90)
        root = ET.fromstring(r.content)
    except Exception as e:
        print("读取图层日期失败，将尝试下载所有日期：", e)
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
            print(f"图层数据范围：{min(days)} 到 {max(days)}（共 {len(days)} 天）")
            return days
    print(f"在 {REGION} 区域没有找到图层 {LAYER}，请换一个区域再试。")
    raise SystemExit(1)


def fetch(layers, day, retries=3):
    params = {
        "version": "1.3.0", "service": "WMS", "request": "GetMap",
        "layers": layers, "styles": "", "format": FORMAT,
        "transparent": "TRUE", "crs": cfg["crs"], "bbox": cfg["bbox"],
        "width": cfg["size"][0], "height": cfg["size"][1],
        "time": day.isoformat(),
    }
    for attempt in range(retries):
        try:
            r = requests.get(cfg["url"], params=params, timeout=90)
            if r.ok and "image" in r.headers.get("Content-Type", ""):
                return r.content
            print(f"  {day}: 服务器返回非图片 -> {r.text[:150]!r}")
            return None
        except requests.RequestException as e:
            print(f"  {day}: 第 {attempt + 1} 次失败 ({e})")
            time.sleep(2)
    return None


days_ok = available_dates()
layers = f"BlueMarble_NextGeneration,{LAYER},Coastlines_15m" if ADD_BASEMAP else LAYER
if ADD_BASEMAP and REGION != "global":
    layers = f"BlueMarble_NextGeneration,{LAYER}"      # 极地区域的底图和海岸线图层名未验证，先不用

saved, skipped, failed = 0, [], []
day = START
while day <= END:
    path = os.path.join(OUT_DIR, f"{LAYER}_{day}.png")
    if os.path.exists(path):
        day += dt.timedelta(days=1)
        continue
    if days_ok is not None and day not in days_ok:
        skipped.append(day)
        day += dt.timedelta(days=1)
        continue

    print(f"下载 {day} ...")
    data = fetch(layers, day)
    if data is None:
        failed.append(day)
    else:
        img = Image.open(BytesIO(data)).convert("RGBA")
        if BLACK_BACKGROUND and not ADD_BASEMAP:
            bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
            img = Image.alpha_composite(bg, img).convert("RGB")
        img.save(path)
        saved += 1
    day += dt.timedelta(days=1)

print(f"\n完成：新下载 {saved} 张，保存在文件夹「{OUT_DIR}」")
if skipped:
    print(f"该图层没有数据而跳过的日期（{len(skipped)} 天）：{skipped[0]} ... {skipped[-1]}")
if failed:
    print(f"下载失败的日期（{len(failed)} 天）：{[str(d) for d in failed]}")
print(f"文件夹里现有图片：{len([f for f in os.listdir(OUT_DIR) if f.endswith('.png')])} 张")