"""CGI (cPanel / Apache / LiteSpeed) and standalone threaded HTTP server runners."""

import http.server
import os
import socketserver
import ssl
import sys
import threading
import time
from http.client import responses as REASONS

from . import __version__, paths
from .app import dispatch
from .http import Headers, Request

MAX_BODY = 100 * 1024 * 1024  # 100 MB, Telegram's upload ceiling for bots is 50 MB


# ------------------------------------------------------------------------ CGI

def run_cgi():
    env = os.environ
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer

    length = env.get("CONTENT_LENGTH", "")
    body = stdin.read(min(int(length), MAX_BODY)) if length.isdigit() and int(length) > 0 else b""

    headers = Headers()
    for k, v in env.items():
        if k.startswith("HTTP_"):
            headers[k[5:].replace("_", "-").title()] = v
    if env.get("CONTENT_TYPE"):
        headers["Content-Type"] = env["CONTENT_TYPE"]
    # Apache hides Authorization from CGI unless .htaccess passes it through.
    if "Authorization" not in headers and env.get("REDIRECT_HTTP_AUTHORIZATION"):
        headers["Authorization"] = env["REDIRECT_HTTP_AUTHORIZATION"]

    scheme = headers.get("X-Forwarded-Proto") or (
        "https" if env.get("HTTPS", "").lower() in ("on", "1") or env.get("SERVER_PORT") == "443" else "http")
    script_dir = os.path.dirname(env.get("SCRIPT_NAME", "").replace("\\", "/"))
    base_path = "" if script_dir in ("", "/", ".") else script_dir

    req = Request(env.get("REQUEST_METHOD", "GET"), env.get("REQUEST_URI", "/"), headers, body,
                  client_ip=env.get("REMOTE_ADDR", ""), scheme=scheme.split(",")[0].strip(),
                  base_path=env.get("GOZAR_BASE_PATH", base_path))
    resp = dispatch(req)

    # LiteSpeed/Apache CGI on shared hosts can stall a response that is written in several
    # pieces. Anything that is not an event stream is read in full and written once.
    is_sse = "text/event-stream" in (resp.headers.get("Content-Type") or "").lower()
    buffered = None
    if resp.streaming and not is_sse and req.method != "HEAD":
        try:
            buffered = b"".join(resp.iter_body())
        except Exception:
            buffered = b""
        del resp.headers["Transfer-Encoding"]
        resp.headers["Content-Length"] = str(len(buffered))

    lines = ["Status: {} {}".format(resp.status, REASONS.get(resp.status, "OK"))]
    lines += ["{}: {}".format(k, v) for k, v in resp.header_list()]
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1", "replace")
    try:
        if req.method == "HEAD":
            stdout.write(head)
        elif buffered is not None:
            stdout.write(head + buffered)
        else:
            stdout.write(head)
            stdout.flush()
            for chunk in resp.iter_body():
                stdout.write(chunk)
                stdout.flush()
        stdout.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        resp.close()
    try:  # CGI has no background threads: run a due automatic backup after replying
        from . import backup
        backup.maybe_run()
    except Exception:
        pass


# ----------------------------------------------------------------- standalone

HANDSHAKE_TIMEOUT = 15


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 256
    is_ssl = False
    base_path = ""
    ssl_context = None

    def finish_request(self, request, client_address):
        # The TLS handshake runs here, in the per-connection thread, never in the
        # accept loop: a client that connects and stalls (scanners, DPI middleboxes)
        # must not block everyone else.
        if self.ssl_context is not None:
            try:
                request.settimeout(HANDSHAKE_TIMEOUT)
                request = self.ssl_context.wrap_socket(request, server_side=True)
            except (OSError, ssl.SSLError):
                try:
                    request.close()
                except OSError:
                    pass
                return
        try:
            super().finish_request(request, client_address)
        finally:
            try:
                request.close()
            except OSError:
                pass

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, ssl.SSLError, OSError)):
            return  # disconnects and timeouts are routine for a public relay
        super().handle_error(request, client_address)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Gozar/" + __version__
    sys_version = ""
    timeout = 75  # idle keep-alive / slow request read; upstream waits are not affected

    def _handle(self):
        length = self.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > MAX_BODY:
            self.send_error(413)
            return
        body = self.rfile.read(int(length)) if length.isdigit() and int(length) > 0 else b""
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            body = self._read_chunked()

        headers = Headers(self.headers.items())
        scheme = "https" if self.server.is_ssl else "http"
        scheme = (headers.get("X-Forwarded-Proto") or scheme).split(",")[0].strip()
        req = Request(self.command, self.path, headers, body, client_ip=self.client_address[0],
                      scheme=scheme, base_path=self.server.base_path)
        resp = dispatch(req)

        try:
            self.send_response_only(resp.status)
            self.send_header("Date", self.date_time_string())
            chunked = False
            for k, v in resp.header_list():
                self.send_header(k, v)
            if resp.streaming and "Content-Length" not in resp.headers:
                if self.command == "HEAD" or resp.status in (204, 304):
                    pass
                else:
                    chunked = True
                    self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            if self.command != "HEAD":
                for chunk in resp.iter_body():
                    if chunked:
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    else:
                        self.wfile.write(chunk)
                    self.wfile.flush()
                if chunked:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            self.close_connection = True
        finally:
            resp.close()

    def _read_chunked(self):
        data = bytearray()
        while True:
            size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
            if size == 0:
                self.rfile.readline()
                return bytes(data)
            data += self.rfile.read(size)
            self.rfile.readline()
            if len(data) > MAX_BODY:
                raise ValueError("body too large")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle

    def log_message(self, fmt, *args):
        sys.stderr.write("[{}] {} {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"),
                                               self.client_address[0], fmt % args))


def _https_server(host, port, cert, key, base_path):
    srv = ThreadedServer((host, port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    srv.ssl_context = ctx
    srv.is_ssl = True
    srv.base_path = base_path
    return srv


def run_standalone(host="0.0.0.0", port=8080, ssl_port=0, cert=None, key=None, base_path=""):
    base_path = (base_path or "").rstrip("/")
    servers = []
    if port:
        srv = ThreadedServer((host, port), Handler)
        srv.base_path = base_path
        servers.append(("http", port, srv))
    if ssl_port:
        cert = cert or os.path.join(paths.data_dir(), "tls", "fullchain.pem")
        key = key or os.path.join(paths.data_dir(), "tls", "privkey.pem")
        if os.path.exists(cert) and os.path.exists(key):
            servers.append(("https", ssl_port, _https_server(host, ssl_port, cert, key, base_path)))
        else:
            print("! TLS certificate not found ({}); HTTPS listener disabled.".format(cert))
    if not servers:
        print("! No listener could be started.")
        sys.exit(1)

    from . import backup
    backup.start_scheduler()
    print("Gozar relay v{} — database: {}".format(__version__, paths.db_path()))
    for scheme, p, _ in servers:
        print("  listening on {}://{}:{}{}".format(scheme, host, p, base_path or "/"))

    for _, _, srv in servers[:-1]:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        servers[-1][2].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, srv in servers:
            srv.server_close()
