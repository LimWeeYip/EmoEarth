import os
import sys
import json
import re
import time
import threading
from datetime import timedelta

from flask import Flask, send_from_directory, jsonify, request, session, redirect, g, Response
from werkzeug.exceptions import HTTPException

import applog
import auth
import signins
import build_assets
import update_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TIMELINE = os.path.join(STATIC_DIR, "data", "timeline.json")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0       # by default the browser re-checks every file (page, json, version)

log = applog.log                                 # logs/emoearth.log + terminal (README "Logs")

# ---------- sign-in ----------
app.secret_key = auth.secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                  SESSION_COOKIE_SECURE=bool(os.environ.get("WEBSITE_HOSTNAME")))   # HTTPS-only cookie on Azure
throttle = auth.Throttle()
PUBLIC = ("/login", "/auth/config", "/static/login.html", "/static/logo/", "/static/version.txt", "/favicon.ico",
          "/api/clientlog", "/api/about")

# Firebase mode when both Firebase files are present (README 5a); otherwise local accounts from auth.py
try:
    FIREBASE = auth.firebase_settings()
except Exception as e:                           # e.g. FIREBASE_SERVICE_ACCOUNT_JSON pasted incompletely
    log.error("Firebase settings could not be read (%s). Using local accounts instead.", e)
    FIREBASE = None
if FIREBASE:
    try:
        auth.firebase_init(FIREBASE)
    except Exception as e:
        log.error("Firebase could not start (%s). Using local accounts (python auth.py add NAME) instead.", e)
        FIREBASE = None


def _about():
    """What is running here: version, when the package was made (build_info.json, from make_azure_package.py)
    and when this server started. On your own computer there is no build_info.json: it shows the start time."""
    info = {}
    try:
        with open(os.path.join(BASE_DIR, "build_info.json")) as f:
            info = json.load(f)
    except (OSError, ValueError):
        pass
    if not info.get("version"):
        try:
            with open(os.path.join(STATIC_DIR, "version.txt")) as f:
                info["version"] = f.read().strip()
        except OSError:
            pass
    from datetime import datetime
    info["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    info["host"] = "Azure" if os.environ.get("WEBSITE_HOSTNAME") else "this computer"
    info.setdefault("build", "local-" + info["started_at"])
    return info


ABOUT = _about()
log.info("EmoEarth app loaded: %s, build %s (packaged %s), sign-in %s, log file %s", ABOUT.get("version", "?"),
         ABOUT["build"], ABOUT.get("packaged_at", "-"),
         "Firebase (" + FIREBASE["web"].get("projectId", "?") + ")" if FIREBASE else "local accounts", applog.LOG_PATH)


def who():
    return session.get("user") or "-"


def client_addr():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()


@app.before_request
def start_timer():
    g.t0 = time.time()


@app.before_request
def require_sign_in():
    """Everything except the sign-in page and its few files needs a signed-in user."""
    if session.get("user"):
        if FIREBASE and session.get("uid"):
            import time as _t
            if _t.time() - session.get("checked", 0) > auth.FIREBASE_RECHECK_SECONDS:
                if not auth.firebase_user_ok(session["uid"]):
                    log.warning("Signed out %s: the Firebase account was deleted or turned off", who())
                    session.clear()              # the Firebase account was deleted or turned off
                else:
                    session["checked"] = _t.time()
        elif not FIREBASE and session.get("method") not in ("email only", "guest") and session["user"] not in auth.load_users():
            log.warning("Signed out %s: the account was removed", who())
            session.clear()                      # the account was removed: sign this browser out too
    if session.get("user") or request.path.startswith(PUBLIC):
        return None
    if request.path.startswith(("/api/", "/static/")):
        return jsonify({"error": "Sign in first."}), 401
    return redirect("/login?next=" + request.full_path.rstrip("?"))


def _safe_next(target):
    """Only send people back to a page on this site after signing in."""
    return target if target and target.startswith("/") and not target.startswith("//") else "/"


@app.route("/login", methods=["GET"])
def login_page():
    if session.get("user"):
        return redirect(_safe_next(request.args.get("next")))
    return send_from_directory(STATIC_DIR, "login.html")


@app.route("/auth/config")
def auth_config():
    """Tells the sign-in page which kind of sign-in to show."""
    if FIREBASE:
        return jsonify({"mode": "firebase", "config": FIREBASE["web"], "google": FIREBASE["google"]})
    return jsonify({"mode": "local", "has_accounts": bool(auth.load_users())})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    addr = request.remote_addr or "?"
    wait = throttle.wait_seconds(addr)
    if wait:
        log.warning("Sign-in blocked for %s: too many wrong passwords", client_addr())
        return jsonify({"error": f"Too many wrong passwords. Try again in {max(1, wait // 60)} minute(s)."}), 429
    if FIREBASE:
        if not data.get("idToken"):
            return jsonify({"error": "Sign in with your email and password."}), 400
        try:
            claims = auth.firebase_verify(data["idToken"])
        except ValueError as e:
            throttle.fail(addr)
            log.warning("Sign-in failed from %s: %s", client_addr(), e)
            return jsonify({"error": str(e)}), 401
        email = claims.get("email", "")
        if not auth.firebase_allowed(email, FIREBASE):
            throttle.fail(addr)
            log.warning("Sign-in refused: %s is not on the allow-list (from %s)", email or "?", client_addr())
            return jsonify({"error": f"{email or 'This account'} isn't on the EmoEarth list. Ask the team to add it."}), 403
        throttle.ok(addr)
        import time as _t
        session.clear()
        session.update(user=claims.get("name") or email or claims["uid"], uid=claims["uid"], email=email, checked=_t.time())
        session.permanent = bool(data.get("remember"))
        provider = claims.get("firebase", {}).get("sign_in_provider", "?")
        session["method"] = provider
        log.info("Signed in: %s (Firebase, %s) from %s", email or claims["uid"], provider, client_addr())
        signins.record(email or claims["uid"], provider, client_addr(), request.headers.get("User-Agent", ""))
        return jsonify({"ok": True, "next": _safe_next(data.get("next"))})
    if not auth.load_users():
        return jsonify({"error": "No accounts yet. On the computer running EmoEarth, run: python auth.py add NAME"}), 403
    name = (data.get("username") or "").strip()
    if not auth.verify(name, data.get("password") or ""):
        throttle.fail(addr)
        log.warning("Sign-in failed for name %r from %s: wrong name or password", name[:60], client_addr())
        return jsonify({"error": "That name and password don't match. Check them and try again."}), 401
    throttle.ok(addr)
    session.clear()
    session["user"] = name
    session.permanent = bool(data.get("remember"))
    session["method"] = "local account"
    log.info("Signed in: %s (local account) from %s", name, client_addr())
    signins.record(name, "local account", client_addr(), request.headers.get("User-Agent", ""))
    return jsonify({"ok": True, "next": _safe_next(data.get("next"))})


# ---------- email-only access (a second sign-in page; README "Email-only sign-in page") ----------
EMAIL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
                      r"@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$")
_email_hits = {}


def email_problem(email):
    """None if this looks like a real email address, else what is wrong (same rules as the page)."""
    if not email:
        return "Enter your email address."
    if len(email) > 254 or " " in email:
        return "That email address has spaces or is too long."
    if email.count("@") != 1:
        return "An email address needs exactly one @, like name@example.com."
    local, at, domain = email.rpartition("@")
    if not local:
        return "Add the part before the @."
    if not domain:
        return "Add the part after the @, like example.com."
    if len(local) > 64:
        return "The part before the @ is too long."
    if not EMAIL_RE.match(email):
        return "That doesn't look like a valid email address. Check it, for example name@example.com."
    return None


def email_access_allowed(email):
    """EMAIL_ACCESS=off turns the page off; EMAIL_ACCESS_DOMAINS (comma-separated) limits it to those domains."""
    if (auth.setting("EMAIL_ACCESS") or "on").lower() in ("off", "0", "no", "false"):
        return False
    domains = {d.strip().lower().lstrip("@") for d in (auth.setting("EMAIL_ACCESS_DOMAINS") or "").split(",") if d.strip()}
    return not domains or email.rpartition("@")[2].lower() in domains


@app.route("/login/email", methods=["GET"])
def email_page():
    # always shown, even when signed in: the page then offers "go to the globe" or "sign out and use another email"
    return send_from_directory(STATIC_DIR, "login_email.html")


@app.route("/login/email", methods=["POST"])
def email_login():
    data = request.get_json(silent=True) or request.form
    addr = client_addr()
    now = time.time()
    hits = [t for t in _email_hits.get(addr, []) if now - t < 600]
    if len(hits) >= 15:                                  # at most 15 tries per address every 10 minutes
        log.warning("Email-only sign-in: too many tries from %s", addr)
        return jsonify({"error": "Too many tries. Wait a few minutes and try again."}), 429
    _email_hits[addr] = hits + [now]
    email = (data.get("email") or "").strip()
    problem = email_problem(email)
    if problem:
        return jsonify({"error": problem, "field": "email"}), 400
    local, _, domain = email.rpartition("@")
    email = local + "@" + domain.lower()
    if not email_access_allowed(email):
        log.warning("Email-only sign-in refused: %s (from %s)", email, addr)
        return jsonify({"error": "Email-only access isn't open for this address. Use the main sign-in page."}), 403
    session.clear()
    session.update(user=email, email=email, method="email only")
    session.permanent = bool(data.get("remember"))
    log.info("Signed in: %s (email only) from %s", email, addr)
    signins.record(email, "email only", addr, request.headers.get("User-Agent", ""))
    return jsonify({"ok": True, "next": _safe_next(data.get("next"))})


# ---------- Guest Only: straight to the globe, no email or password (README "Guest Only") ----------
@app.route("/login/guest", methods=["POST"])
def guest_login():
    if (auth.setting("GUEST_ACCESS") or "on").lower() in ("off", "0", "no", "false"):
        return jsonify({"error": "Guest access is turned off. Sign in with your account."}), 403
    addr = client_addr()
    now = time.time()
    hits = [t for t in _email_hits.get("g:" + addr, []) if now - t < 600]
    if len(hits) >= 30:                                  # at most 30 guest visits per address every 10 minutes
        return jsonify({"error": "Too many tries. Wait a few minutes and try again."}), 429
    _email_hits["g:" + addr] = hits + [now]
    data = request.get_json(silent=True) or {}
    # one id per browser (kept in a cookie for a year), so /stats can count different guests
    gid = request.cookies.get("emo_guest", "")
    if not re.fullmatch(r"[a-f0-9]{8}", gid):
        gid = os.urandom(4).hex()
    session.clear()
    session.update(user="Guest", method="guest", guest=gid)
    log.info("Signed in: guest %s from %s", gid, addr)
    signins.record("guest " + gid, "guest", addr, request.headers.get("User-Agent", ""))
    resp = jsonify({"ok": True, "next": _safe_next(data.get("next"))})
    resp.set_cookie("emo_guest", gid, max_age=365 * 24 * 3600, httponly=True, samesite="Lax",
                    secure=bool(os.environ.get("WEBSITE_HOSTNAME")))
    return resp


@app.route("/logout")
def logout():
    if session.get("user"):
        log.info("Signed out: %s", who())
    session.clear()
    return redirect("/login/email" if request.args.get("to") == "email" else "/login")


@app.route("/api/me")
def me():
    return jsonify({"user": session.get("user"), "method": session.get("method")})


@app.after_request
def cache_versioned_files(resp):
    """Frames and music are requested with ?v=<version>; a new build uses a new version number,
    so the browser can safely keep these files instead of downloading them again on every visit.
    (Every layer: static/data/frames/, static/data/ocean/frames/, static/data/co2/frames/ and their music.)"""
    p = request.path
    if (resp.status_code == 200 and request.args.get("v") and p.startswith("/static/data/")
            and ("/frames/" in p or "/music." in p)):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.after_request
def log_problems(resp):
    """Server errors, missing data files and slow answers go into the log."""
    took = time.time() - g.get("t0", time.time())
    if resp.status_code >= 500:
        log.error("%s %s -> %s (%s, %.1fs)", request.method, request.path, resp.status_code, who(), took)
    elif resp.status_code == 404 and request.path.startswith("/static/data/"):
        log.warning("Missing file: %s (%s)", request.path, who())
    elif took > 5 and not request.path.startswith("/static/"):
        log.warning("Slow: %s %s took %.1fs", request.method, request.path, took)
    return resp


@app.errorhandler(Exception)
def crash(e):
    """Any unexpected error (a crash inside a request): full traceback into the log, a short message to the browser."""
    if isinstance(e, HTTPException):
        return e
    log.exception("Server error on %s %s (user %s, from %s)", request.method, request.path, who(), client_addr())
    if request.path.startswith("/api/"):
        return jsonify({"error": "Something went wrong on the server. It has been written to the log."}), 500
    return "Something went wrong on the server. It has been written to the log.", 500


_client_counts = {}


@app.route("/api/clientlog", methods=["POST"])
def client_log():
    """Problems seen in people's browsers (script errors, frames or music that fail to load)."""
    addr = client_addr()
    now = time.time()
    hits = [t for t in _client_counts.get(addr, []) if now - t < 600]
    if len(hits) >= 60:                                  # at most 60 reports per address per 10 minutes
        return "", 204
    _client_counts[addr] = hits + [now]
    if len(_client_counts) > 5000:
        _client_counts.clear()
    raw = request.get_data(cache=False, as_text=True)[:4000]
    try:
        d = json.loads(raw)
    except ValueError:
        return "", 204
    clean = lambda k, n=300: " ".join(str(d.get(k, "")).split())[:n]
    parts = [f"[{clean('kind', 20)}] {clean('msg')}"]
    for k in ("src", "layer"):
        if d.get(k):
            parts.append(f"{k}={clean(k, 200)}")
    if d.get("line"):
        parts.append(f"line={clean('line', 10)}:{clean('col', 10)}")
    parts.append(f"page={clean('page', 120)}")
    parts.append(f"user={who()}")
    parts.append("browser=" + " ".join(request.headers.get("User-Agent", "?").split())[:120])
    log.warning("Browser: %s", "  ".join(parts))
    if d.get("stack"):
        log.warning("Browser stack: %s", " | ".join(str(d["stack"]).splitlines())[:1500])
    return "", 204


def can_read_logs():
    """LOG_VIEWERS (emails or names, comma-separated) may read the log in the browser.
    Without it, any signed-in user may on your own computer, and nobody may on Azure."""
    if not session.get("user") or session.get("method") in ("email only", "guest"):
        return False                                     # email-only visitors typed an email; it isn't proven
    allowed = {x.strip().lower() for x in (auth.setting("LOG_VIEWERS") or "").split(",") if x.strip()}
    if allowed:
        return session["user"].lower() in allowed or (session.get("email") or "").lower() in allowed
    return not os.environ.get("WEBSITE_HOSTNAME")


@app.route("/logs")
@app.route("/api/logs")
def show_logs():
    """The last lines of the log as plain text: /logs?n=300  or  /logs?errors=1 for warnings and errors only."""
    if not can_read_logs():
        return Response("You can't read the log. Ask the team to add your email to LOG_VIEWERS.\n", 403,
                        mimetype="text/plain")
    n = max(10, min(int(request.args.get("n", 300) or 300), 5000))
    lines = applog.tail(n, "WARNING" if request.args.get("errors") else None)
    head = f"EmoEarth log ({applog.LOG_PATH}), newest at the bottom. /logs?errors=1 = problems only, /logs?n=1000 = more.\n\n"
    return Response(head + ("\n".join(lines) or "(empty)") + "\n", mimetype="text/plain")


@app.route("/stats")
def show_stats():
    """How many people signed in, and how (same viewers as /logs). /stats.csv downloads every sign-in."""
    if not can_read_logs():
        return Response("You can't see the sign-in numbers. Ask the team to add your email to LOG_VIEWERS.\n", 403,
                        mimetype="text/plain")
    from html import escape
    st = signins.stats()
    peak = max([n for _, n in st["per_day"]] + [1])
    gp = st["guest_per_day"]
    bars = "".join(f'<tr><td>{d}</td><td class="n">{n}</td><td class="n g">{gp.get(d, 0)}</td>'
                   f'<td><i style="width:{n / peak * 100:.0f}%"><b style="width:{(gp.get(d, 0) / n * 100) if n else 0:.0f}%"></b></i></td></tr>'
                   for d, n in st["per_day"])
    methods = "".join(f"<tr><td>{escape(m)}</td><td class='n'>{n}</td></tr>" for m, n in st["by_method"]) or "<tr><td>none yet</td><td></td></tr>"
    top = "".join(f"<tr><td>{escape(u)}</td><td class='n'>{n}</td></tr>" for u, n in st["top"]) or "<tr><td>none yet</td><td></td></tr>"
    latest = "".join(f"<tr><td>{escape(r['time'][:16].replace('T', ' '))}</td><td>{escape(r['user'])}</td>"
                     f"<td>{escape(r['method'])}</td><td>{escape(r['address'])}</td></tr>" for r in st["latest"])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign-ins · EmoEarth</title><style>
body {{ margin: 0; background: #070b1a; color: #e8f1ff; font: 15px/1.5 system-ui, sans-serif; }}
main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 60px; }}
h1 {{ font-size: 26px; font-weight: 600; margin: 0 0 4px; }} h2 {{ font-size: 17px; font-weight: 600; margin: 32px 0 10px; }}
.sub {{ color: #9aa6c3; margin: 0 0 24px; }} a {{ color: #e9b949; }}
.big {{ display: flex; gap: 14px; flex-wrap: wrap; }}
.big div {{ flex: 1 1 150px; border: 1px solid rgba(232,241,255,.14); border-radius: 12px; padding: 14px 16px; }}
.big b {{ display: block; font-size: 30px; font-weight: 600; font-variant-numeric: tabular-nums; }}
.big span {{ color: #9aa6c3; font-size: 13px; }}
.cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
td, th {{ padding: 5px 8px; border-bottom: 1px solid rgba(232,241,255,.08); text-align: left; }}
th {{ color: #9aa6c3; font-weight: 500; }} td.n {{ text-align: right; font-variant-numeric: tabular-nums; width: 3em; }}
td i {{ display: block; height: 8px; border-radius: 4px; background: #e9b949; min-width: 1px; overflow: hidden; }}
td i b {{ display: block; height: 100%; background: #5dcaa5; }}
td.g {{ color: #9fe1cb; }} .gc {{ border-color: rgba(93,202,165,.35) !important; }}
.key {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: #e9b949; vertical-align: -1px; }} .key.g {{ background: #5dcaa5; }}
</style></head><body><main>
<h1>EmoEarth sign-ins</h1>
<p class="sub">Every sign-in since {escape((st['first'] or 'the first one')[:10])}. <a href="/stats.csv">Download all as CSV</a> · <a href="/">Back to the globe</a></p>
<div class="big"><div><b>{st['total']}</b><span>sign-ins in total</span></div><div><b>{st['people']}</b><span>different people</span></div>
<div><b>{st['today']}</b><span>today</span></div><div><b>{st['week']}</b><span>last 7 days ({st['people_week']} people)</span></div></div>
<h2>Guest Only</h2>
<div class="big"><div class="gc"><b>{st['guests']}</b><span>guest visits ({st['guest_share']}% of all sign-ins)</span></div>
<div class="gc"><b>{st['guest_people']}</b><span>different guest browsers</span></div>
<div class="gc"><b>{st['guest_today']}</b><span>guests today</span></div><div class="gc"><b>{st['guest_week']}</b><span>guests in the last 7 days</span></div></div>
<div class="cols"><section><h2>How people signed in</h2><table>{methods}</table></section>
<section><h2>Most sign-ins</h2><table>{top}</table></section></div>
<h2>Last 30 days</h2><table><tr><th>Day</th><th class="n">All</th><th class="n">Guests</th><th><span class="key"></span> all &nbsp;<span class="key g"></span> guests</th></tr>{bars}</table>
<h2>Latest sign-ins</h2><table><tr><th>Time</th><th>Who</th><th>How</th><th>From</th></tr>{latest or '<tr><td colspan=4>none yet</td></tr>'}</table>
</main></body></html>"""
    return Response(page, mimetype="text/html")


@app.route("/stats.csv")
def stats_csv():
    if not can_read_logs():
        return Response("Not allowed.\n", 403, mimetype="text/plain")
    try:
        with open(signins.PATH, encoding="utf-8") as f:
            data = f.read()
    except OSError:
        data = ",".join(signins.FIELDS) + "\n"
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=emoearth_signins.csv"})


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/about")
def about():
    """When this EmoEarth was set up: version, package time, start time, where it runs."""
    return jsonify(ABOUT)


@app.route("/api/status")
def status():
    info = {}
    try:
        with open(TIMELINE) as f:
            tl = json.load(f)
        info = {"version": tl.get("version"), "latest_date": tl.get("latest_date"), "built_at": tl.get("built_at")}
    except Exception:
        pass
    info.update(updating=update_data.STATE["updating"], message=update_data.STATE["message"],
                last_check=update_data.STATE["last_check"])
    return jsonify(info)


@app.route("/api/update", methods=["POST"])
def api_update():
    return jsonify({"started": update_data.run_update_async()})


def timeline_ok():
    try:
        with open(TIMELINE) as f:
            return "frames" in json.load(f)      # older builds used numbered frames and need one full rebuild
    except Exception:
        return False


if __name__ == "__main__":
    try:
        if "--rebuild" in sys.argv or "--recalibrate" in sys.argv or not timeline_ok():
            print("Building frames and music (this takes a minute or two) ...")
            build_assets.build(full=True, recalibrate="--recalibrate" in sys.argv)
    except RuntimeError as e:
        raise SystemExit(str(e))
    build_assets.ensure_borders()

    if "--auto-update" in sys.argv:
        hours = float(sys.argv[sys.argv.index("--auto-update") + 1])
        log.info("Auto-update: checking NASA GIBS for new data every %g hour(s).", hours)
        threading.Thread(target=update_data.loop, args=(hours,), daemon=True).start()

    if FIREBASE:
        print("\nSign-in: Firebase (" + FIREBASE["web"].get("projectId", "?") + ")" +
              ("" if FIREBASE["allowed_emails"] or FIREBASE["allowed_domains"] else
               ". No FIREBASE_ALLOWED_EMAILS set: every account in this Firebase project can sign in."))
    elif not auth.load_users():
        print("\nNo sign-in accounts yet. Create one with:  python auth.py add NAME")
    print("Log: " + applog.LOG_PATH + "   (open http://127.0.0.1:5000/logs, or run: python applog.py errors)")
    print("\nOpen http://127.0.0.1:5000 in your browser\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
