"""
Per-relay variables, extra headers and extra query parameters.

Like environment variables on a Cloudflare Worker, every service (and every
access key) can carry variables that are injected into upstream requests:

    Variables      NAME=value                 (one per line, # comments allowed)
    Headers        Header-Name: value         `{{NAME}}` templates allowed
                   Header-Name?: value        only if the client did not send it
                   Header-Name:               (empty) remove the client's header
    Query params   name=value                 `{{NAME}}` templates allowed

Templates also work in the upstream URL path, e.g.
    https://api.cloudflare.com/client/v4/accounts/{{ACCOUNT_ID}}/ai/v1

Key variables override service variables. Built-ins: KEY_NAME, KEY_ID, SERVICE.
Variables whose name contains KEY, SECRET, TOKEN or PASS are masked in the panel.
"""

import json
import re

from . import security

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
HEADER_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~\-]{1,64}\??$")
TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
SECRET_HINTS = ("KEY", "SECRET", "TOKEN", "PASS")
MAX_ITEMS = 50


def load(raw):
    """JSON text from the database → dict."""
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def dump(data):
    return json.dumps(data or {}, ensure_ascii=False)


def is_secret(name):
    upper = name.upper()
    return any(h in upper for h in SECRET_HINTS)


def parse(text, kind):
    """
    Parse panel text into a dict. kind: 'vars' | 'headers' | 'params'.
    Raises ValueError with a Persian message on bad input.
    """
    if isinstance(text, dict):
        text = "\n".join("{}{}{}".format(k, ": " if kind == "headers" else "=", v) for k, v in text.items())
    out = {}
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sep = ":" if kind == "headers" else "="
        if sep not in line:
            raise ValueError("خط {}: قالب باید «{}» باشد".format(
                n, "Header: value" if kind == "headers" else "NAME=value"))
        name, value = line.split(sep, 1)
        name, value = name.strip(), value.strip()
        if kind == "headers":
            if not HEADER_RE.match(name):
                raise ValueError("خط {}: نام هدر نامعتبر است ({})".format(n, name))
            if name.rstrip("?").lower() in ("host", "content-length", "transfer-encoding", "connection"):
                raise ValueError("خط {}: هدر {} قابل تنظیم نیست".format(n, name))
        elif kind == "vars" and not NAME_RE.match(name):
            raise ValueError("خط {}: نام متغیر فقط حروف انگلیسی، عدد و _ ({})".format(n, name))
        elif kind == "params" and not name:
            raise ValueError("خط {}: نام پارامتر خالی است".format(n))
        if len(value) > 4000:
            raise ValueError("خط {}: مقدار خیلی طولانی است".format(n))
        out[name] = value
    if len(out) > MAX_ITEMS:
        raise ValueError("حداکثر {} مورد مجاز است".format(MAX_ITEMS))
    return out


def merge_secrets(new, old):
    """Keep stored values for secret variables the panel sent back still masked."""
    for name, value in list(new.items()):
        if name in old and is_secret(name) and value == security.mask_secret(old[name]):
            new[name] = old[name]
    return new


def to_text(data, kind, mask=False):
    sep = ": " if kind == "headers" else "="
    lines = []
    for name, value in (data or {}).items():
        if mask and kind == "vars" and is_secret(name):
            value = security.mask_secret(value)
        lines.append("{}{}{}".format(name, sep, value))
    return "\n".join(lines)


def context(service, key):
    """Variables visible to templates for one request."""
    ctx = dict(load(service.get("variables")))
    if key:
        ctx.update(load(key.get("variables")))
        ctx.setdefault("KEY_NAME", key.get("name") or "")
        ctx.setdefault("KEY_ID", str(key.get("id") or ""))
    ctx.setdefault("SERVICE", service.get("slug") or "")
    return ctx


def render(text, ctx):
    return TEMPLATE_RE.sub(lambda m: ctx.get(m.group(1), ""), text or "")
