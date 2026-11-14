import os
import glob
import wave
import datetime as dt

import numpy as np
from PIL import Image

# ---------- 设置 ----------
FOLDER = "Ice Surface Temperature (Day)"
OUT = "ice_temperature_music.wav"
SR = 44100
BPM_MIN, BPM_MAX = 66, 132      # 变化最慢 / 最快时的速度
SMOOTH = 5                      # 温度平滑天数（奇数）
T_MIN, T_MAX = 223.2, 313.2     # 色条范围（K）
# --------------------------

MAJOR = [0, 2, 4, 5, 7, 9, 11]   # C 大调：明亮（整体在变暖）
MINOR = [0, 2, 3, 5, 7, 8, 10]   # C 小调：阴沉（整体在变冷）

# 色条（和动画里的近似色一致），用来把像素颜色反推成温度
STOPS = np.array([
    [0x8a, 0x1c, 0xff], [0x1a, 0x1a, 0xff], [0x2e, 0xc8, 0xff], [0x66, 0xe6, 0x4d],
    [0xff, 0xff, 0x33], [0xff, 0x9a, 0x1a], [0xe6, 0x33, 0x1a],
], dtype=np.float32)
POS = np.linspace(0, 1, len(STOPS))
LUT = np.stack([np.interp(np.linspace(0, 1, 256), POS, STOPS[:, c]) for c in range(3)], axis=1)
rng = np.random.default_rng(0)


def half_stats(arr):
    pix = arr.reshape(-1, 3).astype(np.float32)
    valid = pix.max(axis=1) > 12                 # 纯黑 = 没有数据
    if valid.sum() < 50:
        return np.nan
    v = pix[valid]
    if len(v) > 4000:
        v = v[rng.choice(len(v), 4000, replace=False)]
    d = ((v[:, None, :] - LUT[None, :, :]) ** 2).sum(axis=-1)
    frac = d.argmin(axis=1) / 255.0
    return T_MIN + frac.mean() * (T_MAX - T_MIN)


files = sorted(glob.glob(os.path.join(FOLDER, "*.png")))
if len(files) < 10:
    raise SystemExit(f"文件夹「{FOLDER}」里图片太少，请先运行 download_ice.py")

dates, north, south = [], [], []
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    dates.append(dt.date.fromisoformat(stem[-10:]))
    img = Image.open(f).convert("RGB")
    h = max(2, int(img.height * 400 / img.width))
    arr = np.asarray(img.resize((400, h), Image.BILINEAR))
    mid = arr.shape[0] // 2
    north.append(half_stats(arr[:mid]))      # 北半球（图的上半）
    south.append(half_stats(arr[mid:]))      # 南半球（图的下半）
print(f"分析 {len(dates)} 天：{dates[0]} 到 {dates[-1]}")


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


n = len(dates)
tn = smooth(fill(north), SMOOTH)
ts = smooth(fill(south), SMOOTH)
nn, ns = norm(tn), norm(ts)
sn = np.gradient(tn) / p95(np.gradient(tn))      # 每日变化率（已归一化）
ss = np.gradient(ts) / p95(np.gradient(ts))
net = smooth((sn + ss) / 2, 15)

# 大调 / 小调：整体在变暖 -> 大调，整体在变冷 -> 小调
is_major = net >= 0

# 速度：变化越剧烈越快
rate = smooth((np.abs(sn) + np.abs(ss)) / 2, 5)
r = np.clip(rate / (np.percentile(rate, 90) + 1e-9), 0, 1)
bpm = smooth(BPM_MIN + r * (BPM_MAX - BPM_MIN), 5)
beat = 60.0 / bpm
onset = np.concatenate([[0], np.cumsum(beat)[:-1]])
total = onset[-1] + beat[-1]

# 力度：变暖时渐强（crescendo），变冷时渐弱（decrescendo）
vol = np.zeros(n)
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


def midi_to_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def degree_to_midi(base, deg, scale):
    return base + 12 * (deg // 7) + scale[deg % 7]


# 旋律 = 北半球温度（越暖音越高）；低音 = 南半球温度；和弦垫底 = 每周的温度水平
prev_idx = None
for i in range(n):
    scale = MAJOR if is_major[i] else MINOR
    harm = 2 + int(nn[i] * 6)                     # 越暖音色越亮
    idx = int(round(nn[i] * 14))                  # 两个八度（C4 起）
    st = onset[i]
    if prev_idx is not None and r[i] > 0.65 and idx != prev_idx:
        mid = (prev_idx + idx) // 2               # 变化剧烈：加一个经过音，变成快速音阶
        add(tone(midi_to_hz(degree_to_midi(60, mid, scale)), beat[i] * 0.45, harm, 0.01, 0.2, 3.0),
            st, vol[i] * 0.55, 0.38)
        add(tone(midi_to_hz(degree_to_midi(60, idx, scale)), beat[i] * 0.5, harm, 0.01, 0.3, 3.0),
            st + beat[i] * 0.5, vol[i] * 0.6, 0.38)
    else:
        add(tone(midi_to_hz(degree_to_midi(60, idx, scale)), beat[i] * 0.95, harm, 0.015, 0.35, 2.5),
            st, vol[i] * 0.6, 0.38)
    prev_idx = idx

    if i % 2 == 0:
        bidx = int(round(ns[i] * 7))
        bdur = beat[i] + (beat[i + 1] if i + 1 < n else beat[i])
        add(tone(midi_to_hz(degree_to_midi(36, bidx, scale)), bdur * 0.95, 3, 0.03, 0.5, 1.2),
            st, vol[i] * 0.55, 0.62)

    if i % 7 == 0:
        q = float(nn[i:i + 7].mean())
        root = [0, 5, 3, 4][min(3, int(q * 4))]   # 温度低 -> 主和弦，越暖和声越"走远"
        end = onset[i + 7] if i + 7 < n else total
        for k in (0, 2, 4):
            add(tone(midi_to_hz(degree_to_midi(48, root + k, scale)), end - st, 3, 0.5, 1.0, 0.3),
                st, vol[i] * 0.22, 0.5)

# 简单混响
for delay, gain in [(0.113, 0.32), (0.171, 0.24), (0.229, 0.18)]:
    d = int(delay * SR)
    for ch in (L, R):
        ch[d:] += gain * ch[:-d].copy()

peak = max(np.abs(L).max(), np.abs(R).max()) * 1.05
stereo = np.stack([L, R], axis=1) / peak
with wave.open(OUT, "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes((stereo * 32767).astype("<i2").tobytes())

print(f"\n已生成 {OUT}，时长约 {total:.0f} 秒")
print(f"速度：{bpm.min():.0f} 到 {bpm.max():.0f} BPM")
print(f"大调占 {is_major.mean() * 100:.0f}%，小调占 {100 - is_major.mean() * 100:.0f}%")
print(f"北半球平均温度（色条近似）：{tn.min():.1f} K 到 {tn.max():.1f} K")
print(f"南半球平均温度（色条近似）：{ts.min():.1f} K 到 {ts.max():.1f} K")
