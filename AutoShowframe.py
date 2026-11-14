import os
import glob
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from PIL import Image

FRAME_MS = 150   # 每帧停留毫秒数，越小越快

files = sorted(glob.glob(os.path.join("frames", "*.png")))
dates = [os.path.splitext(os.path.basename(f))[0] for f in files]

# 跳过没有数据的日期 2026-01-20 ~ 2026-01-27
missing = {f"2026-01-{d}" for d in range(20, 28)}
pairs = [(f, d) for f, d in zip(files, dates) if d not in missing]
files = [p[0] for p in pairs]
dates = [p[1] for p in pairs]
images = [Image.open(f) for f in files]
n = len(images)

fig, ax = plt.subplots(figsize=(11, 6))
ax.axis("off")
im = ax.imshow(images[0])
title = ax.set_title(dates[0], fontsize=16)
plt.tight_layout()


def update(i):
    im.set_data(images[i])
    title.set_text(f"{dates[i]}   ({i + 1}/{n})")
    return im, title


anim = FuncAnimation(fig, update, frames=n, interval=FRAME_MS, repeat=True)

# 点击画面：暂停 / 继续
paused = {"on": False}
def on_click(event):
    if paused["on"]:
        anim.resume()
    else:
        anim.pause()
    paused["on"] = not paused["on"]

fig.canvas.mpl_connect("button_press_event", on_click)

plt.show()