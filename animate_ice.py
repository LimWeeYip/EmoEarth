import os
import glob
import datetime as dt

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from PIL import Image

# ---------- 设置 ----------
FOLDER = "Ice Surface Temperature (Day)"
SCALE = 0.5          # 缩小图片以节省内存：0.5 = 宽高各缩一半；1 = 原尺寸
FILL_DAYS = 2        # 用前后几天补卫星空隙（黑色部分）；0 = 不补
STEPS = 6            # 相邻两天之间的过渡帧数；1 = 不做过渡
FRAME_MS = 40        # 每帧毫秒数（40 ≈ 25 帧/秒）
SAVE_AS = None       # None = 只播放；"gif" 或 "mp4" = 同时导出文件（mp4 需要 ffmpeg）
# --------------------------

files = sorted(glob.glob(os.path.join(FOLDER, "*.png")))
if not files:
    raise SystemExit(f"在文件夹「{FOLDER}」里没有找到 PNG 图片，请先运行 download_ice.py")

dates, raw = [], []
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    dates.append(dt.date.fromisoformat(stem[-10:]))
    img = Image.open(f).convert("RGB")
    if SCALE != 1:
        img = img.resize((int(img.width * SCALE), int(img.height * SCALE)), Image.BILINEAR)
    raw.append(np.asarray(img))
print(f"读取 {len(raw)} 张：{dates[0]} 到 {dates[-1]}")

# 补空隙：纯黑像素视为"没有数据"，用前后 FILL_DAYS 天有数据的像素取平均
if FILL_DAYS > 0:
    frames = []
    for i, d in enumerate(dates):
        idx = [j for j, dj in enumerate(dates) if abs((dj - d).days) <= FILL_DAYS]
        stack = np.stack([raw[j] for j in idx]).astype(np.float32)
        valid = (stack.max(axis=-1) > 12)[..., None]
        cnt = valid.sum(axis=0)
        mean = (stack * valid).sum(axis=0) / np.maximum(cnt, 1)
        frames.append(mean.astype(np.uint8))
else:
    frames = raw
raw = None

n = len(frames)
total = (n - 1) * STEPS + 1


def frame_at(k):
    i, s = divmod(k, STEPS)
    if i >= n - 1:
        return frames[-1], dates[-1]
    t = s / STEPS
    mix = frames[i].astype(np.float32) * (1 - t) + frames[i + 1].astype(np.float32) * t
    return mix.astype(np.uint8), (dates[i] if t < 0.5 else dates[i + 1])


fig, ax = plt.subplots(figsize=(11, 7), facecolor="black")
fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.2)
ax.axis("off")
img0, d0 = frame_at(0)
im = ax.imshow(img0)
title = ax.set_title(d0.isoformat(), fontsize=16, color="white")

# 温度色条（颜色是照 Worldview 图例的近似色，范围 223.2 K 到 313.2 K）
T_MIN, T_MAX = 223.2, 313.2
cmap = LinearSegmentedColormap.from_list("ist", [
    "#8a1cff", "#1a1aff", "#2ec8ff", "#66e64d", "#ffff33", "#ff9a1a", "#e6331a",
])
cax = fig.add_axes([0.25, 0.1, 0.5, 0.03])
cbar = fig.colorbar(ScalarMappable(norm=Normalize(T_MIN, T_MAX), cmap=cmap),
                    cax=cax, orientation="horizontal")
ticks = [T_MIN, T_MIN + 30, T_MIN + 60, T_MAX]
cbar.set_ticks(ticks)
cbar.set_ticklabels([f"{t:.1f} K\n({t - 273.15:.0f} °C)" for t in ticks])
cbar.ax.tick_params(colors="white", labelsize=9)
cbar.outline.set_edgecolor("white")
fig.text(0.5, 0.03, "MODIS Terra Ice Surface Temperature (Day)", ha="center", color="gray", fontsize=10)


def update(k):
    img, d = frame_at(k)
    im.set_data(img)
    title.set_text(d.isoformat())
    return im, title


anim = FuncAnimation(fig, update, frames=total, interval=FRAME_MS, repeat=True)

state = {"paused": False}


def on_click(event):
    anim.resume() if state["paused"] else anim.pause()
    state["paused"] = not state["paused"]


fig.canvas.mpl_connect("button_press_event", on_click)

if SAVE_AS == "gif":
    anim.save("ice_surface_temperature.gif", writer="pillow", fps=int(1000 / FRAME_MS))
    print("已保存 ice_surface_temperature.gif")
elif SAVE_AS == "mp4":
    anim.save("ice_surface_temperature.mp4", writer="ffmpeg", fps=int(1000 / FRAME_MS), dpi=120)
    print("已保存 ice_surface_temperature.mp4")

print("点击画面可暂停 / 继续")
plt.show()