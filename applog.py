"""EmoEarth's log: one place that records what happened and anything that went wrong.

Written to logs/emoearth.log (on Azure: /home/LogFiles/emoearth/emoearth.log, which survives redeploys),
kept small by rotation (1 MB x 5 files), and also printed, so it shows in the terminal and in Azure's
Log stream. Change the folder with LOG_DIR in .env or the Azure settings.

What is recorded (never passwords, tokens or keys):
  server start and sign-in mode; sign-ins, failed sign-ins, sign-outs and blocked accounts;
  every server error with its full traceback (a crash), slow or failing requests;
  data updates; and errors from people's browsers (page script errors, frames or music that fail to load).
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _setting(name):
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


def log_dir():
    d = _setting("LOG_DIR")
    if not d:
        d = "/home/LogFiles/emoearth" if os.environ.get("WEBSITE_HOSTNAME") else os.path.join(BASE_DIR, "logs")
    return d if os.path.isabs(d) else os.path.join(BASE_DIR, d)


LOG_DIR = log_dir()
LOG_PATH = os.path.join(LOG_DIR, "emoearth.log")
log = logging.getLogger("emoearth")

if not log.handlers:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(fmt)
    log.addHandler(out)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError as e:
        log.warning("Log file not available (%s); logging to the terminal only.", e)
    log.propagate = False


def tail(lines=200, level=None):
    """The last `lines` lines of the log (newest last); level='WARNING' keeps warnings and errors only."""
    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            text = f.read().splitlines()
    except OSError:
        return []
    if level:
        keep = {"WARNING": ("WARNING", "ERROR", "CRITICAL"), "ERROR": ("ERROR", "CRITICAL")}.get(level.upper(), ())
        out, inside = [], False
        for ln in text:
            head = ln[21:29].strip() if len(ln) > 29 and ln[4] == "-" else None
            if head is not None:
                inside = head in keep
            if inside:
                out.append(ln)               # also keeps a traceback's lines under its error line
        text = out
    return text[-lines:]


if __name__ == "__main__":
    # python applog.py            -> last 50 lines
    # python applog.py errors     -> warnings and errors only
    lvl = "WARNING" if "errors" in sys.argv[1:] else None
    print("\n".join(tail(50, lvl)) or f"(no log yet at {LOG_PATH})")
