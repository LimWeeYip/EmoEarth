"""Prepare everything the 3D globe page needs (incremental, so new days are cheap to add):
  static/data/frames/YYYY-MM-DD.webp  gap-filled temperature frames (equirectangular; empty areas are transparent)
  static/data/music.mp3               the same music, compressed (~10x smaller), which the page plays
  static/data/music.wav               orchestral music composed from the map colours and temperature change (orchestra.py)
  static/data/timeline.json           per-day timing, mode, tempo, dynamics, version
  static/data/calibration.json        FIXED pitch/tempo reference ranges (keeps old music stable when data grows)
  static/data/stats_cache.json        cached per-day temperature estimates
  static/data/base.jpg / borders.png / coastlines.png   optional overlays downloaded once from GIBS
Run directly (python build_assets.py [--full] [--recalibrate]) or let app.py / update_data.py call build().
"""
import os
import sys
import glob
import json
import time
import wave
import datetime as dt

import numpy as np
import requests
from PIL import Image

import orchestra

# ---------- settings ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(BASE_DIR, "Ice Surface Temperature (Day)")
OUT_DIR = os.path.join(BASE_DIR, "static", "data")
FRAMES_DIR = os.path.join(OUT_DIR, "frames")
TL_PATH = os.path.join(OUT_DIR, "timeline.json")
CAL_PATH = os.path.join(OUT_DIR, "calibration.json")
STATS_PATH = os.path.join(OUT_DIR, "stats_cache.json")

FRAME_WIDTH = 1600        # texture width in pixels (height = width / 2). Higher = sharper when zoomed
FILL_DAYS = 2             # fill satellite gaps (black) using +/- this many days; 0 = off
FRAME_FORMAT = "webp"     # "webp" (about 3x smaller, empty areas stored exactly as transparency) or "png"
FRAME_QUALITY = 88        # WebP quality for the colours (the empty/no-data mask is always exact)
MP3_KBPS = 192            # bitrate of music.mp3 (the page plays this; music.wav is kept for export_wave.py)
SMOOTH = 5                # temperature smoothing in days (odd number)
BPM_MIN, BPM_MAX = 66, 132
T_MIN, T_MAX = 223.2, 313.2
SR = orchestra.SR
MODE_HYST = 0.05          # trend must pass +/- this before the key switches (stops major/minor flickering)
ROLLING_DAYS = None       # None = growing timeline (everything from the first day). Or e.g. 150 = only the last 150 days
CAL_MARGIN = 0.15         # extra room added around the first-seen temperature range before it is frozen
DOWNLOAD_BASE = True      # download a Blue Marble base map once so the globe looks like Earth
DOWNLOAD_BORDERS = True   # try to download the borders and coastlines layers from GIBS once
# ------------------------------

rng = np.random.default_rng(0)

STOPS_HEX = ["#8a1cff", "#1a1aff", "#2ec8ff", "#66e64d", "#ffff33", "#ff9a1a", "#e6331a"]
STOPS = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in STOPS_HEX], dtype=np.float32)
POS = np.linspace(0, 1, len(STOPS))
LUT = np.stack([np.interp(np.linspace(0, 1, 256), POS, STOPS[:, c]) for c in range(3)], axis=1)


def half_stats(arr):
    pix = arr.reshape(-1, 3).astype(np.float32)
    valid = pix.max(axis=1) > 12                  # pure black = no data
    if valid.sum() < 50:
        return float("nan")
    v = pix[valid]
    if len(v) > 4000:
        v = v[rng.choice(len(v), 4000, replace=False)]
    d = ((v[:, None, :] - LUT[None, :, :]) ** 2).sum(axis=-1)
    return float(T_MIN + (d.argmin(axis=1) / 255.0).mean() * (T_MAX - T_MIN))


def color_bands(arr):
    """Share of the valid pixels that fall in each of the 7 colour bands (purple ... red)."""
    pix = arr.reshape(-1, 3).astype(np.float32)
    v = pix[pix.max(axis=1) > 12]
    if len(v) < 50:
        return [float("nan")] * len(STOPS)
    if len(v) > 6000:
        v = v[rng.choice(len(v), 6000, replace=False)]
    pos = ((v[:, None, :] - LUT[None, :, :]) ** 2).sum(axis=-1).argmin(axis=1) / 255.0
    band = np.clip(np.round(pos * (len(STOPS) - 1)).astype(int), 0, len(STOPS) - 1)
    return [round(float(x), 4) for x in np.bincount(band, minlength=len(STOPS)) / len(band)]


def fill(x):
    x = np.array(x, dtype=float)
    bad = np.isnan(x)
    if bad.all():
        raise RuntimeError("No usable temperature data found in the images (were they downloaded with a base map?)")
    if bad.any():
        x[bad] = np.interp(np.where(bad)[0], np.where(~bad)[0], x[~bad])
    return x


def smooth(x, k):
    p = k // 2
    return np.convolve(np.pad(x, (p, p), mode="edge"), np.ones(k) / k, mode="valid")


def p95(x):
    return np.percentile(np.abs(x), 95) + 1e-9


def span(x):
    lo, hi = float(x.min()), float(x.max())
    pad = (hi - lo) * CAL_MARGIN + 1e-6
    return [lo - pad, hi + pad]


def compose_music(north, south, bands, recalibrate=False, bpm_range=None, arousal_scale=1.0, style="orchestra",
                  rising_is_major=True):
    n = len(north)
    tn = smooth(fill(north), SMOOTH)
    ts = smooth(fill(south), SMOOTH)
    gn, gs = np.gradient(tn), np.gradient(ts)
    bs = np.stack([smooth(fill(np.array(bands, dtype=float)[:, k]), SMOOTH) for k in range(len(STOPS))], axis=1)

    # Calibration is computed ONCE (first build) and then frozen, so notes already composed for
    # earlier days keep the same pitch / tempo / instrumentation when new days are added.
    cal = None
    if not recalibrate and os.path.exists(CAL_PATH):
        try:
            with open(CAL_PATH) as f:
                cal = json.load(f)
        except Exception:
            cal = None
    changed = False
    if cal is None:
        cal = {"tn": span(tn), "ts": span(ts), "gn": float(p95(gn)), "gs": float(p95(gs))}
        rate0 = smooth((np.abs(gn / cal["gn"]) + np.abs(gs / cal["gs"])) / 2, 5)
        cal["rate"] = float(np.percentile(rate0, 90))
        changed = True
    if "band_lo" not in cal:                              # added with the orchestra; older files get it once
        cal["band_lo"] = [float(x) for x in np.percentile(bs, 5, axis=0)]
        cal["band_hi"] = [float(x) for x in np.percentile(bs, 95, axis=0)]
        changed = True
    if changed:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(CAL_PATH, "w") as f:
            json.dump(cal, f)
        print("Calibration saved (pitch, tempo and instrument ranges are now fixed).")

    nn = np.clip((tn - cal["tn"][0]) / (cal["tn"][1] - cal["tn"][0]), 0, 1)
    ns = np.clip((ts - cal["ts"][0]) / (cal["ts"][1] - cal["ts"][0]), 0, 1)
    sn = gn / cal["gn"]
    ss = gs / cal["gs"]
    net = smooth((sn + ss) / 2, 15)

    is_major = np.zeros(n, bool)                          # warming -> major, cooling -> minor (with hysteresis)
    mode_net = net if rising_is_major else -net           # rising_is_major=False: a rise sounds minor (CO2 layer)
    state = bool(mode_net[0] >= 0)
    for i in range(n):
        if state and mode_net[i] < -MODE_HYST:
            state = False
        elif not state and mode_net[i] > MODE_HYST:
            state = True
        is_major[i] = state

    rate = smooth((np.abs(sn) + np.abs(ss)) / 2, 5)
    r = np.clip(rate / (cal["rate"] + 1e-9), 0, 1)
    lo_bpm, hi_bpm = bpm_range or (BPM_MIN, BPM_MAX)
    bpm = smooth(lo_bpm + r * (hi_bpm - lo_bpm), 5)       # faster when change is sharper
    beat = 60.0 / bpm
    onset = np.concatenate([[0], np.cumsum(beat)[:-1]])
    total = float(onset[-1] + beat[-1])

    vol = np.zeros(n)                                     # crescendo when warming, decrescendo when cooling
    v = 0.45
    for i in range(n):
        v = float(np.clip(v + 0.035 * np.clip(net[i], -1.5, 1.5), 0.2, 1.0))
        vol[i] = v

    # colour -> orchestra section loudness (relative to how much of that colour is usual)
    lo, hi = np.array(cal["band_lo"]), np.array(cal["band_hi"])
    rel = np.clip((bs - lo) / (hi - lo + 1e-9), 0, 1)
    level = orchestra.BASE_LEVEL + (1 - orchestra.BASE_LEVEL) * rel

    warmth = (nn + ns) / 2
    arousal = np.clip((0.65 * r + 0.35 * rel[:, -1]) * arousal_scale, 0, 1)  # speed of change + how much red (heat)
    emotion = orchestra.emotions(is_major, warmth, arousal)

    stereo, change = orchestra.compose(onset, beat, total, vol, nn, ns, r, is_major, level, emotion, style=style)
    return dict(stereo=stereo, onset=onset, beat=beat, bpm=bpm, major=is_major, net=net,
                vol=vol, total=total, tn=tn, ts=ts, level=level, emotion=emotion, change=change)


def write_wav(path, stereo):
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((stereo * 32767).astype("<i2").tobytes())
    os.replace(tmp, path)                        # swap in atomically so the page never sees a half-written file


MP3_DELAY = 1105                                 # samples the MP3 encoder adds at the start (LAME); trimmed so timing stays exact


def write_mp3(path, stereo):
    """Compressed copy of the music for the web page. Returns True if written (needs the lameenc package)."""
    try:
        import lameenc
    except ImportError:
        print("lameenc is not installed (pip install lameenc): the page will play music.wav instead.")
        return False
    enc = lameenc.Encoder()
    enc.set_bit_rate(MP3_KBPS)
    enc.set_in_sample_rate(SR)
    enc.set_channels(2)
    enc.set_quality(2)
    pcm = (np.clip(stereo[MP3_DELAY:], -1, 1) * 32767).astype("<i2").tobytes()
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(bytes(enc.encode(pcm)) + bytes(enc.flush()))
    os.replace(tmp, path)
    return True


def save_frame(arr, path):
    """Save one globe frame. WebP keeps no-data (black) pixels exact as transparency, colours lossy."""
    tmp = path + ".tmp"
    if FRAME_FORMAT == "webp":
        alpha = np.where(arr.max(axis=-1) > 12, 255, 0).astype(np.uint8)
        Image.fromarray(np.dstack([arr, alpha]), "RGBA").save(tmp, format="WEBP", quality=FRAME_QUALITY,
                                                               alpha_quality=100, method=4)
    else:
        Image.fromarray(arr).save(tmp, format="PNG", compress_level=3)
    os.replace(tmp, path)


def download_base():
    path = os.path.join(OUT_DIR, "base.jpg")
    if os.path.exists(path):
        return
    url = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
    params = {
        "version": "1.3.0", "service": "WMS", "request": "GetMap",
        "layers": "BlueMarble_NextGeneration", "styles": "", "format": "image/jpeg",
        "crs": "EPSG:4326", "bbox": "-90,-180,90,180", "width": 2048, "height": 1024,
    }
    try:
        r = requests.get(url, params=params, timeout=90)
        if r.ok and "image" in r.headers.get("Content-Type", ""):
            with open(path, "wb") as f:
                f.write(r.content)
            print("Downloaded base map (Blue Marble).")
        else:
            print("Base map download failed, continuing without it.")
    except requests.RequestException as e:
        print("Base map download failed, continuing without it:", e)


def _download_overlay(layer, filename, label):
    """Download a GIBS layer as a transparent global PNG. Returns True if saved."""
    path = os.path.join(OUT_DIR, filename)
    if os.path.exists(path):
        return True
    url = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
    try:
        cap = requests.get(url, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"}, timeout=90)
        if layer.encode() not in cap.content:
            print(f"{layer} is not offered as an image by GIBS; the page will draw {label} itself.")
            return False
        params = {
            "version": "1.3.0", "service": "WMS", "request": "GetMap",
            "layers": layer, "styles": "", "format": "image/png",
            "transparent": "TRUE", "crs": "EPSG:4326", "bbox": "-90,-180,90,180",
            "width": 4096, "height": 2048,
        }
        r = requests.get(url, params=params, timeout=120)
        if r.ok and "image" in r.headers.get("Content-Type", ""):
            from io import BytesIO
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            if img.getchannel("A").getextrema()[1] > 0:
                os.makedirs(OUT_DIR, exist_ok=True)
                img.save(path)
                print(f"Downloaded {label} layer.")
                return True
        print(f"{label} layer came back empty; the page will draw {label} itself.")
    except Exception as e:
        print(f"{label} download failed; the page will draw {label} itself:", e)
    return False


def download_borders():
    return _download_overlay("DoS_International_Boundaries", "borders.png", "borders")


def download_coastlines():
    return _download_overlay("Coastlines_15m", "coastlines.png", "coastlines")


def ensure_borders():
    """Add borders and coastlines to an already-built dataset without rebuilding frames or music."""
    if not (DOWNLOAD_BORDERS and os.path.exists(TL_PATH)):
        return
    with open(TL_PATH) as f:
        tl = json.load(f)
    changed = False
    if "has_borders" not in tl:
        tl["has_borders"] = download_borders()
        changed = True
    if "has_coast" not in tl:
        tl["has_coast"] = download_coastlines()
        changed = True
    if changed:
        with open(TL_PATH, "w") as f:
            json.dump(tl, f)


def build(full=False, recalibrate=False):
    """Build (or incrementally update) frames, music and timeline.
    full=True redoes everything; otherwise only new or changed days are reprocessed."""
    files = sorted(glob.glob(os.path.join(FOLDER, "*.png")))
    if ROLLING_DAYS:
        files = files[-ROLLING_DAYS:]
    if len(files) < 10:
        raise RuntimeError(f"Not enough images in '{FOLDER}'. Run download_ice.py or update_data.py first.")
    os.makedirs(FRAMES_DIR, exist_ok=True)

    dates = [dt.date.fromisoformat(os.path.splitext(os.path.basename(f))[0][-10:]) for f in files]
    n = len(files)
    src_mtime = [os.path.getmtime(f) for f in files]
    print(f"Found {n} images: {dates[0]} to {dates[-1]}")

    prev = {}
    stats_cache = {}
    if not full:
        try:
            with open(TL_PATH) as f:
                prev = json.load(f)
        except Exception:
            prev = {}
        try:
            with open(STATS_PATH) as f:
                stats_cache = json.load(f)
        except Exception:
            stats_cache = {}

    cache, stats = {}, {}

    def get(j):
        if j not in cache:
            img = Image.open(files[j]).convert("RGB")
            h = max(2, int(img.height * FRAME_WIDTH / img.width))
            a = np.asarray(img.resize((FRAME_WIDTH, h), Image.BILINEAR))
            cache[j] = a
            mid = a.shape[0] // 2
            stats[j] = (half_stats(a[:mid]), half_stats(a[mid:]), color_bands(a))
        return cache[j]

    keep = set()
    rebuilt = 0
    for i in range(n):
        key = dates[i].isoformat()
        out = os.path.join(FRAMES_DIR, key + "." + FRAME_FORMAT)
        keep.add(key + "." + FRAME_FORMAT)
        near = [j for j in range(max(0, i - FILL_DAYS), min(n, i + FILL_DAYS + 1))
                if abs((dates[j] - dates[i]).days) <= FILL_DAYS]

        need_frame = full or (not os.path.exists(out)) or any(src_mtime[j] > os.path.getmtime(out) for j in near)
        sc = stats_cache.get(key)
        need_stats = sc is None or "b" not in sc or abs(sc.get("mtime", 0) - src_mtime[i]) > 1e-3

        if need_frame:
            for j in near:
                get(j)
            if FILL_DAYS > 0 and len(near) > 1:
                stack = np.stack([cache[j] for j in near]).astype(np.float32)
                valid = (stack.max(axis=-1) > 12)[..., None]
                cnt = valid.sum(axis=0)
                out_arr = ((stack * valid).sum(axis=0) / np.maximum(cnt, 1)).astype(np.uint8)
            else:
                out_arr = cache[i]
            save_frame(out_arr, out)
            rebuilt += 1
            if rebuilt % 20 == 1:
                print(f"  frames rebuilt: {rebuilt} (day {i + 1}/{n})")
        elif need_stats:
            get(i)

        for k in [k for k in cache if k < i - FILL_DAYS]:
            del cache[k]

    for old in glob.glob(os.path.join(FRAMES_DIR, "*.png")) + glob.glob(os.path.join(FRAMES_DIR, "*.webp")):
        if os.path.basename(old) not in keep:
            os.remove(old)                        # days that left the timeline, or frames in the other format
    for leftover in glob.glob(os.path.join(FRAMES_DIR, "*.tmp")):
        os.remove(leftover)

    north, south, bands, new_cache = [], [], [], {}
    for i in range(n):
        key = dates[i].isoformat()
        if i in stats:
            nv, sv, bv = stats[i]
        else:
            nv, sv, bv = stats_cache[key]["n"], stats_cache[key]["s"], stats_cache[key]["b"]
        north.append(nv)
        south.append(sv)
        bands.append(bv)
        new_cache[key] = {"mtime": src_mtime[i], "n": nv, "s": sv, "b": bv}
    with open(STATS_PATH, "w") as f:
        json.dump(new_cache, f)

    print("Composing the orchestra ...")
    m = compose_music(north, south, bands, recalibrate=recalibrate)
    write_wav(os.path.join(OUT_DIR, "music.wav"), m["stereo"])
    has_mp3 = write_mp3(os.path.join(OUT_DIR, "music.mp3"), m["stereo"])

    if DOWNLOAD_BASE:
        download_base()
    if "has_borders" in prev:
        has_borders = bool(prev["has_borders"])
    else:
        has_borders = download_borders() if DOWNLOAD_BORDERS else False
    if "has_coast" in prev:
        has_coast = bool(prev["has_coast"])
    else:
        has_coast = download_coastlines() if DOWNLOAD_BORDERS else False

    timeline = {
        "n": n,
        "dates": [d.isoformat() for d in dates],
        "frames": [d.isoformat() for d in dates],
        "frame_ext": FRAME_FORMAT,
        "frame_ver": [int(os.path.getmtime(os.path.join(FRAMES_DIR, d.isoformat() + "." + FRAME_FORMAT))) for d in dates],
        "music": "music.mp3" if has_mp3 else "music.wav",
        "onset": [round(float(x), 4) for x in m["onset"]],
        "beat": [round(float(x), 4) for x in m["beat"]],
        "bpm": [round(float(x), 1) for x in m["bpm"]],
        "major": [bool(x) for x in m["major"]],
        "vol": [round(float(x), 3) for x in m["vol"]],
        "net": [round(float(x), 3) for x in m["net"]],
        "tn": [round(float(x), 2) for x in m["tn"]],
        "ts": [round(float(x), 2) for x in m["ts"]],
        "instruments": orchestra.INSTRUMENTS,
        "inst": [[round(float(x), 2) for x in row] for row in m["level"]],
        "emotion": m["emotion"],
        "key_change": [bool(x) for x in m["change"]],
        "total": round(m["total"], 3),
        "has_base": os.path.exists(os.path.join(OUT_DIR, "base.jpg")),
        "has_borders": has_borders,
        "has_coast": has_coast,
        "t_min": T_MIN, "t_max": T_MAX,
        "version": int(time.time()),
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "first_date": dates[0].isoformat(),
        "latest_date": dates[-1].isoformat(),
    }
    tmp = TL_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(timeline, f)
    os.replace(tmp, TL_PATH)                     # last step: the page only sees the new data once everything is ready
    print(f"Done. {n} days, {rebuilt} frames rebuilt. Music is {m['total']:.0f} s, "
          f"{m['bpm'].min():.0f}-{m['bpm'].max():.0f} BPM, {m['major'].mean() * 100:.0f}% major, "
          f"{int(m['change'].sum())} key changes.")
    return {"days": n, "frames_rebuilt": rebuilt, "latest": dates[-1].isoformat()}


if __name__ == "__main__":
    try:
        build(full="--full" in sys.argv, recalibrate="--recalibrate" in sys.argv)
    except RuntimeError as e:
        raise SystemExit(str(e))
