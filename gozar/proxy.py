"""
The relay engine: resolves service + access key from a request, enforces
policy, and streams the request to the upstream API.

Supported URL shapes (all equivalent):

    /<ACCESS_KEY>/<service>/<upstream path>           key in the path
    /<service>/<upstream path>                        key in a header / query
    /<ACCESS_KEY>/bot<TOKEN>/<method>                 legacy v1 Telegram form
    /<ACCESS_KEY>/file/bot<TOKEN>/<file path>         legacy v1 Telegram files
    /<upstream host>/<full upstream path>             Worker-style (e.g. /openrouter.ai/api/v1/...)

Where the key may be sent instead of the path:
    X-Relay-Key: <key>          ?relay_key=<key>
    Authorization: Bearer <key> (or the service's own auth header / query param)
"""

import http.client
import json
import random
import re
import socket
import ssl
import time
import urllib.parse

from . import security, variables
from .http import Headers, Response

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailer", "trailers", "transfer-encoding", "upgrade",
}
# Never leak these to upstreams: they identify the client or belong to the panel.
STRIP_REQUEST = HOP_BY_HOP | {
    "host", "content-length", "cookie", "x-relay-key", "forwarded", "via",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-port",
    "x-real-ip", "true-client-ip", "cf-connecting-ip", "cf-ipcountry", "cf-ray",
    "cf-visitor", "cdn-loop", "x-request-start",
}
STRIP_RESPONSE = HOP_BY_HOP | {"alt-svc", "strict-transport-security"}

CHUNK = 16 * 1024
_SSL_CTX = ssl.create_default_context()


class RelayError(Exception):
    def __init__(self, status, message, code="relay_error"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def error_response(status, message, service=None, code="relay_error"):
    """Errors shaped like the upstream's own errors, so client SDKs surface them nicely."""
    preset = (service or {}).get("preset")
    if preset == "telegram":
        payload = {"ok": False, "error_code": status, "description": "[Gozar] " + message}
    elif preset == "gemini":
        payload = {"error": {"code": status, "message": "[Gozar] " + message, "status": code.upper()}}
    elif preset == "anthropic":
        payload = {"type": "error", "error": {"type": code, "message": "[Gozar] " + message}}
    else:
        payload = {"error": {"message": "[Gozar] " + message, "type": code, "code": status}}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return Response(status, [("Content-Type", "application/json; charset=utf-8"),
                             ("X-Gozar-Error", code)], body)


def cors_headers(req):
    return [
        ("Access-Control-Allow-Origin", req.headers.get("Origin") or "*"),
        ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"),
        ("Access-Control-Allow-Headers", req.headers.get("Access-Control-Request-Headers") or "*"),
        ("Access-Control-Max-Age", "86400"),
        ("Vary", "Origin"),
    ]


# ------------------------------------------------------------------ resolution

def _bearer(value):
    if value and value.lower().startswith("bearer "):
        return value[7:].strip()
    return ""


def _remainder(path, consumed):
    parts = path.lstrip("/").split("/", consumed)
    rest = parts[consumed] if len(parts) > consumed else ""
    return "/" + rest


def _service_by_host(store, segment):
    """
    Worker-style routing: /<upstream host>/<full upstream path>. Only hosts that
    belong to a configured service are accepted, so the relay never becomes an
    open proxy. The service's own base path is ignored (the client sends it).
    """
    if "." not in segment or not re.match(r"^[A-Za-z0-9.\-]+(:\d+)?$", segment):
        return None
    for s in store.list_services():
        parts = urllib.parse.urlsplit(s["upstream"])
        if parts.netloc.lower() == segment.lower():
            svc = dict(s)
            svc["upstream"] = "{}://{}".format(parts.scheme, parts.netloc)
            return svc
    return None


def _telegram_service(store):
    svc = store.get_service(slug="telegram")
    if svc:
        return svc
    for s in store.list_services():
        if s["preset"] == "telegram":
            return s
    return None


def resolve(req, store):
    """
    Work out (service, access_key, upstream_path, key_source) for a request.
    Raises RelayError on failure.
    """
    segs = req.segments
    if not segs:
        raise RelayError(404, "Not found")

    service = None
    key = None
    key_source = None
    consumed = 0

    first = store.get_service(slug=segs[0]) if security.SLUG_PATTERN.match(segs[0]) else None
    if first:
        service, consumed = first, 1
    else:
        key = store.get_key(key=segs[0]) if security.KEY_PATTERN.match(segs[0]) else None
        if key:
            key_source = "path"
            nxt = segs[1] if len(segs) > 1 else ""
            svc = store.get_service(slug=nxt) if nxt and security.SLUG_PATTERN.match(nxt) else None
            svc = svc or (_service_by_host(store, nxt) if nxt else None)
            if svc:
                service, consumed = svc, 2
            elif nxt.startswith("bot") or nxt == "file":
                service, consumed = _telegram_service(store), 1
            else:
                raise RelayError(404, "Unknown service. Use /<key>/<service>/...")
        elif segs[0].startswith("bot") or segs[0] == "file":
            service, consumed = _telegram_service(store), 0
        elif _service_by_host(store, segs[0]):
            service, consumed = _service_by_host(store, segs[0]), 1
        else:
            raise RelayError(404, "Unknown service or access key")

    if not service:
        raise RelayError(404, "Service is not configured")

    if key is None:
        key, key_source = _find_key(req, store, service)

    return service, key, _remainder(req.path, consumed), key_source


def _find_key(req, store, service):
    candidates = [("header", req.headers.get("X-Relay-Key"))]
    params = req.query_params()
    candidates.append(("query:relay_key", (params.get("relay_key") or [""])[0]))
    candidates.append(("auth:Authorization", _bearer(req.headers.get("Authorization"))))
    if service["auth_name"] and service["auth_type"] == "header":
        candidates.append(("auth:" + service["auth_name"], req.headers.get(service["auth_name"])))
    for qname in {service["auth_name"] if service["auth_type"] == "query" else "", "key"} - {""}:
        candidates.append(("query:" + qname, (params.get(qname) or [""])[0]))
    for source, value in candidates:
        if value and security.KEY_PATTERN.match(value):
            key = store.get_key(key=value)
            if key:
                return key, source
    return None, None


def check_access(store, service, key):
    if not store.get("enabled"):
        raise RelayError(503, "Relay is disabled by the administrator", "relay_disabled")
    if not service["enabled"]:
        raise RelayError(503, "Service '{}' is disabled".format(service["slug"]), "service_disabled")
    if not key:
        raise RelayError(401, "Missing or invalid access key", "invalid_key")
    if not key["enabled"]:
        raise RelayError(403, "Access key is disabled", "key_disabled")
    if key["expires_at"] and key["expires_at"] < time.time():
        raise RelayError(403, "Access key has expired", "key_expired")
    allowed = [s.strip() for s in (key["services"] or "*").split(",") if s.strip()]
    if "*" not in allowed and service["slug"] not in allowed:
        raise RelayError(403, "This key may not use service '{}'".format(service["slug"]), "service_forbidden")
    if key["rate_limit"] and store.requests_last_minute(key["id"]) >= key["rate_limit"]:
        raise RelayError(429, "Rate limit exceeded ({} requests/minute)".format(key["rate_limit"]), "rate_limited")


# -------------------------------------------------------------- request build

def _clean(value):
    return value.replace(chr(13), "").replace(chr(10), "")


def build_upstream(req, service, path, key_source, key=None):
    """Return (url, headers) for the upstream request."""
    ctx = variables.context(service, key)
    upstream = urllib.parse.urlsplit(service["upstream"])
    base = variables.render(upstream.path, ctx).rstrip("/")
    managed_key = _clean(variables.render(pick_upstream_key(service), ctx))

    drop_params = {"relay_key"}
    if key_source and key_source.startswith("query:"):
        drop_params.add(key_source.split(":", 1)[1])
    if managed_key and service["auth_type"] == "query":
        drop_params.add(service["auth_name"])
    if managed_key and service["preset"] == "gemini":
        drop_params.add("key")
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(req.query, keep_blank_values=True) if k not in drop_params]
    if managed_key and service["auth_type"] == "query" and service["auth_name"]:
        pairs.append((service["auth_name"], managed_key))
    extra_params = variables.load(service.get("params"))
    if extra_params:
        pairs = [(k, v) for k, v in pairs if k not in extra_params]
        pairs += [(k, variables.render(v, ctx)) for k, v in extra_params.items()]
    query = urllib.parse.urlencode(pairs) if pairs else ""

    url = urllib.parse.urlunsplit((upstream.scheme, upstream.netloc, base + path, query, ""))

    headers = Headers()
    for name, value in req.headers.items():
        if name.lower() not in STRIP_REQUEST:
            headers[name] = value
    if key_source and key_source.startswith("auth:"):
        del headers[key_source.split(":", 1)[1]]
    if managed_key:
        if service["auth_type"] == "bearer":
            headers["Authorization"] = "Bearer " + managed_key
        elif service["auth_type"] == "header" and service["auth_name"]:
            if service["preset"] == "gemini":
                del headers["Authorization"]
            headers[service["auth_name"]] = managed_key
    for name, template in variables.load(service.get("headers")).items():
        only_if_missing = name.endswith("?")
        name = name.rstrip("?")
        value = _clean(variables.render(template, ctx))
        if only_if_missing and name in headers:
            continue
        if value:
            headers[name] = value
        else:
            del headers[name]
    headers["Host"] = upstream.netloc
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Gozar-Relay/2"
    if req.body:
        headers["Content-Length"] = str(len(req.body))
    return url, headers


def pick_upstream_key(service):
    keys = [k.strip() for k in (service.get("upstream_keys") or "").splitlines() if k.strip()]
    return random.choice(keys) if keys else ""


# ---------------------------------------------------------------- forwarding

def open_upstream(method, url, headers, body, timeout):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https":
        conn = http.client.HTTPSConnection(parts.netloc, timeout=timeout, context=_SSL_CTX)
    else:
        conn = http.client.HTTPConnection(parts.netloc, timeout=timeout)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
    for name, value in headers.items():
        conn.putheader(name, value)
    conn.endheaders(body or None)
    return conn, conn.getresponse()


def _stream(conn, resp, stats):
    reader = getattr(resp, "read1", None)
    try:
        while True:
            chunk = reader(CHUNK) if reader else resp.read(CHUNK)
            if not chunk:
                break
            stats["bytes"] += len(chunk)
            yield chunk
    except (socket.timeout, OSError, http.client.HTTPException) as exc:
        stats["error"] = "stream: " + str(exc)
    finally:
        conn.close()


def handle(req, store):
    started = time.time()
    service = key = None
    log = {"ts": started, "method": req.method, "path": security.redact(req.path), "client_ip": req.client_ip}

    def finish(status, error=None, nbytes=0):
        log.update(status=status, error=error, bytes_out=nbytes,
                   duration_ms=int((time.time() - started) * 1000),
                   service=service["slug"] if service else None, key_id=key["id"] if key else None)
        try:
            store.log_request(log)
        except Exception:  # logging must never break relaying
            pass

    try:
        service, key, path, key_source = resolve(req, store)
        log["path"] = security.redact(path + ("?" + req.query if req.query else ""))

        if req.method == "OPTIONS" and service["cors"]:
            return Response(204, cors_headers(req), b"")

        check_access(store, service, key)
        url, headers = build_upstream(req, service, path, key_source, key)
    except RelayError as exc:
        resp = error_response(exc.status, exc.message, service, exc.code)
        if service and service["cors"]:
            for k, v in cors_headers(req):
                resp.headers[k] = v
        finish(exc.status, exc.message)
        return resp

    try:
        conn, upstream = open_upstream(req.method, url, headers, req.body, service["timeout"] or 120)
    except (socket.timeout, TimeoutError):
        finish(504, "upstream timeout")
        return error_response(504, "Upstream timed out", service, "upstream_timeout")
    except (OSError, http.client.HTTPException) as exc:
        finish(502, str(exc))
        return error_response(502, "Upstream unreachable: {}".format(exc), service, "upstream_error")

    out = Headers()
    for name, value in upstream.getheaders():
        if name.lower() not in STRIP_RESPONSE:
            if name.lower() == "set-cookie":
                continue
            out[name] = value
    out["X-Accel-Buffering"] = "no"
    if service["cors"]:
        for k, v in cors_headers(req):
            out[k] = v

    stats = {"bytes": 0, "error": None}
    status = upstream.status
    response = Response(status, out, _stream(conn, upstream, stats))
    response.on_close = lambda: finish(status, stats["error"], stats["bytes"])
    return response


# ------------------------------------------------------------------- testing

def probe(service, timeout=8):
    """Quick reachability check used by the panel. Returns (ok, detail, ms)."""
    started = time.time()
    try:
        parts = urllib.parse.urlsplit(service["upstream"])
        url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))
        conn, resp = open_upstream("GET", url, Headers([("Host", parts.netloc),
                                                        ("User-Agent", "Gozar-Relay/2")]), b"", timeout)
        resp.read(1024)
        conn.close()
        return True, "HTTP {}".format(resp.status), int((time.time() - started) * 1000)
    except Exception as exc:
        return False, str(exc) or exc.__class__.__name__, int((time.time() - started) * 1000)
