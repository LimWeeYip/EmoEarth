import os
import glob
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from PIL import Image

# ---------- 设置 ----------
STEPS = 4         # 每两天之间插入的过渡帧数，越大越平滑（也越慢）
FRAME_MS = 40      # 每帧毫秒数，40ms ≈ 25 帧/秒
# --------------------------

#files = sorted(glob.glob(os.path.join("frames", "*.png")))
files = sorted(glob.glob(os.path.join("frames_filled", "*.png")))
dates = [os.path.splitext(os.path.basename(f))[0] for f in files]

# 去掉没有数据的日期 2026-01-20 ~ 2026-01-27
missing = {f"2026-01-{d}" for d in range(20, 28)}
pairs = [(f, d) for f, d in zip(files, dates) if d not in missing]
dates = [p[1] for p in pairs]
images = [np.asarray(Image.open(p[0]).convert("RGB"), dtype=np.float32) for p in pairs]
n = len(images)

total = (n - 1) * STEPS + 1   # 总帧数


def frame_at(k):
    """第 k 帧 = 相邻两天按比例混合"""
    i, step = divmod(k, STEPS)
    if i >= n - 1:
        return images[-1], dates[-1]
    t = step / STEPS
    blended = images[i] * (1 - t) + images[i + 1] * t
    label = dates[i] if t < 0.5 else dates[i + 1]
    return blended.astype(np.uint8), label


fig, ax = plt.subplots(figsize=(11, 6))
ax.axis("off")
first, label0 = frame_at(0)
im = ax.imshow(first)
title = ax.set_title(label0, fontsize=16)
plt.tight_layout()


def update(k):
    img, label = frame_at(k)
    im.set_data(img)
    title.set_text(label)
    return im, title


anim = FuncAnimation(fig, update, frames=total, interval=FRAME_MS,
                     repeat=True, blit=False)

# 点击画面暂停 / 继续
state = {"paused": False}
def on_click(event):
    anim.resume() if state["paused"] else anim.pause()
    state["paused"] = not state["paused"]
fig.canvas.mpl_connect("button_press_event", on_click)

# 想导出文件就取消下面一行的注释（需要先 brew install ffmpeg）
# anim.save("temperature_smooth.mp4", writer="ffmpeg", fps=25, dpi=120)

plt.show()