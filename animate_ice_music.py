import os
import sys
import glob
import wave
import time
import itertools
import subprocess
import platform
import datetime as dt

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from PIL import Image

try:
    import sounddevice as sd
except Exception:
    sd = None

# ---------- 设置 ----------
FOLDER = "Ice Surface Temperature (Day)"
SCALE = 0.5            # 图片缩小比例，0.5 = 宽高各缩一半
FILL_DAYS = 2          # 用前后几天补卫星空隙；0 = 不补
SMOOTH = 5             # 温度平滑天数（奇数）
BPM_MIN, BPM_MAX = 66, 132
T_MIN, T_MAX = 223.2, 313.2
SR = 44100
SAVE_WAV = True        # 同时保存 ice_temperature_music.wav
AUDIO_OFFSET = 0.0     # 声音比画面慢就调大（秒），声音比画面快就调成负数
AUDIO_BACKEND = "system"   # "system" = 用系统自带播放器（Mac: afplay，Windows: winsound），最稳；"sounddevice" = 用 sounddevice
EXPORT_MP4 = False     # True：不弹窗，直接导出带声音的 MP4（需要 ffmpeg）
EXPORT_FPS = 25
OUT_MP4 = "ice_surface_temperature_music.mp4"
# --------------------------

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
rng = np.random.default_rng(0)

# ---------- 色条与颜色→temperature ----------
STOPS_HEX = ["#8a1cff", "#1a1aff", "#2ec8ff", "#66e64d", "#ffff33", "#ff9a1a", "#e6331a"]
cmap = LinearSegmentedColormap.from_list("ist", STOPS_HEX)
STOPS = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in STOPS_HEX], dtype=np.float32)
POS = np.linspace(0, 1, len(STOPS))
LUT = np.stack([np.interp(np.linspace(0, 1, 256), POS, STOPS[:, c]) for c in range(3)], axis=1)


def half_stats(arr):
    pix = arr.reshape(-1, 3).astype(np.float32)
    valid = pix.max(axis=1) > 12                  
    if valid.sum() < 50:
        return np.nan
    v = pix[valid]
    if len(v) > 4000:
        v = v[rng.choice(len(v), 4000, replace=False)]
    d = ((v[:, None, :] - LUT[None, :, :]) ** 2).sum(axis=-1)
    return T_MIN + (d.argmin(axis=1) / 255.0).mean() * (T_MAX - T_MIN)


# ---------- 读取图片 ----------
files = sorted(glob.glob(os.path.join(FOLDER, "*.png")))
if len(files) < 10:
    raise SystemExit(f"文件夹「{FOLDER}」里图片太少，请先运行 download_ice.py")

dates, raw = [], []
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    dates.append(dt.date.fromisoformat(stem[-10:]))
    img = Image.open(f).convert("RGB")
    if SCALE != 1:
        img = img.resize((int(img.width * SCALE), int(img.height * SCALE)), Image.BILINEAR)
    raw.append(np.asarray(img))
n = len(dates)
print(f"读取 {n} 张：{dates[0]} 到 {dates[-1]}")

north = [half_stats(a[: a.shape[0] // 2]) for a in raw]     # 北半球 = 图的上半
south = [half_stats(a[a.shape[0] // 2:]) for a in raw]      # 南半球 = 图的下半

# ---------- 补空隙（画面用） ----------
if FILL_DAYS > 0:
    frames = []
    for i, d in enumerate(dates):
        idx = [j for j, dj in enumerate(dates) if abs((dj - d).days) <= FILL_DAYS]
        stack = np.stack([raw[j] for j in idx]).astype(np.float32)
        valid = (stack.max(axis=-1) > 12)[..., None]
        cnt = valid.sum(axis=0)
        frames.append(((stack * valid).sum(axis=0) / np.maximum(cnt, 1)).astype(np.uint8))
else:
    frames = raw
raw = None


# ---------- 作曲 ----------
def fill(x):
    x = np.array(x, dtype=float)
    bad = np.isnan(x)
    if bad.all():
        raise SystemExit("图片里没有找到可用的温度数据（可能下载时叠加了底图）")
    if bad.any():
        x[bad] = np.interp(np.where(bad)[0], np.where(~bad)[0], x[~bad])
    return x


def smooth(x, k):
    p = k // 2
    return np.convolve(np.pad(x, (p, p), mode="edge"), np.ones(k) / k, mode="valid")


def norm(x):
    return (x - x.min()) / (x.max() - x.min() + 1e-9)


def p95(x):
    return np.percentile(np.abs(x), 95) + 1e-9


tn = smooth(fill(north), SMOOTH)
ts = smooth(fill(south), SMOOTH)
nn, ns = norm(tn), norm(ts)
sn = np.gradient(tn) / p95(np.gradient(tn))
ss = np.gradient(ts) / p95(np.gradient(ts))
net = smooth((sn + ss) / 2, 15)
is_major = net >= 0                                   # 变暖 -> 大调；变冷 -> 小调

rate = smooth((np.abs(sn) + np.abs(ss)) / 2, 5)
r = np.clip(rate / (np.percentile(rate, 90) + 1e-9), 0, 1)
bpm = smooth(BPM_MIN + r * (BPM_MAX - BPM_MIN), 5)    # 变化越剧烈越快
beat = 60.0 / bpm
onset = np.concatenate([[0], np.cumsum(beat)[:-1]])   # 每一天对应的音符开始时间
total = float(onset[-1] + beat[-1])

vol = np.zeros(n)                                     # 变暖渐强，变冷渐弱
v = 0.45
for i in range(n):
    v = float(np.clip(v + 0.035 * np.clip(net[i], -1.5, 1.5), 0.2, 1.0))
    vol[i] = v

L = np.zeros(int((total + 4) * SR))
R = np.zeros_like(L)


def tone(freq, dur, harmonics, attack, release, decay):
    t = np.arange(int(SR * (dur + release))) / SR
    w = np.zeros_like(t)
    amp = 0.0
    for h in range(1, harmonics + 1):
        a = 1.0 / h ** 1.3
        w += a * np.sin(2 * np.pi * freq * h * t)
        amp += a
    w /= amp
    env = np.minimum(t / attack, 1.0) * (0.55 + 0.45 * np.exp(-decay * t))
    gate = np.where(t < dur, 1.0, np.clip(1 - (t - dur) / release, 0, 1))
    return w * env * gate


def add(w, start, volume, pan):
    s = int(start * SR)
    e = min(s + len(w), len(L))
    w = w[: e - s] * volume
    L[s:e] += w * np.cos(pan * np.pi / 2)
    R[s:e] += w * np.sin(pan * np.pi / 2)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def deg(base, d, scale):
    return base + 12 * (d // 7) + scale[d % 7]


prev_idx = None
for i in range(n):
    scale = MAJOR if is_major[i] else MINOR
    harm = 2 + int(nn[i] * 6)
    idx = int(round(nn[i] * 14))
    st = onset[i]
    if prev_idx is not None and r[i] > 0.65 and idx != prev_idx:
        mid = (prev_idx + idx) // 2
        add(tone(hz(deg(60, mid, scale)), beat[i] * 0.45, harm, 0.01, 0.2, 3.0), st, vol[i] * 0.55, 0.38)
        add(tone(hz(deg(60, idx, scale)), beat[i] * 0.5, harm, 0.01, 0.3, 3.0), st + beat[i] * 0.5, vol[i] * 0.6, 0.38)
    else:
        add(tone(hz(deg(60, idx, scale)), beat[i] * 0.95, harm, 0.015, 0.35, 2.5), st, vol[i] * 0.6, 0.38)
    prev_idx = idx

    if i % 2 == 0:
        bidx = int(round(ns[i] * 7))
        bdur = beat[i] + (beat[i + 1] if i + 1 < n else beat[i])
        add(tone(hz(deg(36, bidx, scale)), bdur * 0.95, 3, 0.03, 0.5, 1.2), st, vol[i] * 0.55, 0.62)

    if i % 7 == 0:
        q = float(nn[i:i + 7].mean())
        root = [0, 5, 3, 4][min(3, int(q * 4))]
        end = onset[i + 7] if i + 7 < n else total
        for k in (0, 2, 4):
            add(tone(hz(deg(48, root + k, scale)), end - st, 3, 0.5, 1.0, 0.3), st, vol[i] * 0.22, 0.5)

for delay, gain in [(0.113, 0.32), (0.171, 0.24), (0.229, 0.18)]:
    d = int(delay * SR)
    for ch in (L, R):
        ch[d:] += gain * ch[:-d].copy()

peak = max(np.abs(L).max(), np.abs(R).max()) * 1.05
stereo = (np.stack([L, R], axis=1) / peak).astype(np.float32)
L = R = None

WAV = "ice_temperature_music.wav"
if SAVE_WAV or EXPORT_MP4:
    with wave.open(WAV, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((stereo * 32767).astype("<i2").tobytes())
print(f"音乐时长约 {total:.0f} 秒，速度 {bpm.min():.0f}–{bpm.max():.0f} BPM，大调占 {is_major.mean() * 100:.0f}%")

# ---------- 画面 ----------
fig, ax = plt.subplots(figsize=(11, 7), facecolor="black")
fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.2)
ax.axis("off")
im = ax.imshow(frames[0])
title = ax.set_title(dates[0].isoformat(), fontsize=16, color="white")
info = fig.text(0.5, 0.165, "", ha="center", color="white", fontsize=12)

cax = fig.add_axes([0.25, 0.1, 0.5, 0.03])
cbar = fig.colorbar(ScalarMappable(norm=Normalize(T_MIN, T_MAX), cmap=cmap), cax=cax, orientation="horizontal")
ticks = [T_MIN, T_MIN + 30, T_MIN + 60, T_MAX]
cbar.set_ticks(ticks)
cbar.set_ticklabels([f"{t:.1f} K\n({t - 273.15:.0f} °C)" for t in ticks])
cbar.ax.tick_params(colors="white", labelsize=9)
cbar.outline.set_edgecolor("white")
fig.text(0.5, 0.03, "MODIS Terra Ice Surface Temperature (Day)", ha="center", color="gray", fontsize=10)


def dynamic_mark(x):
    for limit, name in [(0.3, "pp"), (0.45, "p"), (0.6, "mp"), (0.75, "mf"), (0.9, "f")]:
        if x < limit:
            return name
    return "ff"


def draw(t):
    """t = 音乐播放到第几秒；画面和音符同步：每个音符开始时，画面正好是那一天"""
    t = max(0.0, min(t, total - 1e-6))
    i = int(np.clip(np.searchsorted(onset, t, side="right") - 1, 0, n - 1))
    if i >= n - 1:
        img, f, j = frames[-1], 0.0, n - 1
    else:
        f = float(np.clip((t - onset[i]) / beat[i], 0, 1))
        j = i + 1
        img = (frames[i].astype(np.float32) * (1 - f) + frames[j].astype(np.float32) * f).astype(np.uint8)
    im.set_data(img)
    title.set_text(dates[i if f < 0.5 else j].isoformat())
    trend = "crescendo ▲" if net[i] > 0.05 else ("decrescendo ▼" if net[i] < -0.05 else "steady")
    info.set_text(f"{'C major' if is_major[i] else 'C minor'}   ·   {bpm[i]:.0f} BPM   ·   {dynamic_mark(vol[i])}   ·   {trend}")


# ---------- 导出带声音的 MP4 ----------
if EXPORT_MP4:
    nframes = int(total * EXPORT_FPS) + 1
    ea = FuncAnimation(fig, lambda k: draw(k / EXPORT_FPS), frames=nframes, interval=1000 / EXPORT_FPS, blit=False)
    silent = "_silent.mp4"
    ea.save(silent, writer="ffmpeg", fps=EXPORT_FPS, dpi=120)
    subprocess.run(["ffmpeg", "-y", "-i", silent, "-i", WAV, "-c:v", "copy", "-c:a", "aac", "-shortest", OUT_MP4], check=True)
    os.remove(silent)
    print(f"已导出 {OUT_MP4}")
    sys.exit(0)

# ---------- 现场播放：声音和画面同步 ----------
SYSTEM = platform.system()
if AUDIO_BACKEND == "sounddevice" and sd is not None:
    backend = "sounddevice"
elif SYSTEM in ("Darwin", "Windows", "Linux"):
    backend = "system"
elif sd is not None:
    backend = "sounddevice"
else:
    backend = None
print(f"声音播放方式：{backend}")
if backend is None:
    print("找不到可用的声音播放方式，将只播放画面。可以试试：python -m pip install sounddevice")

PLAY_WAV = "_play.wav"
proc = {"p": None}


def write_pcm(path, arr):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((arr * 32767).astype("<i2").tobytes())


def stop_audio():
    if backend == "sounddevice":
        sd.stop()
    elif backend == "system":
        if SYSTEM == "Windows":
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        elif proc["p"] is not None:
            proc["p"].kill()
            proc["p"] = None


def start_audio(offset):
    if backend is None:
        return
    stop_audio()
    seg = stereo[int(max(offset, 0) * SR):]
    if backend == "sounddevice":
        sd.play(seg, SR)
        return
    write_pcm(PLAY_WAV, seg)
    if SYSTEM == "Darwin":
        proc["p"] = subprocess.Popen(["afplay", PLAY_WAV])
    elif SYSTEM == "Windows":
        import winsound
        winsound.PlaySound(os.path.abspath(PLAY_WAV), winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        proc["p"] = subprocess.Popen(["aplay", "-q", PLAY_WAV])


st = {"started": False, "paused": False, "t0": 0.0, "t_pause": 0.0}


def update(_):
    now = time.perf_counter()
    if not st["started"]:
        start_audio(0)
        st["t0"] = time.perf_counter()
        st["started"] = True
        now = st["t0"]
    t = st["t_pause"] if st["paused"] else now - st["t0"]
    if t > total + 1.5:                                  # 播完自动重新开始
        start_audio(0)
        st["t0"] = time.perf_counter()
        t = 0.0
    draw(t - AUDIO_OFFSET)
    return (im,)


def on_click(event):
    now = time.perf_counter()
    if st["paused"]:
        st["t0"] = now - st["t_pause"]
        start_audio(st["t_pause"])
    else:
        st["t_pause"] = now - st["t0"]
        stop_audio()
    st["paused"] = not st["paused"]


fig.canvas.mpl_connect("button_press_event", on_click)
fig.canvas.mpl_connect("close_event", lambda e: stop_audio())

anim = FuncAnimation(fig, update, frames=itertools.count(), interval=30, blit=False, cache_frame_data=False)
print("点击画面可暂停 / 继续（声音会一起暂停）")
plt.show()