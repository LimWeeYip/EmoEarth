"""Build the "Ocean currents & sea surface temperature" layer (NASA SVS 3912, ECCO2 model, 2007-03-25 to 2008-03-03).

    python download_ocean.py     # once: fetch the frames from NASA
    python build_ocean.py        # make the globe frames, the ocean orchestra and its timeline

Output (the page's layer menu picks it up automatically):
  static/data/ocean/frames/YYYY-MM-DD.webp   currents coloured by temperature; land and empty sea are transparent
  static/data/ocean/music.mp3 (+ .wav)       a separate orchestra composed from the sea temperatures
  static/data/ocean/timeline.json            same format as the ice layer's timeline.json
  static/data/ocean/calibration.json         frozen pitch/tempo ranges for this layer
Temperatures are estimated from the colours with NASA's colour bar (0 to 32 degrees C) and stored in kelvin,
like the ice layer, so the page shows both the same way.
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
SRC = os.path.join(BASE_DIR, "Ocean Currents (ECCO2)")
OUT = os.path.join(BASE_DIR, "static", "data", "ocean")
FRAMES = os.path.join(OUT, "frames")
TL_PATH = os.path.join(OUT, "timeline.json")
STATS_PATH = os.path.join(OUT, "stats_cache.json")       # per-day temperatures, so re-composing the music is quick
MAIN_TL = os.path.join(BASE_DIR, "static", "data", "timeline.json")

FRAME_WIDTH = 1600           # same as the ice layer; 2048 (NASA full width) is sharper but about 2.5x bigger
FRAME_QUALITY = 82
SMOOTH = 5
T_MIN, T_MAX = 273.15, 305.15        # 0 and 32 degrees C, the ends of NASA's colour bar
# The ocean's own orchestra: its own instruments, soft and slow (orchestra.py style "ocean").
# "gentle" = the ice layer's instruments played softly; --lively = the ice layer's music style exactly.
OCEAN_STYLE = "ocean"
OCEAN_BPM = (46, 72)                 # beats (= model days) per minute; the ice layer uses 66-132
OCEAN_AROUSAL = 0.45                 # < 1 keeps the moods calm: mostly Serene, Joyful and Melancholy

# NASA's colour bar (sst_ecco2_cbar.png), sampled left to right: 0 to 32 degrees C
CBAR = np.array([
    [52, 95, 248], [51, 102, 243], [51, 109, 238], [51, 117, 233], [50, 125, 227], [50, 132, 222], [50, 139, 217],
    [50, 146, 211], [50, 153, 206], [50, 159, 200], [50, 166, 195], [50, 172, 189], [51, 179, 184], [51, 184, 178],
    [51, 191, 173], [52, 197, 167], [52, 203, 162], [53, 209, 158], [54, 214, 152], [54, 221, 147], [55, 226, 141],
    [56, 231, 136], [56, 236, 131], [57, 241, 126], [58, 246, 120], [58, 250, 116], [59, 254, 111], [60, 255, 106],
    [60, 255, 101], [61, 255, 96], [62, 255, 91], [64, 255, 86], [68, 255, 81], [72, 255, 76], [79, 255, 71],
    [87, 255, 66], [96, 255, 62], [107, 255, 57], [118, 255, 53], [131, 255, 49], [143, 255, 46], [156, 255, 42],
    [169, 255, 40], [182, 255, 38], [194, 255, 36], [207, 255, 35], [219, 255, 34], [229, 255, 34], [238, 255, 34],
    [246, 255, 33], [251, 255, 33], [251, 250, 33], [251, 242, 32], [250, 231, 32], [250, 220, 31], [250, 209, 30],
    [249, 196, 30], [249, 182, 29], [249, 168, 28], [248, 153, 27], [248, 138, 27], [248, 122, 26], [247, 106, 26],
    [247, 88, 25], [247, 70, 25], [247, 50, 25], [247, 26, 25], [247, 0, 24], [247, 0, 24]], dtype=np.float32)
CB_N = CBAR / CBAR.max(axis=1, keepdims=True)          # colour without brightness (fading trails keep their hue)
CB_T = np.linspace(0.0, 1.0, len(CBAR))                 # position on the bar, 0 = 0 C, 1 = 32 C
rng = np.random.default_rng(0)


def color_mask(a):
    """Strength of the coloured current lines (0..255): grey land and black empty sea are 0."""
    a = a.astype(np.int16)
    sat = a.max(axis=-1) - a.min(axis=-1)
    return np.clip((sat - 15) * 4, 0, 255).astype(np.uint8)


def positions(a):
    """Colour-bar position (0..1) of a sample of clearly coloured pixels."""
    pix = a.reshape(-1, 3).astype(np.float32)
    mx = pix.max(axis=1)
    keep = (mx - pix.min(axis=1) > 60) & (mx > 90)
    v = pix[keep]
    if len(v) < 50:
        return None
    if len(v) > 5000:
        v = v[rng.choice(len(v), 5000, replace=False)]
    v = v / v.max(axis=1, keepdims=True)
    return CB_T[((v[:, None, :] - CB_N[None, :, :]) ** 2).sum(axis=-1).argmin(axis=1)]


def half_temp(a):
    p = positions(a)
    return float("nan") if p is None else float(T_MIN + p.mean() * (T_MAX - T_MIN))


def bands(a):
    p = positions(a)
    if p is None:
        return [float("nan")] * 7
    b = np.clip(np.round(p * 6).astype(int), 0, 6)
    return [round(float(x), 4) for x in np.bincount(b, minlength=7) / len(b)]


def save_frame(a, path):
    alpha = color_mask(a)
    Image.fromarray(np.dstack([a, alpha]), "RGBA").save(path + ".tmp", format="WEBP", quality=FRAME_QUALITY,
                                                         alpha_quality=70, method=4)
    os.replace(path + ".tmp", path)


def build(full=False, recalibrate=False, lively=False):
    files = sorted(glob.glob(os.path.join(SRC, "ecco2_*.jpg")))
    if len(files) < 10:
        raise RuntimeError(f"Not enough frames in '{SRC}'. Run: python download_ocean.py")
    os.makedirs(FRAMES, exist_ok=True)
    dates = [os.path.basename(f)[6:16] for f in files]
    n = len(files)
    print(f"Ocean layer: {n} days, {dates[0]} to {dates[-1]}")

    try:
        with open(STATS_PATH) as fh:
            cache = json.load(fh)
    except Exception:
        cache = {}
    north, south, bnd, made = [], [], [], 0
    for i, f in enumerate(files):
        out = os.path.join(FRAMES, dates[i] + ".webp")
        c = cache.get(dates[i])
        if (not full and c and abs(c["mtime"] - os.path.getmtime(f)) < 1e-3 and os.path.exists(out)
                and os.path.getmtime(f) <= os.path.getmtime(out)):
            north.append(c["n"]); south.append(c["s"]); bnd.append(c["b"])
            continue                                     # frame and numbers already up to date
        img = Image.open(f).convert("RGB")
        if img.width != FRAME_WIDTH:
            img = img.resize((FRAME_WIDTH, FRAME_WIDTH // 2), Image.BILINEAR)
        a = np.asarray(img)
        if full or not os.path.exists(out) or os.path.getmtime(f) > os.path.getmtime(out):
            save_frame(a, out)
            made += 1
        mid = a.shape[0] // 2
        north.append(half_temp(a[:mid]))
        south.append(half_temp(a[mid:]))
        bnd.append(bands(a))
        cache[dates[i]] = {"mtime": os.path.getmtime(f), "n": north[-1], "s": south[-1], "b": bnd[-1]}
        if (i + 1) % 25 == 0 or i == n - 1:
            print(f"  {i + 1}/{n} days read, {made} frames written")
    with open(STATS_PATH, "w") as fh:
        json.dump(cache, fh)
    keep = {d + ".webp" for d in dates}
    for old in glob.glob(os.path.join(FRAMES, "*.webp")):
        if os.path.basename(old) not in keep:
            os.remove(old)

    m = compose(north, south, bnd, recalibrate, lively)
    write_outputs(dates, m, lively)
    print(f"Done. {n} days, {made} frames written. Ocean music is {m['total']:.0f} s, "
          f"{m['bpm'].min():.0f}-{m['bpm'].max():.0f} BPM, {m['major'].mean() * 100:.0f}% major, "
          f"{int(m['change'].sum())} key changes.")


def compose(north, south, bnd, recalibrate=False, lively=False):
    """The ice layer's composer, pointed at this layer's own calibration, tempo, calmness and instruments."""
    ba.CAL_PATH = os.path.join(OUT, "calibration.json")
    ba.OUT_DIR = OUT
    ba.SMOOTH = SMOOTH
    print("Composing the ocean orchestra ...")
    if lively:
        m = ba.compose_music(north, south, bnd, recalibrate=recalibrate)
    else:
        m = ba.compose_music(north, south, bnd, recalibrate=recalibrate, bpm_range=OCEAN_BPM,
                             arousal_scale=OCEAN_AROUSAL, style=OCEAN_STYLE)
    return m


def write_outputs(dates, m, lively=False):
    """music.wav / music.mp3 and timeline.json for the ocean layer."""
    n = len(dates)
    ba.write_wav(os.path.join(OUT, "music.wav"), m["stereo"])
    has_mp3 = ba.write_mp3(os.path.join(OUT, "music.mp3"), m["stereo"])

    try:
        with open(MAIN_TL) as fh:
            main = json.load(fh)
    except Exception:
        main = {}
    tl = {
        "layer": "ocean",
        "title": "Ocean currents and sea surface temperature",
        "source": "NASA/GSFC Scientific Visualization Studio 3912, ECCO2 model (MIT/JPL)",
        "fixed": True,
        "style": "lively" if lively else OCEAN_STYLE,
        "n": n,
        "dates": dates,
        "frames": dates,
        "frame_ext": "webp",
        "frame_ver": [int(os.path.getmtime(os.path.join(FRAMES, d + ".webp"))) for d in dates],
        "music": "music.mp3" if has_mp3 else "music.wav",
        "onset": [round(float(x), 4) for x in m["onset"]],
        "beat": [round(float(x), 4) for x in m["beat"]],
        "bpm": [round(float(x), 1) for x in m["bpm"]],
        "major": [bool(x) for x in m["major"]],
        "vol": [round(float(x), 3) for x in m["vol"]],
        "net": [round(float(x), 3) for x in m["net"]],
        "tn": [round(float(x), 2) for x in m["tn"]],
        "ts": [round(float(x), 2) for x in m["ts"]],
        "instruments": orchestra.OCEAN_INSTRUMENTS if (OCEAN_STYLE == "ocean" and not lively) else orchestra.INSTRUMENTS,
        "inst": [[round(float(x), 2) for x in row] for row in m["level"]],
        "emotion": m["emotion"],
        "key_change": [bool(x) for x in m["change"]],
        "total": round(m["total"], 3),
        "has_base": bool(main.get("has_base")),
        "has_borders": bool(main.get("has_borders")),
        "has_coast": bool(main.get("has_coast")),
        "t_min": T_MIN, "t_max": T_MAX,
        "version": int(time.time()),
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "first_date": dates[0],
        "latest_date": dates[-1],
    }
    with open(TL_PATH + ".tmp", "w") as fh:
        json.dump(tl, fh)
    os.replace(TL_PATH + ".tmp", TL_PATH)


if __name__ == "__main__":
    try:
        build(full="--full" in sys.argv, recalibrate="--recalibrate" in sys.argv, lively="--lively" in sys.argv)
    except RuntimeError as e:
        raise SystemExit(str(e))
