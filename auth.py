"""EmoEarth sign-in accounts.

  python auth.py add NAME       create an account, or change its password (asks for the password twice)
  python auth.py remove NAME    delete an account
  python auth.py list           show the account names

Accounts live in users.json next to this file: only password hashes are stored, never the passwords.
users.json and .flask_secret are in .gitignore, so accounts stay on this computer.

Firebase mode: when firebase_web_config.json and the service account key (firebase-service-account.json, or the
path in FIREBASE_SERVICE_ACCOUNT) are both in this folder, sign-in uses Firebase Authentication instead
(email + password, "Forgot password?", optional Google). See README section 5a.
"""
import os
import sys
import json
import time
import getpass
import secrets

from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_PATH = os.path.join(BASE_DIR, "users.json")
SECRET_PATH = os.path.join(BASE_DIR, ".flask_secret")
FIREBASE_WEB_CONFIG = os.path.join(BASE_DIR, "firebase_web_config.json")
FIREBASE_KEY_DEFAULT = os.path.join(BASE_DIR, "firebase-service-account.json")
FIREBASE_RECHECK_SECONDS = 10 * 60      # how often a signed-in Firebase user is re-checked (disabled or deleted)
FIREBASE_MAX_TOKEN_AGE = 10 * 60        # a sign-in token must come from a sign-in in the last 10 minutes

MAX_FAILURES = 5               # wrong passwords allowed from one address ...
LOCK_SECONDS = 10 * 60         # ... within this time, before that address must wait
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def load_users():
    try:
        with open(USERS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_users(users):
    tmp = USERS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(users, f, indent=1)
    os.replace(tmp, USERS_PATH)
    try:
        os.chmod(USERS_PATH, 0o600)
    except OSError:
        pass


def verify(username, password):
    """True if the name and password match. Takes the same time whether or not the name exists."""
    h = load_users().get((username or "").strip())
    if not h:
        check_password_hash(_DUMMY_HASH, password or "")
        return False
    return check_password_hash(h, password or "")


def setting(name):
    """A setting from the environment, or from the .env file in this folder."""
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


# ---------------------------------------------------------------- Firebase mode
def firebase_settings():
    """Firebase settings if both Firebase files are present, else None (local accounts are used)."""
    raw = setting("FIREBASE_SERVICE_ACCOUNT_JSON")    # the key's contents, for hosts like Azure (app setting)
    if raw:
        key = json.loads(raw)
    else:
        key = setting("FIREBASE_SERVICE_ACCOUNT") or FIREBASE_KEY_DEFAULT
        if not os.path.isabs(key):
            key = os.path.join(BASE_DIR, key)
        if not os.path.exists(key):
            return None
    if not os.path.exists(FIREBASE_WEB_CONFIG):
        return None
    with open(FIREBASE_WEB_CONFIG) as f:
        web = json.load(f)
    google = bool(web.pop("googleSignIn", False)) or (setting("FIREBASE_GOOGLE_SIGNIN") or "").lower() in ("1", "true", "yes")
    split = lambda v: {x.strip().lower() for x in (v or "").split(",") if x.strip()}
    return {"web": web, "key": key, "google": google,
            "allowed_emails": split(setting("FIREBASE_ALLOWED_EMAILS")),
            "allowed_domains": split(setting("FIREBASE_ALLOWED_DOMAINS"))}


def firebase_init(settings):
    """Start the Firebase Admin SDK with the service account key."""
    import firebase_admin
    from firebase_admin import credentials
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(settings["key"]))


def firebase_allowed(email, settings):
    """True if this email may use EmoEarth. With no allow-list set, every account in the Firebase project may."""
    email = (email or "").lower()
    if not settings["allowed_emails"] and not settings["allowed_domains"]:
        return True
    return email in settings["allowed_emails"] or email.rpartition("@")[2] in settings["allowed_domains"]


def firebase_verify(id_token):
    """Check a Firebase sign-in token. Returns its claims, or raises ValueError with a message for the person."""
    from firebase_admin import auth as fb
    try:
        claims = fb.verify_id_token(id_token, check_revoked=True)
    except fb.RevokedIdTokenError:
        raise ValueError("This sign-in was cancelled. Sign in again.")
    except fb.UserDisabledError:
        raise ValueError("This account is turned off. Ask the EmoEarth team.")
    except Exception:
        raise ValueError("Couldn't check this sign-in with Firebase. Try again.")
    if time.time() - claims.get("auth_time", 0) > FIREBASE_MAX_TOKEN_AGE:
        raise ValueError("This sign-in is too old. Sign in again.")
    return claims


def firebase_user_ok(uid):
    """False if the Firebase account was deleted or turned off since the person signed in."""
    from firebase_admin import auth as fb
    try:
        return not fb.get_user(uid).disabled
    except fb.UserNotFoundError:
        return False
    except Exception:
        return True                          # Firebase unreachable for a moment: don't sign everyone out


def secret_key():
    """Key that signs the sign-in cookie: FLASK_SECRET_KEY from the environment or .env, else a random key
    kept in .flask_secret (so people stay signed in when the server restarts)."""
    if setting("FLASK_SECRET_KEY"):
        return setting("FLASK_SECRET_KEY")
    try:
        with open(SECRET_PATH) as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    with open(SECRET_PATH, "w") as f:
        f.write(key)
    try:
        os.chmod(SECRET_PATH, 0o600)
    except OSError:
        pass
    return key


class Throttle:
    """Slows down password guessing: after MAX_FAILURES wrong tries, an address waits LOCK_SECONDS."""

    def __init__(self):
        self.failures = {}

    def _recent(self, addr):
        now = time.time()
        self.failures[addr] = [t for t in self.failures.get(addr, []) if now - t < LOCK_SECONDS]
        return self.failures[addr]

    def wait_seconds(self, addr):
        recent = self._recent(addr)
        if len(recent) < MAX_FAILURES:
            return 0
        return int(LOCK_SECONDS - (time.time() - recent[0])) + 1

    def fail(self, addr):
        self._recent(addr).append(time.time())

    def ok(self, addr):
        self.failures.pop(addr, None)


def _cli():
    if len(sys.argv) < 2 or sys.argv[1] not in ("add", "remove", "list"):
        print(__doc__)
        return 1
    users = load_users()
    cmd = sys.argv[1]
    if cmd == "list":
        print("\n".join(sorted(users)) if users else "No accounts yet. Create one with: python auth.py add NAME")
        return 0
    if len(sys.argv) < 3 or not sys.argv[2].strip():
        print(f"Give a name: python auth.py {cmd} NAME")
        return 1
    name = sys.argv[2].strip()
    if cmd == "remove":
        if users.pop(name, None) is None:
            print(f"No account called {name}.")
            return 1
        save_users(users)
        print(f"Removed {name}.")
        return 0
    pw = getpass.getpass(f"New password for {name}: ")
    if len(pw) < 8:
        print("Use at least 8 characters.")
        return 1
    if getpass.getpass("Type it again: ") != pw:
        print("The two passwords are different. Nothing was changed.")
        return 1
    existed = name in users
    users[name] = generate_password_hash(pw)
    save_users(users)
    print(("Changed the password for " if existed else "Created the account ") + name + ".")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
