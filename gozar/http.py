"""Server-agnostic request/response objects shared by the CGI and standalone runners."""

import json
import urllib.parse
from http import cookies


class Headers:
    """Case-insensitive, order-preserving header map (one value per name)."""

    def __init__(self, items=()):
        self._d = {}
        for k, v in items:
            self[k] = v

    def __setitem__(self, name, value):
        self._d[name.lower()] = (name, value)

    def __getitem__(self, name):
        return self._d[name.lower()][1]

    def __contains__(self, name):
        return name.lower() in self._d

    def __delitem__(self, name):
        self._d.pop(name.lower(), None)

    def get(self, name, default=None):
        item = self._d.get(name.lower())
        return item[1] if item else default

    def pop(self, name, default=None):
        item = self._d.pop(name.lower(), None)
        return item[1] if item else default

    def items(self):
        return list(self._d.values())


class Request:
    def __init__(self, method, target, headers, body=b"", client_ip="", scheme="http", base_path=""):
        self.method = method.upper()
        split = urllib.parse.urlsplit(target)
        raw_path = split.path or "/"
        base_path = (base_path or "").rstrip("/")
        if base_path and raw_path.startswith(base_path):
            raw_path = raw_path[len(base_path):] or "/"
        self.path = raw_path
        self.query = split.query
        self.headers = headers if isinstance(headers, Headers) else Headers(headers)
        self.body = body or b""
        self.client_ip = client_ip
        self.scheme = scheme
        self.base_path = base_path
        self.host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "localhost"
        self._form = None
        self._cookies = None

    @property
    def segments(self):
        return [s for s in self.path.split("/") if s]

    @property
    def base_url(self):
        return "{}://{}{}".format(self.scheme, self.host, self.base_path)

    @property
    def cookie_path(self):
        return self.base_path or "/"

    def cookie(self, name):
        if self._cookies is None:
            self._cookies = cookies.SimpleCookie()
            try:
                self._cookies.load(self.headers.get("Cookie", ""))
            except cookies.CookieError:
                pass
        morsel = self._cookies.get(name)
        return morsel.value if morsel else ""

    def form(self):
        if self._form is None:
            ctype = (self.headers.get("Content-Type") or "").lower()
            if "application/json" in ctype:
                try:
                    data = json.loads(self.body.decode("utf-8") or "{}")
                except ValueError:
                    data = {}
                self._form = data if isinstance(data, dict) else {}
            else:
                parsed = urllib.parse.parse_qs(self.body.decode("utf-8", "replace"), keep_blank_values=True)
                self._form = {k: v[0] for k, v in parsed.items()}
        return self._form

    def query_params(self):
        return urllib.parse.parse_qs(self.query, keep_blank_values=True)


class Response:
    """
    body is either bytes or an iterator yielding bytes (streamed responses).
    `on_close` is called once the body has been fully written (used for logging).
    """

    def __init__(self, status=200, headers=None, body=b"", on_close=None):
        self.status = status
        self.headers = headers if isinstance(headers, Headers) else Headers(headers or [])
        self.body = body
        self.on_close = on_close
        self.cookies = []

    @property
    def streaming(self):
        return not isinstance(self.body, (bytes, bytearray))

    def set_cookie(self, name, value, req, max_age=None, http_only=True, same_site="Strict"):
        parts = ["{}={}".format(name, value), "Path=" + req.cookie_path, "SameSite=" + same_site]
        if http_only:
            parts.append("HttpOnly")
        if req.scheme == "https":
            parts.append("Secure")
        if max_age is not None:
            parts.append("Max-Age={}".format(int(max_age)))
        self.cookies.append("; ".join(parts))

    def header_list(self):
        items = self.headers.items()
        if not self.streaming and "Content-Length" not in self.headers:
            items.append(("Content-Length", str(len(self.body))))
        items.extend(("Set-Cookie", c) for c in self.cookies)
        return items

    def iter_body(self):
        if self.streaming:
            for chunk in self.body:
                if chunk:
                    yield chunk
        elif self.body:
            yield bytes(self.body)

    def close(self):
        if self.on_close:
            cb, self.on_close = self.on_close, None
            cb()


def json_response(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(status, [("Content-Type", "application/json; charset=utf-8"),
                             ("Cache-Control", "no-store")], body)


def html_response(html, status=200):
    return Response(status, [("Content-Type", "text/html; charset=utf-8"),
                             ("Cache-Control", "no-store"),
                             ("X-Frame-Options", "DENY"),
                             ("Referrer-Policy", "no-referrer"),
                             ("X-Content-Type-Options", "nosniff")], html.encode("utf-8"))


def redirect(location, status=303):
    return Response(status, [("Location", location)], b"")
