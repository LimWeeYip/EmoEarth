"""Spoken description of the EmoEarth timeline, for blind and low-vision listeners.

  python narrate.py            make static/data/narration.json (+ narration.wav if a voice engine is available)
  python narrate.py --local    skip Gemini and use the description built from the data
  python narrate.py --fresh    delete the old narration.wav first (app.py runs this on the first page load)
  python narrate.py --voices   list the voices on this computer (pick one with NARRATION_VOICE=Name in .env)

What it writes (the page reads both):
  static/data/narration.json   {"text", "source", "audio", "latest_date", "timeline_version", "generated_at"}
  static/data/narration.wav    the text spoken by pyttsx3 (only if pyttsx3 works on this computer)

It never fails hard: if there is no API key, Gemini is busy (high traffic) or the voice engine is missing,
it falls back to a description built from timeline.json, and the web page can speak the text itself.

API key: put GEMINI_API_KEY=your-key in a file called .env in this folder (it is in .gitignore),
or set the GEMINI_API_KEY environment variable. Never write the key in a .py file.
"""
import os
import sys
import json
import time
import datetime as dt
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, "static", "data")
TL_PATH = os.path.join(DATA, "timeline.json")
OUT_JSON = os.path.join(DATA, "narration.json")
OUT_WAV = os.path.join(DATA, "narration.wav")

MODEL = "gemini-3.5-flash-lite" #"gemini-3.8-flash"
MAX_WORDS = 60
TIMEOUT_S = 400              # give up on one Gemini attempt after this many seconds (busy servers can hang)
RETRIES = 4                 # Gemini attempts; waits 3, 6, 12 s between them (busy servers usually recover)

# SYSTEM_INSTRUCTION = (
#     "You are an accessible audio-description assistant for blind users. "
#     "Translate environmental telemetry and satellite data trends into spatial and temporal descriptions of Earth. "
#     "In the provided dataset, 'TN' is the Northern Hemisphere ice surface temperature and 'TS' the Southern, in kelvin. "
#     "Speak in plain, warm sentences that sound natural when read aloud. Say temperatures in degrees Celsius in words, "
#     "and do not use symbols, abbreviations, lists or markdown."
# )


SYSTEM_INSTRUCTION = (
    "You are an accessible audio-description assistant for blind users. "
    "Translate environmental telemetry and satellite data trends into spatial and temporal descriptions of Earth. "
    "In the provided dataset, if there are 'TN' and 'TS' values, 'TN' is the Northern Hemisphere ice surface temperature and 'TS' the Southern, in kelvin. "
    "Speak in plain, warm sentences that sound natural when read aloud. "
)


USER_PROMPT = (
    "Analyze this time series of daily satellite data and describe the shifting environmental conditions "
    f"across the hemispheres as a tactile, immersive experience. Keep it strictly under {MAX_WORDS} words."
)


def setting(name):
    """A value from the environment, or from the .env file in this folder."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(os.path.join(BASE_DIR, ".env")) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.strip() == name and v.strip():
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def pick_voice(voices):
    """NARRATION_VOICE in .env (part of a voice name, e.g. Rishi or Tingting), else the second voice as before."""
    want = (setting("NARRATION_VOICE") or "").lower()
    if want:
        for v in voices:
            if want in (v.name or "").lower() or want in (v.id or "").lower():
                return v
        print(f'Voice "{want}" not found on this computer (see: python narrate.py --voices); using the default.')
    return voices[1] if len(voices) > 1 else voices[0]


def list_voices():
    import pyttsx3
    engine = pyttsx3.init()
    for v in engine.getProperty("voices"):
        langs = ", ".join(str(x) for x in (getattr(v, "languages", None) or []))
        print(f"{v.name:<28} {langs}")
    print('\nPut the one you like in .env, e.g.  NARRATION_VOICE=Rishi   then run: python narrate.py')


def api_key():
    """GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment, or from a .env file in this folder."""
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with open(os.path.join(BASE_DIR, ".env")) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v.strip():
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def _c(k):
    return round(k - 273.15)


def _deg(c):
    return ("minus " if c < 0 else "") + f"{abs(c)} degrees"


def _month(d):
    return dt.date.fromisoformat(d).strftime("%B")


def _day(d):
    x = dt.date.fromisoformat(d)
    return f"{x.day} {x.strftime('%B')}"


def local_description(tl):
    """A plain description built from the data itself: used when Gemini is not available."""
    dates, tn, ts = tl["dates"], tl["tn"], tl["ts"]
    i_nmax = max(range(len(tn)), key=tn.__getitem__)
    i_smin = min(range(len(ts)), key=ts.__getitem__)
    parts = [f"EmoEarth, from {_day(dates[0])} to {_day(dates[-1])} {dates[-1][:4]}."]
    parts.append(f"In the north, the frozen surface goes from about {_deg(_c(tn[0]))}, "
                 f"warms to {_deg(_c(tn[i_nmax]))} in {_month(dates[i_nmax])}, "
                 f"and ends near {_deg(_c(tn[-1]))}.")
    parts.append(f"The south moves the other way, from {_deg(_c(ts[0]))} down to {_deg(_c(ts[i_smin]))} "
                 f"in {_month(dates[i_smin])}, then back to {_deg(_c(ts[-1]))}.")
    emo = tl.get("emotion")
    if emo:
        common = max(set(emo), key=emo.count)
        kc = sum(tl.get("key_change", []))
        parts.append(f"The orchestra feels mostly {common.lower()}, and changes between major and minor keys {kc} times.")
    return " ".join(parts)


WHY_NO_GEMINI = "Gemini is busy or unreachable"


def gemini_description(tl):
    """Ask Gemini for the description. Returns None if there is no key, no library, or the service is busy."""
    global WHY_NO_GEMINI
    key = api_key()
    if not key:
        WHY_NO_GEMINI = "no GEMINI_API_KEY (add it to .env)"
        print("No GEMINI_API_KEY found: using the description built from the data.")
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        WHY_NO_GEMINI = "google-genai is not installed"
        print("google-genai is not installed (pip install google-genai): using the description built from the data.")
        return None
    data = json.dumps({"n": tl.get("n"), "dates": tl.get("dates"), "TN": tl.get("tn"), "TS": tl.get("ts")})
    try:
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))
    except Exception:                                  # older google-genai without HttpOptions
        client = genai.Client(api_key=key)
    for attempt in range(RETRIES):
        try:
            r = client.models.generate_content(
                model=MODEL, contents=[data, USER_PROMPT],
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION,
                                                   temperature=0.5, max_output_tokens=2000))
            text = (r.text or "").strip()
            if text:
                return text
        except Exception as e:                         # rate limits, timeouts, server busy ...
            msg = str(e)
            busy = any(x in msg for x in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "high demand"))
            print(f"Gemini attempt {attempt + 1} failed: " + ("busy (high demand), will retry" if busy else msg[:200]))
            WHY_NO_GEMINI = "Gemini busy (high demand)" if busy else "Gemini error: " + msg[:120]
            if not busy and any(x in msg for x in ("400", "401", "403", "404", "API key", "PERMISSION")):
                break                                   # key or model problem: retrying will not help
            if attempt < RETRIES - 1:
                time.sleep(3 * 2 ** attempt)
    return None


def to_real_wav(path):
    """On a Mac, pyttsx3 saves Apple AIFF audio even when the name ends in .wav, and Chrome, Firefox and VS Code
    cannot play AIFF. Convert it in place to a normal 16-bit WAV with macOS's own afconvert. True if the file is
    (now) a real WAV."""
    with open(path, "rb") as f:
        head = f.read(12)
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return True                                    # already a real WAV (Windows, Linux)
    if head[:4] != b"FORM":
        print("Voice engine wrote an unknown audio format: the web page will read the text aloud instead.")
        return False
    import shutil
    import subprocess
    if not shutil.which("afconvert"):
        print("Voice engine wrote AIFF and afconvert is missing: the web page will read the text aloud instead.")
        return False
    out = path + ".conv.wav"
    try:
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", path, out], check=True, capture_output=True,
                       timeout=120)
        os.replace(out, path)
        return True
    except Exception as e:
        print(f"Could not convert the narration to WAV: {e}")
        if os.path.exists(out):
            os.remove(out)
        return False


def speak_to_wav(text, path):
    """Save the text as speech with pyttsx3. Returns True if a usable file was written."""
    try:
        import pyttsx3
    except ImportError:
        print("pyttsx3 is not installed: the web page will read the text aloud instead.")
        return False
    tmp = f"{path}.{os.getpid()}.tmp.wav"
    engine = None
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        engine.setProperty("rate", 165)
        voice = pick_voice(voices)
        engine.setProperty("voice", voice.id)
        print(f"Voice: {voice.name}")
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        if os.path.exists(tmp) and os.path.getsize(tmp) > 1000 and to_real_wav(tmp):
            os.replace(tmp, path)
            return True
    except Exception as e:
        print(f"Voice engine failed: {e}")
    finally:
        # pyttsx3 (especially on Windows) prints a long harmless error if its engine is cleaned up while Python
        # is shutting down. Shut it down here, while everything still works.
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
            del engine
            import gc
            gc.collect()
    if os.path.exists(tmp):
        os.remove(tmp)
    return False

SETMAX_DATA = 100 # Lower this if Gemini is too slow or the narration is too long. The web page will read the text aloud anyway.


def write_json(out):
    tmp = f"{OUT_JSON}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, OUT_JSON)


def clear_audio():
    """Delete the old narration.wav before making a new one. narration.json keeps its text but says there is no
    audio, so while the new narration is being made the page reads the old text aloud with the browser's voice."""
    if os.path.exists(OUT_WAV):
        os.remove(OUT_WAV)
        print("Old narration.wav deleted.")
    try:
        with open(OUT_JSON) as f:
            old = json.load(f)
        if old.get("audio"):
            old["audio"] = None
            write_json(old)
    except (OSError, ValueError):
        pass


def run(use_gemini=True, fresh=False):
    if fresh:
        clear_audio()
    with open(TL_PATH) as f:
        tl_raw = json.load(f)
    total_len = tl_raw.get("n") or len(tl_raw["dates"])
    if total_len <= SETMAX_DATA:
        print(f"Timeline has {total_len} frames: sending all of them.")
        i = list(range(total_len))
    else:
        print(f"Timeline has {total_len} frames: preprocessing to {SETMAX_DATA} frames for narration.")
        i = np.linspace(0, total_len - 1, SETMAX_DATA).astype(int)
    tl = {
        "n": len(i),
        "dates": [tl_raw["dates"][j] for j in i],
        "tn": [tl_raw["tn"][j] for j in i],
        "ts": [tl_raw["ts"][j] for j in i],
        "emotion": tl_raw.get("emotion"),
        "key_change": tl_raw.get("key_change"),
        "latest_date": tl_raw.get("latest_date") or tl_raw["dates"][-1],
        "version": tl_raw.get("version"),
    }

    text = gemini_description(tl) if use_gemini else None
    source = "gemini" if text else "local"
    if not text and use_gemini:
        # Gemini busy or unreachable: keep an earlier Gemini narration rather than replacing it with the plain one
        try:
            with open(OUT_JSON) as f:
                old = json.load(f)
            if old.get("source") == "gemini" and old.get("text"):
                print(f"No new Gemini text ({WHY_NO_GEMINI}): keeping the earlier Gemini narration. "
                      "Run narrate.py again later to update it.")
                if not (old.get("audio") and os.path.exists(OUT_WAV)) and speak_to_wav(old["text"], OUT_WAV):
                    old["audio"] = "narration.wav"
                    write_json(old)
                return old
        except (OSError, ValueError):
            pass
    if not text:
        text = local_description(tl)
    has_audio = speak_to_wav(text, OUT_WAV)
    if not has_audio and os.path.exists(OUT_WAV):
        os.remove(OUT_WAV)
        print("Old audio removed...")                             # never leave old audio that no longer matches the text
    out = {
        "text": text, "source": source, "audio": "narration.wav" if has_audio else None,
        "latest_date": tl.get("latest_date"), "timeline_version": tl.get("version"),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    write_json(out)
    print(f"Narration ({source}{', with audio' if has_audio else ', text only'}): {text}")
    return out


if __name__ == "__main__":
    if "--voices" in sys.argv:
        list_voices()
        sys.stdout.flush()
        os._exit(0)
    t0 = time.perf_counter()
    run(use_gemini="--local" not in sys.argv, fresh="--fresh" in sys.argv)
    print(f"Done in {time.perf_counter() - t0:.1f} s")
    # Exit right away: pyttsx3 (on Windows) otherwise prints a long, harmless "DriverProxy.__del__" error while
    # Python shuts down. All files are already written and closed at this point.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
