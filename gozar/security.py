"""Password hashing, signed tokens, captcha and secret redaction."""

import hashlib
import hmac
import random
import re
import secrets
import time

PBKDF2_ROUNDS = 200_000
SESSION_MAX_AGE = 7 * 24 * 3600
CAPTCHA_MAX_AGE = 300
CAPTCHA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{6,80}$")
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{1,31}$")


# ----------------------------------------------------------------- passwords

def hash_password(password, rounds=PBKDF2_ROUNDS):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds).hex()
    return "pbkdf2${}${}${}".format(rounds, salt, digest)


def verify_password(password, stored):
    if not stored:
        return False
    try:
        if stored.startswith("pbkdf2$"):
            _, rounds, salt, digest = stored.split("$", 3)
            rounds = int(rounds)
        else:  # v1 format: "salt:digest" with 100k rounds
            salt, digest = stored.split(":", 1)
            rounds = 100_000
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds).hex()
    return hmac.compare_digest(digest, test)


def random_password():
    return secrets.token_urlsafe(12)


def new_access_key():
    return "gz_" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")


# ------------------------------------------------------------- signed tokens

def _sign(secret, message):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def make_session(username, secret, generation):
    payload = "{}|{}|{}".format(username, int(time.time()), generation)
    return payload + "|" + _sign(secret, payload)


def verify_session(token, secret, generation, max_age=SESSION_MAX_AGE):
    """Return the username if the token is valid, else None."""
    try:
        username, ts, gen, sig = token.rsplit("|", 3)
        ts = int(ts)
    except (ValueError, AttributeError):
        return None
    if time.time() - ts > max_age or str(gen) != str(generation):
        return None
    if not hmac.compare_digest(sig, _sign(secret, "{}|{}|{}".format(username, ts, gen))):
        return None
    return username


def csrf_token(session_token, secret):
    return _sign(secret, "csrf|" + session_token)[:32]


# ------------------------------------------------------------------- captcha

def new_captcha(secret):
    """Return (token, svg). The answer is bound into the token's signature."""
    code = "".join(random.choice(CAPTCHA_ALPHABET) for _ in range(5))
    ts = int(time.time())
    nonce = secrets.token_hex(6)
    token = "{}.{}.{}".format(ts, nonce, _sign(secret, "cap|{}|{}|{}".format(code, ts, nonce)))
    return token, _captcha_svg(code)


def verify_captcha(answer, token, secret):
    try:
        ts, nonce, sig = token.split(".", 2)
        ts = int(ts)
    except (ValueError, AttributeError):
        return False
    if time.time() - ts > CAPTCHA_MAX_AGE:
        return False
    answer = (answer or "").strip().upper()
    expected = _sign(secret, "cap|{}|{}|{}".format(answer, ts, nonce))
    return hmac.compare_digest(sig, expected)


def _captcha_svg(code):
    w, h = 150, 48
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}">'.format(w, h)]
    for _ in range(5):
        parts.append(
            '<path d="M{} {} Q{} {} {} {}" stroke="#64748b" stroke-opacity=".55" stroke-width="1.4" fill="none"/>'.format(
                random.randint(0, 30), random.randint(5, h - 5), random.randint(40, 110),
                random.randint(0, h), random.randint(120, w), random.randint(5, h - 5)))
    for _ in range(25):
        parts.append('<circle cx="{}" cy="{}" r="1" fill="#94a3b8" fill-opacity=".6"/>'.format(
            random.randint(0, w), random.randint(0, h)))
    palette = ["#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#fbbf24"]
    for i, ch in enumerate(code):
        x = 16 + i * 26 + random.randint(-3, 3)
        y = 33 + random.randint(-4, 4)
        parts.append(
            '<text x="{x}" y="{y}" font-family="Verdana,Arial,sans-serif" font-size="25" font-weight="700" '
            'fill="{c}" transform="rotate({r} {x} {y})">{ch}</text>'.format(
                x=x, y=y, c=random.choice(palette), r=random.randint(-18, 18), ch=ch))
    parts.append("</svg>")
    return "".join(parts)


# ----------------------------------------------------------------- redaction

_TG_TOKEN = re.compile(r"(bot\d+):[A-Za-z0-9_\-]+")
_QUERY_SECRET = re.compile(r"((?:^|[?&])(?:key|api_key|apikey|token|access_token|relay_key)=)[^&]*", re.I)


def redact(text):
    """Strip bot tokens and credential query parameters from a path for logging."""
    text = _TG_TOKEN.sub(r"\1:***", text or "")
    return _QUERY_SECRET.sub(r"\1***", text)


def mask_secret(value):
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return value[:4] + "•" * 6 + value[-4:]
