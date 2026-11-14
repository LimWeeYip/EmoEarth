"""Make azure_deploy.zip: only the files the hosted web app needs (see README section 9b).

    python make_azure_package.py

Leaves out secrets (.env, Firebase key, .flask_secret, users.json), the venv, raw NASA images
and music.wav (the page plays music.mp3). Build the data first (python app.py --rebuild, narrate.py).
"""
import os
import json
import zipfile
import subprocess
import datetime as dt

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "azure_deploy.zip")
CODE = ["app.py", "applog.py", "auth.py", "signins.py", "build_assets.py", "update_data.py", "orchestra.py", "firebase_web_config.json"]
SKIP_STATIC = {os.path.join("static", "data", "music.wav"), os.path.join("static", "data", "ocean", "music.wav"),
               os.path.join("static", "data", "co2", "music.wav")}

# Packages the web server needs (the full requirements.txt has desktop-only tools as well)
SERVER_REQUIREMENTS = """flask>=3.0
gunicorn>=22.0
firebase-admin>=6.5
requests>=2.31
pillow>=10.1
numpy>=1.26
lameenc>=1.7
"""


def build_info():
    """Version, when this package was made, and the git commit: shown on the page as "updated ..."."""
    try:
        with open(os.path.join(BASE, "static", "version.txt")) as f:
            version = f.read().strip()
    except OSError:
        version = ""
    git = ""
    try:
        git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BASE, capture_output=True, text=True,
                             timeout=10).stdout.strip()
        if git and subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=BASE,
                                  capture_output=True, text=True, timeout=20).stdout.strip():
            git += " + local changes"
    except Exception:
        pass
    now = dt.datetime.now().astimezone()
    return {"version": version, "packaged_at": now.isoformat(timespec="seconds"), "git": git,
            "build": now.strftime("%Y%m%d%H%M%S")}


def files_to_ship():
    """(path on disk, path in the zip) for every file the hosted app needs, in a fixed order."""
    out = [(os.path.join(BASE, f), f) for f in CODE if os.path.exists(os.path.join(BASE, f))]
    for root, dirs, files in os.walk(os.path.join(BASE, "static")):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith("."))
        for f in sorted(files):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, BASE)
            if (rel in SKIP_STATIC or f.startswith(".") or f.endswith(".tmp")
                    or f.endswith(".png") and os.sep + "frames" + os.sep in full):
                continue                          # music.wav, .DS_Store, half-written files, old PNG frames
            out.append((full, rel.replace(os.sep, "/")))
    return out


def main(quiet=False):
    """Make azure_deploy.zip; returns its build_info."""
    need = [os.path.join("static", "data", "timeline.json"), os.path.join("static", "data", "music.mp3")]
    missing = [p for p in need if not os.path.exists(os.path.join(BASE, p))]
    if missing:
        raise SystemExit("Build the data first (python app.py --rebuild). Missing: " + ", ".join(missing))
    files = files_to_ship()
    info = build_info()
    with zipfile.ZipFile(OUT + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("requirements.txt", SERVER_REQUIREMENTS)
        z.writestr("build_info.json", json.dumps(info, indent=1))
        for full, arc in files:
            z.write(full, arc)
    os.replace(OUT + ".tmp", OUT)
    mb = os.path.getsize(OUT) / 1e6
    print(f"Made {os.path.basename(OUT)}: {len(files) + 2} files, {mb:.0f} MB. No secrets inside.")
    print(f"Build {info['build']} ({info['version']}, made {info['packaged_at']}{', git ' + info['git'] if info['git'] else ''}).")
    if not quiet:
        print("Upload it with: python deploy_azure.py   (or az webapp deploy ..., README section 9b)")
    return info


if __name__ == "__main__":
    main()
