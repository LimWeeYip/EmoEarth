"""Build the "Carbon dioxide (DYAMOND)" layer (NASA SVS 5436, GEOS model, 15 Jan to 3 Mar 2020, every 6 hours).

    python download_co2.py     # once: fetch the frames from NASA
    python build_co2.py        # globe frames, the CO2 orchestra and its timeline

Output (the page's layer menu picks it up automatically):
  static/data/co2/frames/YYYY-MM-DDTHH.webp  NASA's picture (land, ice, ocean and CO2 plumes), opaque
  static/data/co2/music.mp3 (+ .wav)         an orchestra composed from the CO2 plumes
  static/data/co2/timeline.json              same format as the other layers, plus times and plume ppm
  static/data/co2/calibration.json           frozen pitch/tempo ranges for this layer

What is measured: NASA's colour bar runs from 380 to 460 ppm, but below about 425 ppm it is see-through,
so only the high-CO2 plumes (tan, orange, red) are visible. For each frame and hemisphere this script
measures how much of the map the plumes cover (%) and, from their colour, roughly how high they reach
(ppm, 425 to 460). These are estimates from the picture's colours, good for trends only.
"""
import os
import sys
import glob
import json
import time
import datetime as dt

import numpy as np
from PIL import Image

import build_assets as ba
import orchestra

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE_DIR, "Carbon Dioxide (DYAMOND)")
OUT = os.path.join(BASE_DIR, "static", "data", "co2")
FRAMES = os.path.join(OUT, "frames")
TL_PATH = os.path.join(OUT, "timeline.json")
STATS_PATH = os.path.join(OUT, "stats_cache.json")
MAIN_TL = os.path.join(BASE_DIR, "static", "data", "timeline.json")

FRAME_WIDTH = 2048
FRAME_QUALITY = 80
SMOOTH = 5                     # smoothing in frames (6 hours each)
PPM_LO, PPM_HI = 425.0, 460.0  # the visible (opaque) part of NASA's colour bar

# The CO2 orchestra: the ice layer's instruments, a little slower and darker. A rise in CO2 sounds minor
# (and louder), a fall sounds major.
CO2_STYLE = "orchestra"
CO2_BPM = (52, 92)                  # beats (= 6-hour steps) per minute; the ice layer uses 66-132
CO2_AROUSAL = 1.0
CO2_RISING_IS_MAJOR = False

# NASA's colour bar (dyamondCbar_6-27-2024a.png), opaque part, 425 -> 460 ppm
CBAR = np.array([
    [218, 193, 135], [214, 182, 115], [233, 175, 74], [234, 131, 49], [230, 117, 42], [225, 108, 39],
    [224, 100, 36], [225, 93, 34], [226, 85, 31], [227, 76, 28], [228, 66, 24], [229, 53, 19], [230, 34, 12],
    [230, 11, 4]], dtype=np.float32)
CB_N = CBAR / CBAR.max(axis=1, keepdims=True)
CB_T = np.linspace(0.0, 1.0, len(CBAR))
rng = np.random.default_rng(0)


def plume_mask(a):
    """Pixels coloured by a CO2 plume (tan to red). Deserts, snow, land and ocean are left out."""
    a = a.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    return (r - b > 70) & (r > 120) & ((mx - mn) > 0.4 * mx) & (r >= g)


def half_stats(a):
    """(cover %, plume ppm, 7 colour shares) for one hemisphere."""
    m = plume_mask(a)
    cover = float(m.mean() * 100)
    v = a[m].astype(np.float32)
    if len(v) < 30:
        return cover, float("nan"), [float("nan")] * 7
    if len(v) > 5000:
        v = v[rng.choice(len(v), 5000, replace=False)]
    v = v / v.max(axis=1, keepdims=True)
    pos = CB_T[((v[:, None, :] - CB_N[None, :, :]) ** 2).sum(axis=-1).argmin(axis=1)]
    shares = np.bincount(np.clip(np.round(pos * 6).astype(int), 0, 6), minlength=7) / len(pos)
    return cover, float(PPM_LO + pos.mean() * (PPM_HI - PPM_LO)), [round(float(x), 4) for x in shares]


def build(full=False, recalibrate=False):
    files = sorted(glob.glob(os.path.join(SRC, "co2_*.jpg")))
    if len(files) < 10:
        raise RuntimeError(f"Not enough frames in '{SRC}'. Run: python download_co2.py")
    os.makedirs(FRAMES, exist_ok=True)
    keys = [os.path.basename(f)[4:17] for f in files]              # YYYY-MM-DDTHH
    n = len(files)
    print(f"CO2 layer: {n} frames, {keys[0]} to {keys[-1]}")
    try:
        with open(STATS_PATH) as fh:
            cache = json.load(fh)
    except Exception:
        cache = {}
    made = 0
    for i, f in enumerate(files):
        out = os.path.join(FRAMES, keys[i] + ".webp")
        c = cache.get(keys[i])
        fresh = os.path.exists(out) and os.path.getmtime(f) <= os.path.getmtime(out)
        if not full and c and fresh and abs(c["mtime"] - os.path.getmtime(f)) < 1e-3:
            continue
        img = Image.open(f).convert("RGB")
        if img.width != FRAME_WIDTH:
            img = img.resize((FRAME_WIDTH, FRAME_WIDTH // 2), Image.BILINEAR)
        a = np.asarray(img)
        if full or not fresh:
            img.save(out + ".tmp", format="WEBP", quality=FRAME_QUALITY, method=4)
            os.replace(out + ".tmp", out)
            made += 1
        mid = a.shape[0] // 2
        cn, pn, bn = half_stats(a[:mid])
        cs, ps, bs = half_stats(a[mid:])
        both = half_stats(a)[2]
        cache[keys[i]] = {"mtime": os.path.getmtime(f), "cn": cn, "cs": cs, "pn": pn, "ps": ps, "b": both}
        if (i + 1) % 25 == 0 or i == n - 1:
            print(f"  {i + 1}/{n} frames read, {made} written")
    with open(STATS_PATH, "w") as fh:
        json.dump(cache, fh)
    for old in glob.glob(os.path.join(FRAMES, "*.webp")):
        if os.path.basename(old)[:-5] not in keys:
            os.remove(old)

    st = [cache[k] for k in keys]
    m = compose([s["cn"] for s in st], [s["cs"] for s in st], [s["b"] for s in st], recalibrate)
    write_outputs(keys, st, m)
    print(f"Done. {n} frames, {made} written. CO2 music is {m['total']:.0f} s, "
          f"{m['bpm'].min():.0f}-{m['bpm'].max():.0f} BPM, {m['major'].mean() * 100:.0f}% major, "
          f"{int(m['change'].sum())} key changes.")


def compose(cover_n, cover_s, bands, recalibrate=False):
    """The shared composer: northern plume cover drives the melody, southern the bass, colours the sections."""
    ba.CAL_PATH = os.path.join(OUT, "calibration.json")
    ba.OUT_DIR = OUT
    ba.SMOOTH = SMOOTH
    print("Composing the CO2 orchestra ...")
    return ba.compose_music(cover_n, cover_s, bands, recalibrate=recalibrate, bpm_range=CO2_BPM,
                            arousal_scale=CO2_AROUSAL, style=CO2_STYLE, rising_is_major=CO2_RISING_IS_MAJOR)


def write_outputs(keys, st, m):
    ba.write_wav(os.path.join(OUT, "music.wav"), m["stereo"])
    has_mp3 = ba.write_mp3(os.path.join(OUT, "music.mp3"), m["stereo"])
    try:
        with open(MAIN_TL) as fh:
            main = json.load(fh)
    except Exception:
        main = {}
    ppm = lambda k: [None if not np.isfinite(s[k]) else round(float(s[k]), 1) for s in st]
    tl = {
        "layer": "co2",
        "title": "Global carbon dioxide (DYAMOND)",
        "source": "NASA/GSFC Scientific Visualization Studio 5436, GEOS model (DYAMOND)",
        "fixed": True,
        "style": CO2_STYLE,
        "n": len(keys),
        "dates": [k[:10] for k in keys],
        "times": [k[11:13] + ":00 UTC" for k in keys],
        "frames": keys,
        "frame_ext": "webp",
        "frame_ver": [int(os.path.getmtime(os.path.join(FRAMES, k + ".webp"))) for k in keys],
        "music": "music.mp3" if has_mp3 else "music.wav",
        "onset": [round(float(x), 4) for x in m["onset"]],
        "beat": [round(float(x), 4) for x in m["beat"]],
        "bpm": [round(float(x), 1) for x in m["bpm"]],
        "major": [bool(x) for x in m["major"]],
        "vol": [round(float(x), 3) for x in m["vol"]],
        "net": [round(float(x), 3) for x in m["net"]],
        "tn": [round(float(x), 3) for x in m["tn"]],          # plume cover, % of the northern half (smoothed)
        "ts": [round(float(x), 3) for x in m["ts"]],          # plume cover, % of the southern half (smoothed)
        "pn": ppm("pn"), "ps": ppm("ps"),                     # roughly how high the plumes reach, ppm
        "unit": "% plume cover",
        "instruments": orchestra.INSTRUMENTS,
        "inst": [[round(float(x), 2) for x in row] for row in m["level"]],
        "emotion": m["emotion"],
        "key_change": [bool(x) for x in m["change"]],
        "total": round(m["total"], 3),
        "has_base": bool(main.get("has_base")),
        "has_borders": bool(main.get("has_borders")),
        "has_coast": bool(main.get("has_coast")),
        "t_min": 380, "t_max": 460,
        "version": int(time.time()),
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "first_date": keys[0][:10],
        "latest_date": keys[-1][:10],
    }
    with open(TL_PATH + ".tmp", "w") as fh:
        json.dump(tl, fh)
    os.replace(TL_PATH + ".tmp", TL_PATH)


if __name__ == "__main__":
    try:
        build(full="--full" in sys.argv, recalibrate="--recalibrate" in sys.argv)
    except RuntimeError as e:
        raise SystemExit(str(e))
