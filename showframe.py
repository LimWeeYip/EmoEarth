import os
import glob
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from PIL import Image

files = sorted(glob.glob(os.path.join("frames", "*.png")))
dates = [os.path.splitext(os.path.basename(f))[0] for f in files]
images = [Image.open(f) for f in files]

# 跳过没有数据的日期（可选）
missing = {f"2026-01-{d}" for d in range(20, 28)}
keep = [i for i, d in enumerate(dates) if d not in missing]
files = [files[i] for i in keep]
dates = [dates[i] for i in keep]
images = [images[i] for i in keep]

n = len(images)
state = {"i": 0, "playing": False}

fig, ax = plt.subplots(figsize=(11, 6.5))
plt.subplots_adjust(bottom=0.15)
im = ax.imshow(images[0])
ax.axis("off")
title = ax.set_title(f"{dates[0]}  (1/{n})", fontsize=14)

slider_ax = fig.add_axes([0.15, 0.04, 0.7, 0.03])
slider = Slider(slider_ax, "Frame", 0, n - 1, valinit=0, valstep=1)


def show(i):
    state["i"] = max(0, min(n - 1, int(i)))
    im.set_data(images[state["i"]])
    title.set_text(f"{dates[state['i']]}  ({state['i'] + 1}/{n})")
    fig.canvas.draw_idle()


def on_slider(val):
    show(val)


def on_key(event):
    if event.key == "right":
        slider.set_val(min(n - 1, state["i"] + 1))
    elif event.key == "left":
        slider.set_val(max(0, state["i"] - 1))
    elif event.key == " ":
        state["playing"] = not state["playing"]


def tick():
    if state["playing"]:
        nxt = state["i"] + 1
        slider.set_val(0 if nxt >= n else nxt)


slider.on_changed(on_slider)
fig.canvas.mpl_connect("key_press_event", on_key)

timer = fig.canvas.new_timer(interval=150)
timer.add_callback(tick)
timer.start()

print("操作：← → 逐帧 | 空格 播放/暂停 | 拖动下方滑块跳转")
plt.show()