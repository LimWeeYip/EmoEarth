"""Put the latest EmoEarth on Azure in one step (README section 9b, "One-command update").

    python deploy_azure.py            # package, upload, wait until the new version is live, check it
    python deploy_azure.py --check    # only show what changed since the last upload (uploads nothing)
    python deploy_azure.py --force    # upload even if nothing changed

What it does:
  1. Checks the Azure CLI is installed and signed in (runs "az login" for you if needed).
  2. Compares every file that goes online with the last upload and lists what changed
     (new, changed, removed); stops if nothing changed.
  3. Checks the Python files compile, so a typo never goes online.
  4. Makes azure_deploy.zip (make_azure_package.py: no secrets inside).
  5. Uploads it with "az webapp deploy" and waits until the site answers with the new build number
     (the Free plan can need several minutes to start).
  6. Remembers what was uploaded (.deploy_state.json, not in git) and writes a line to the app log.

Settings (optional) in .env:  AZURE_RESOURCE_GROUP=emoearth-rg   AZURE_WEBAPP=emoearth
"""
import os
import sys
import json
import time
import shutil
import hashlib
import py_compile
import subprocess
import urllib.request

import make_azure_package as pkg

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, ".deploy_state.json")
WAIT_MINUTES = 15


def setting(name, default):
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(os.path.join(BASE, ".env")) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.strip() == name and v.strip():
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


GROUP = setting("AZURE_RESOURCE_GROUP", "emoearth-rg")
APP = setting("AZURE_WEBAPP", "emoearth")


def say(msg):
    print(msg, flush=True)


def note(msg):
    try:
        import applog
        applog.log.info("Deploy: %s", msg)
    except Exception:
        pass


def az(*args, check=True, capture=True):
    exe = shutil.which("az") or shutil.which("az.cmd")
    if not exe:
        raise SystemExit("The Azure CLI is not installed. Mac: brew install azure-cli   "
                         "Windows: winget install -e --id Microsoft.AzureCLI   (then open a new terminal)")
    r = subprocess.run([exe, *args], capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip()[-1500:])
    return r


def fingerprint():
    """sha256 of every file that goes online."""
    out = {}
    for full, arc in pkg.files_to_ship():
        h = hashlib.sha256()
        with open(full, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        out[arc] = h.hexdigest()
    out["requirements.txt"] = hashlib.sha256(pkg.SERVER_REQUIREMENTS.encode()).hexdigest()
    return out


def changes(old, new):
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    return added, changed, removed


def show(label, items, limit=12):
    if not items:
        return
    say(f"  {label} ({len(items)}):")
    for x in items[:limit]:
        say(f"    {x}")
    if len(items) > limit:
        groups = {}
        for x in items[limit:]:
            groups[x.rsplit("/", 1)[0]] = groups.get(x.rsplit("/", 1)[0], 0) + 1
        for g, n in sorted(groups.items()):
            say(f"    ... and {n} more in {g}/")


def site_about(host):
    try:
        with urllib.request.urlopen(f"https://{host}/api/about?{time.time():.0f}", timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def main():
    check_only = "--check" in sys.argv
    force = "--force" in sys.argv

    # 1. what changed since the last upload
    try:
        with open(STATE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    say("Looking for changes ...")
    new = fingerprint()
    added, changed, removed = changes(state.get("files", {}), new)
    if state:
        say(f"Since the last upload ({state.get('build', '?')}, {state.get('deployed_at', '?')}):")
        show("new", added)
        show("changed", changed)
        show("removed", removed)
    else:
        say(f"No record of an earlier upload from this computer: everything ({len(new)} files) will be uploaded.")
    nothing = state and not (added or changed or removed)
    if nothing:
        say("  nothing changed.")
    if check_only:
        return
    if nothing and not force:
        say("Nothing to upload. (Use --force to upload anyway.)")
        return

    # 2. no typos go online
    for full, arc in pkg.files_to_ship():
        if arc.endswith(".py"):
            try:
                py_compile.compile(full, doraise=True)
            except py_compile.PyCompileError as e:
                raise SystemExit(f"Stopped: {arc} has an error, nothing was uploaded.\n{e.msg}")

    # 3. Azure CLI signed in, app found
    say("Checking the Azure sign-in ...")
    if az("account", "show", check=False).returncode != 0:
        say("Not signed in to Azure: a browser window opens for you to sign in.")
        az("login", capture=False)
    try:
        host = az("webapp", "show", "-g", GROUP, "-n", APP, "--query", "defaultHostName", "-o", "tsv").stdout.strip()
    except RuntimeError as e:
        raise SystemExit(f"Could not find the Web App '{APP}' in resource group '{GROUP}'. "
                         f"Set AZURE_WEBAPP / AZURE_RESOURCE_GROUP in .env.\n{e}")
    say(f"Web App: {APP} ({host})")

    # 4. package
    info = pkg.main(quiet=True)

    # 5. upload and wait until the new build answers
    say(f"Uploading ({os.path.getsize(pkg.OUT) / 1e6:.0f} MB). This takes a few minutes ...")
    note(f"upload of build {info['build']} to {APP} started")
    t0 = time.time()
    r = az("webapp", "deploy", "-g", GROUP, "-n", APP, "--src-path", pkg.OUT, "--type", "zip", check=False)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        say("Azure reported a problem (often only the slow first start on the Free plan):")
        say("  " + "\n  ".join(out.splitlines()[-6:]))
    say(f"Waiting for https://{host} to answer with build {info['build']} ...")
    live = None
    while time.time() - t0 < WAIT_MINUTES * 60:
        a = site_about(host)
        if a and a.get("build") == info["build"]:
            live = a
            break
        time.sleep(15)
    mins = (time.time() - t0) / 60
    if not live:
        note(f"build {info['build']} did not answer within {WAIT_MINUTES} min")
        raise SystemExit(f"The site did not answer with the new build within {WAIT_MINUTES} minutes.\n"
                         f"Look at: az webapp log tail -n {APP} -g {GROUP}   (or Azure > Monitoring > Log stream)\n"
                         f"Then run python deploy_azure.py again.")

    # 6. remember
    state = {"build": info["build"], "version": info["version"], "git": info["git"],
             "deployed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "host": host, "files": new}
    with open(STATE, "w") as f:
        json.dump(state, f)
    note(f"build {info['build']} ({info['version']}) live on {host} after {mins:.1f} min")
    say(f"\nDone in {mins:.1f} minutes. EmoEarth {info['version']} (build {info['build']}) is live:")
    say(f"  https://{host}")
    say("People with the page open will see \"EmoEarth has been updated - click to reload\" within 5 minutes.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        raise SystemExit(f"Azure CLI error:\n{e}")
    except KeyboardInterrupt:
        raise SystemExit("\nStopped.")
