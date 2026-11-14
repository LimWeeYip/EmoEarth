"""Export the sound wave of static/data/music.wav as tables (CSV + pandas DataFrames).

  python export_wave.py              daily summary + 100 Hz envelope
  python export_wave.py --rate 50    envelope with 50 rows per second instead of 100
  python export_wave.py --raw        also write every audio sample (very large: ~16 million rows)

Writes to static/data/:
  wave_daily.csv      one row per day (= one beat): date, time, tempo, key, emotion, instrument levels, loudness
  wave_envelope.csv   the wave shape over time: for each short window, its min/max (the wave outline) and RMS loudness
  wave_raw.csv        (only with --raw) time, left, right for every sample

In Python:  import export_wave; daily, env = export_wave.load()   # returns pandas DataFrames
"""
import os
import sys
import json
import wave

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, "static", "data")
WAV = os.path.join(DATA, "music.wav")
TL = os.path.join(DATA, "timeline.json")


def read_wav(path=WAV):
    with wave.open(path, "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype="<i2").reshape(-1, ch).astype(np.float32) / 32768.0
    return sr, x


def db(v):
    return np.round(20 * np.log10(np.maximum(v, 1e-6)), 2)


def envelope(sr, x, rate=100):
    """One row per 1/rate seconds: the wave's min/max (outline), RMS loudness and peak, per channel."""
    hop = int(sr / rate)
    m = len(x) // hop
    seg = x[: m * hop].reshape(m, hop, x.shape[1])
    mono = seg.mean(axis=2)
    rms = np.sqrt((seg ** 2).mean(axis=1))
    df = pd.DataFrame({
        "time_s": np.round(np.arange(m) * hop / sr, 4),
        "min": np.round(mono.min(axis=1), 5),
        "max": np.round(mono.max(axis=1), 5),
        "rms_left": np.round(rms[:, 0], 5),
        "rms_right": np.round(rms[:, 1], 5) if x.shape[1] > 1 else np.round(rms[:, 0], 5),
        "peak": np.round(np.abs(seg).max(axis=(1, 2)), 5),
    })
    df["rms"] = np.round(np.sqrt((df.rms_left ** 2 + df.rms_right ** 2) / 2), 5)
    df["loudness_db"] = db(df["rms"].values)
    return df


def daily(sr, x, tl):
    rows = []
    names = tl.get("instruments", [])
    for i, d in enumerate(tl["dates"]):
        a, b = tl["onset"][i], tl["onset"][i] + tl["beat"][i]
        seg = x[int(a * sr): int(b * sr)]
        rms = float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0
        row = {
            "date": d, "start_s": a, "duration_s": tl["beat"][i], "bpm": tl["bpm"][i],
            "key": "C major" if tl["major"][i] else "C minor",
            "key_change": bool(tl.get("key_change", [False] * len(tl["dates"]))[i]),
            "emotion": tl.get("emotion", [""] * len(tl["dates"]))[i],
            "volume": tl["vol"][i], "trend": tl["net"][i],
            "north_K": tl["tn"][i], "south_K": tl["ts"][i],
            "rms": round(rms, 5), "loudness_db": float(db(np.array([rms]))[0]),
            "peak": round(float(np.abs(seg).max()) if len(seg) else 0.0, 5),
        }
        for k, name in enumerate(names):
            row["level_" + name.lower().replace(" & ", "_").replace(" ", "_")] = tl["inst"][i][k]
        rows.append(row)
    return pd.DataFrame(rows)


def load(rate=100):
    """Return (daily, envelope) as pandas DataFrames, straight from music.wav and timeline.json."""
    sr, x = read_wav()
    with open(TL) as f:
        tl = json.load(f)
    env = envelope(sr, x, rate)
    # label each envelope row with the day being played
    idx = np.searchsorted(np.array(tl["onset"]), env["time_s"].values, side="right") - 1
    env.insert(1, "date", np.array(tl["dates"])[np.clip(idx, 0, len(tl["dates"]) - 1)])
    return daily(sr, x, tl), env


if __name__ == "__main__":
    rate = int(sys.argv[sys.argv.index("--rate") + 1]) if "--rate" in sys.argv else 100
    d, e = load(rate)
    d.to_csv(os.path.join(DATA, "wave_daily.csv"), index=False)
    e.to_csv(os.path.join(DATA, "wave_envelope.csv"), index=False)
    print(f"wave_daily.csv     {len(d)} rows x {d.shape[1]} columns")
    print(f"wave_envelope.csv  {len(e)} rows x {e.shape[1]} columns ({rate} per second)")
    if "--raw" in sys.argv:
        sr, x = read_wav()
        raw = pd.DataFrame({"time_s": np.round(np.arange(len(x)) / sr, 6), "left": np.round(x[:, 0], 5),
                            "right": np.round(x[:, -1], 5)})
        raw.to_csv(os.path.join(DATA, "wave_raw.csv"), index=False)
        print(f"wave_raw.csv       {len(raw)} rows")
