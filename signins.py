"""Every sign-in to EmoEarth, written down and counted (README "Sign-in records and /stats").

One CSV row per sign-in in signins.csv, next to the app log (logs/ on your computer,
/home/LogFiles/emoearth on Azure, so it survives redeploys):
    time, user, method, address, browser
method: "email only" (the email-only page), "password" or "google.com" (Firebase), "local account" (auth.py).

    python signins.py                        # the totals in the terminal
    python signins.py reset                  # start counting from zero (the old records are kept as a backup)
    python signins.py reset guest "email only"   # remove only those kinds (e.g. test visits), keep the rest
"""
import os
import csv
import sys
import threading
import datetime as dt
from collections import Counter

import applog

PATH = os.path.join(applog.LOG_DIR, "signins.csv")
FIELDS = ["time", "user", "method", "address", "browser"]
_lock = threading.Lock()


def record(user, method, address="", browser=""):
    """Add one sign-in. Never raises: a full disk must not stop people signing in."""
    row = {"time": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "user": user, "method": method,
           "address": address, "browser": " ".join((browser or "").split())[:160]}
    try:
        with _lock:
            new = not os.path.exists(PATH)
            os.makedirs(os.path.dirname(PATH), exist_ok=True)
            with open(PATH, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                w.writerow(row)
    except OSError as e:
        applog.log.error("Could not record the sign-in of %s (%s)", user, e)


def rows():
    try:
        with open(PATH, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def stats(days=30, latest=50):
    """Totals for the /stats page."""
    rs = rows()
    today = dt.date.today()
    per_day = Counter(r["time"][:10] for r in rs)
    people = Counter(r["user"].lower() for r in rs)
    week = [r for r in rs if r["time"][:10] >= (today - dt.timedelta(days=6)).isoformat()]
    guests = [r for r in rs if r["method"] == "guest"]
    gweek = [r for r in guests if r["time"][:10] >= (today - dt.timedelta(days=6)).isoformat()]
    gday = Counter(r["time"][:10] for r in guests)
    return {
        "total": len(rs),
        "people": len(people),
        "today": per_day.get(today.isoformat(), 0),
        "week": len(week),
        "people_week": len({r["user"].lower() for r in week}),
        "by_method": Counter(r["method"] for r in rs).most_common(),
        "per_day": [((today - dt.timedelta(days=k)).isoformat(), per_day.get((today - dt.timedelta(days=k)).isoformat(), 0))
                    for k in range(days)],
        "top": people.most_common(10),
        "latest": rs[-latest:][::-1],
        "first": rs[0]["time"] if rs else None,
        "guests": len(guests),                                       # Guest Only visits
        "guest_people": len({r["user"] for r in guests}),            # different guest browsers
        "guest_today": gday.get(today.isoformat(), 0),
        "guest_week": len(gweek),
        "guest_share": round(100 * len(guests) / len(rs)) if rs else 0,
        "guest_per_day": {d: gday.get(d, 0) for d, _ in [((today - dt.timedelta(days=k)).isoformat(), 0) for k in range(days)]},
    }


def reset(methods=None):
    """Start again: the current file is renamed to signins_backup_<time>.csv (nothing is deleted).
    With methods (e.g. ["guest", "email only"]) only those rows are removed; the others are kept."""
    with _lock:
        rs = rows()
        if not rs:
            return 0, None
        stem = os.path.join(os.path.dirname(PATH), "signins_backup_" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        backup, k = stem + ".csv", 1
        while os.path.exists(backup):                    # never overwrite an earlier backup
            k += 1
            backup = f"{stem}_{k}.csv"
        os.replace(PATH, backup)
        keep = [r for r in rs if methods and r["method"] not in methods]
        if keep:
            with open(PATH, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(keep)
    applog.log.warning("Sign-in records reset (%s): %d removed, %d kept, backup %s",
                       ", ".join(methods) if methods else "all", len(rs) - len(keep), len(keep), backup)
    return len(rs) - len(keep), backup


if __name__ == "__main__":
    if sys.argv[1:2] == ["reset"]:
        methods = sys.argv[2:] or None
        what = "the " + " and ".join(f'"{m}"' for m in methods) + " sign-ins" if methods else "ALL sign-in records"
        if input(f"Reset {what}? A backup copy is kept. Type yes to go on: ").strip().lower() != "yes":
            raise SystemExit("Nothing changed.")
        n, backup = reset(methods)
        print(f"Removed {n} sign-in(s)." + (f" Backup: {backup}" if backup else " There was nothing to reset."))
    s = stats()
    print(f"{s['total']} sign-ins by {s['people']} people (today {s['today']}, last 7 days {s['week']}).")
    print(f"Guests: {s['guests']} Guest Only visits from {s['guest_people']} different browsers "
          f"(today {s['guest_today']}, last 7 days {s['guest_week']}, {s['guest_share']}% of all sign-ins).")
    for m, n in s["by_method"]:
        print(f"  {m}: {n}")
    print(f"File: {PATH}")
