"""
End-to-end tests: a fake upstream API + a real Gozar standalone server.
Run with:  python -m unittest discover -s tests -v
"""

import http.server
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

TMP = tempfile.mkdtemp(prefix="gozar-test-")
os.environ["GOZAR_DATA_DIR"] = TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gozar import security  # noqa: E402
from gozar.runners import Handler, ThreadedServer  # noqa: E402
from gozar.store import get_store  # noqa: E402


class Upstream(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _echo(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(3):
                data = "data: {}\n\n".format(i).encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                self.wfile.flush()
                time.sleep(0.05)
            self.wfile.write(b"0\r\n\r\n")
            return
        payload = json.dumps({
            "method": self.command, "path": self.path, "body": body.decode(),
            "headers": {k.lower(): v for k, v in self.headers.items()},
        }).encode()
        self.send_response(int(self.headers.get("X-Want-Status") or 200))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Set-Cookie", "upstream=1")
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = _echo

    def log_message(self, *a):
        pass


def serve(handler):
    srv = ThreadedServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class RelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = serve(Upstream)
        up_url = "http://127.0.0.1:{}".format(cls.up.server_port)
        cls.store = st = get_store()
        creds = st.initialize(password="admin-pass-123")
        cls.key = creds["key"]
        for s in st.list_services():
            st.update_service(s["id"], {"upstream": up_url})
        st.update_service(st.get_service(slug="openrouter")["id"], {"upstream_keys": "sk-or-REAL"})
        st.update_service(st.get_service(slug="gemini")["id"], {"upstream_keys": "AIza-REAL"})
        cls.tg_only = st.add_key({"name": "tg", "services": "telegram"})["key"]
        cls.limited = st.add_key({"name": "limited", "services": "*", "rate_limit": 2})["key"]
        cls.relay = serve(Handler)
        cls.base = "http://127.0.0.1:{}".format(cls.relay.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.relay.shutdown()
        cls.up.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)

    def call(self, path, method="GET", headers=None, body=None):
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def jcall(self, *a, **kw):
        status, headers, body = self.call(*a, **kw)
        return status, headers, json.loads(body.decode())

    # ----------------------------------------------------------- telegram

    def test_legacy_telegram_path(self):
        s, _, j = self.jcall("/{}/bot123:ABC/getMe?x=1".format(self.key))
        self.assertEqual(s, 200)
        self.assertEqual(j["path"], "/bot123:ABC/getMe?x=1")

    def test_telegram_with_service_slug(self):
        s, h, j = self.jcall("/{}/telegram/bot1:X/sendMessage".format(self.key), "POST",
                             {"Content-Type": "application/json", "Cookie": "gozar_session=secret",
                              "X-Forwarded-For": "5.6.7.8"}, b'{"chat_id":1}')
        self.assertEqual(s, 200)
        self.assertEqual(j["path"], "/bot1:X/sendMessage")
        self.assertEqual(j["body"], '{"chat_id":1}')
        self.assertNotIn("cookie", j["headers"])
        self.assertNotIn("x-forwarded-for", j["headers"])
        self.assertNotIn("Set-Cookie", h)

    def test_telegram_file_path(self):
        s, _, j = self.jcall("/{}/file/bot1:X/photos/a.jpg".format(self.key))
        self.assertEqual(j["path"], "/file/bot1:X/photos/a.jpg")

    def test_missing_key_is_rejected_telegram_style(self):
        s, _, j = self.jcall("/telegram/bot1:X/getMe")
        self.assertEqual(s, 401)
        self.assertFalse(j["ok"])

    def test_header_key(self):
        s, _, j = self.jcall("/telegram/bot1:X/getMe", headers={"X-Relay-Key": self.key})
        self.assertEqual(s, 200)
        self.assertNotIn("x-relay-key", j["headers"])

    def test_query_key_is_stripped(self):
        s, _, j = self.jcall("/telegram/bot1:X/getMe?relay_key={}&a=b".format(self.key))
        self.assertEqual(j["path"], "/bot1:X/getMe?a=b")

    # ------------------------------------------------------- managed keys

    def test_openrouter_managed_bearer(self):
        s, _, j = self.jcall("/openrouter/api/v1/chat/completions", "POST",
                             {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}, b"{}")
        self.assertEqual(s, 200)
        self.assertEqual(j["path"], "/api/v1/chat/completions")
        self.assertEqual(j["headers"]["authorization"], "Bearer sk-or-REAL")

    def test_gemini_managed_header_and_query(self):
        s, _, j = self.jcall("/gemini/v1beta/models/x:generateContent", "POST", {"x-goog-api-key": self.key}, b"{}")
        self.assertEqual(j["headers"]["x-goog-api-key"], "AIza-REAL")
        s, _, j = self.jcall("/gemini/v1beta/models?key={}&pageSize=5".format(self.key))
        self.assertEqual(s, 200)
        self.assertEqual(j["path"], "/v1beta/models?pageSize=5")
        self.assertEqual(j["headers"]["x-goog-api-key"], "AIza-REAL")

    def test_passthrough_keeps_client_auth(self):
        st = self.store
        svc = st.add_service({"slug": "passthru", "name": "P", "upstream": "http://127.0.0.1:{}/base".format(
            self.up.server_port), "auth_type": "bearer", "auth_name": "Authorization"})
        try:
            s, _, j = self.jcall("/{}/passthru/v1/x".format(self.key), headers={"Authorization": "Bearer user-own"})
            self.assertEqual(j["headers"]["authorization"], "Bearer user-own")
            self.assertEqual(j["path"], "/base/v1/x")
        finally:
            st.delete_service(svc["id"])

    def test_host_style_routing(self):
        host = "127.0.0.1:{}".format(self.up.server_port)
        s, _, j = self.jcall("/{}/api/v1/chat/completions".format(host), "POST",
                             {"X-Relay-Key": self.key, "Authorization": "Bearer provider-key"}, b"{}")
        self.assertEqual(s, 200)
        self.assertEqual(j["path"], "/api/v1/chat/completions")
        s, _, _ = self.jcall("/{}/{}/x".format(self.key, host))
        self.assertEqual(s, 200)
        s, _, _ = self.jcall("/evil.example.com/x", headers={"X-Relay-Key": self.key})
        self.assertEqual(s, 404)

    def test_variables_headers_params(self):
        from gozar import variables as V
        st = self.store
        svc = st.add_service({
            "slug": "withvars", "name": "V", "auth_type": "bearer", "auth_name": "Authorization",
            "upstream": "http://127.0.0.1:{}/acct/{{{{ACCOUNT_ID}}}}".format(self.up.server_port),
            "upstream_keys": "{{PROVIDER_KEY}}",
            "variables": V.dump({"ACCOUNT_ID": "a1", "SITE": "Default", "PROVIDER_KEY": "svc-key"}),
            "headers": V.dump({"X-Title": "{{SITE}} via {{KEY_NAME}}", "X-Ver?": "1", "X-Drop": ""}),
            "params": V.dump({"src": "{{SERVICE}}"})})
        k = st.add_key({"name": "Hamicar", "services": "*",
                        "variables": V.dump({"SITE": "Hamicar", "PROVIDER_KEY": "key-own"})})
        try:
            s, _, j = self.jcall("/{}/withvars/v1/x?a=1".format(k["key"]),
                                 headers={"X-Ver": "client", "X-Drop": "bye"})
            self.assertEqual(s, 200)
            self.assertEqual(j["path"], "/acct/a1/v1/x?a=1&src=withvars")
            h = j["headers"]
            self.assertEqual(h["x-title"], "Hamicar via Hamicar")
            self.assertEqual(h["x-ver"], "client")
            self.assertNotIn("x-drop", h)
            self.assertEqual(h["authorization"], "Bearer key-own")
        finally:
            st.delete_service(svc["id"])
            st.delete_key(k["id"])

    # -------------------------------------------------------------- policy

    def test_service_restriction(self):
        s, _, j = self.jcall("/{}/openrouter/api/v1/models".format(self.tg_only))
        self.assertEqual(s, 403)
        self.assertIn("error", j)

    def test_rate_limit(self):
        codes = [self.call("/{}/telegram/bot1:X/getMe".format(self.limited))[0] for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_upstream_status_passthrough(self):
        s, _, _ = self.call("/{}/telegram/bot1:X/getMe".format(self.key), headers={"X-Want-Status": "400"})
        self.assertEqual(s, 400)

    def test_disabled_relay(self):
        self.store.set("enabled", False)
        try:
            s, _, _ = self.call("/{}/telegram/bot1:X/getMe".format(self.key))
            self.assertEqual(s, 503)
        finally:
            self.store.set("enabled", True)

    def test_streaming(self):
        s, h, body = self.call("/{}/openrouter/stream".format(self.key))
        self.assertEqual(s, 200)
        self.assertEqual(body, b"data: 0\n\ndata: 1\n\ndata: 2\n\n")

    def test_logs_redact_tokens(self):
        self.call("/{}/bot999:SECRETTOKEN/getMe".format(self.key))
        time.sleep(0.1)
        paths = [l["path"] for l in self.store.recent_logs(20)]
        self.assertTrue(any("bot999:***" in p for p in paths))
        self.assertFalse(any("SECRETTOKEN" in p for p in paths))

    # --------------------------------------------------------------- panel

    def test_panel_login_flow(self):
        s, _, body = self.call("/")
        self.assertEqual(s, 200)
        html = body.decode()
        self.assertIn('name="captcha_token"', html)
        # Mint a captcha token with a known answer using the server secret.
        secret = self.store.get("secret")
        ts, nonce = str(int(time.time())), "abcdef"
        answer = "ABCDE"
        token = "{}.{}.{}".format(ts, nonce, security._sign(secret, "cap|ABCDE|{}|{}".format(ts, nonce)))
        form = "username=admin&password=admin-pass-123&captcha={}&captcha_token={}".format(answer, token)
        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(self.base + "/_panel/login", data=form.encode(), method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            opener.open(req)
            self.fail("expected redirect")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 303)
            cookie = e.headers["Set-Cookie"].split(";")[0]

        s, _, body = self.call("/", headers={"Cookie": cookie})
        csrf = re.search(r'csrf: "([^"]+)"', body.decode()).group(1)
        s, _, state = self.jcall("/_panel/api/state", headers={"Cookie": cookie})
        self.assertEqual(s, 200)
        self.assertTrue(all("REAL" not in json.dumps(x) for x in state["services"]))

        s, _, _ = self.jcall("/_panel/api/keys/save", "POST", {"Cookie": cookie, "Content-Type": "application/json"},
                             json.dumps({"name": "x"}).encode())
        self.assertEqual(s, 403)  # no CSRF header
        s, _, j = self.jcall("/_panel/api/keys/save", "POST",
                             {"Cookie": cookie, "Content-Type": "application/json", "X-CSRF-Token": csrf},
                             json.dumps({"name": "Hamikar", "services": ["openrouter", "gemini"]}).encode())
        self.assertEqual(s, 200)
        self.assertEqual(j["key"]["services"], ["openrouter", "gemini"])

    def test_panel_api_requires_login(self):
        s, _, _ = self.call("/_panel/api/state")
        self.assertEqual(s, 401)

    def test_static_and_health(self):
        s, h, _ = self.call("/_panel/static/app.js")
        self.assertEqual(s, 200)
        s, _, _ = self.call("/_panel/static/../store.py")
        self.assertEqual(s, 404)
        s, _, j = self.jcall("/_health")
        self.assertEqual(j["status"], "ok")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


class CgiAndMigrationTests(unittest.TestCase):
    def test_cgi_runner(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tmp = tempfile.mkdtemp(prefix="gozar-cgi-")
        env = dict(os.environ, GOZAR_DATA_DIR=tmp, GATEWAY_INTERFACE="CGI/1.1", REQUEST_METHOD="GET",
                   REQUEST_URI="/_health", SCRIPT_NAME="/relay.py", HTTP_HOST="relay.test", HTTPS="on")
        try:
            out = subprocess.run([sys.executable, os.path.join(root, "relay.py")], env=env,
                                 stdout=subprocess.PIPE, timeout=30).stdout
            self.assertTrue(out.startswith(b"Status: 200 OK"), out[:200])
            self.assertIn(b'"status": "ok"', out)
            env["REQUEST_URI"] = "/sub/_health"
            env["SCRIPT_NAME"] = "/sub/relay.py"
            out = subprocess.run([sys.executable, os.path.join(root, "relay.py")], env=env,
                                 stdout=subprocess.PIPE, timeout=30).stdout
            self.assertIn(b'"status": "ok"', out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cgi_buffers_streamed_body(self):
        import io
        from unittest import mock
        from gozar import runners
        from gozar.http import Response

        class Out(io.BytesIO):
            writes = 0

            def write(self, b):
                Out.writes += 1
                return super().write(b)

        def stream():
            yield b'{"data": ['
            yield b'"a", "b"'
            yield b']}'

        cases = [
            (Response(200, [("Content-Type", "application/json")], stream()), True),
            (Response(200, [("Content-Type", "text/event-stream")], iter([b"data: 1\n\n", b"data: 2\n\n"])), False),
        ]
        for resp, buffered in cases:
            out = Out()
            Out.writes = 0
            fake_stdout = mock.Mock(buffer=out)
            fake_stdin = mock.Mock(buffer=io.BytesIO())
            env = {"REQUEST_METHOD": "GET", "REQUEST_URI": "/x", "SCRIPT_NAME": "/relay.py"}
            with mock.patch.object(runners, "dispatch", return_value=resp), \
                    mock.patch.object(runners.sys, "stdout", fake_stdout), \
                    mock.patch.object(runners.sys, "stdin", fake_stdin), \
                    mock.patch.dict(runners.os.environ, env, clear=True):
                runners.run_cgi()
            raw = out.getvalue()
            if buffered:
                self.assertEqual(Out.writes, 1)
                self.assertIn(b"Content-Length: 20\r\n", raw)
                self.assertTrue(raw.endswith(b'{"data": ["a", "b"]}'))
            else:
                self.assertGreater(Out.writes, 1)
                self.assertNotIn(b"Content-Length", raw)
                self.assertTrue(raw.endswith(b"data: 2\n\n"))

    def test_legacy_import(self):
        from gozar.store import Store
        tmp = tempfile.mkdtemp(prefix="gozar-legacy-")
        try:
            cfg = os.path.join(tmp, "config.json")
            with open(cfg, "w") as f:
                json.dump({"enabled": True, "admin": {"username": "boss", "password_hash": "abc:def"},
                           "bot_keys": [{"name": "Old bot", "key": "key_0123456789", "enabled": True}]}, f)
            st = Store(os.path.join(tmp, "x.db"))
            self.assertTrue(st.import_legacy_config(cfg))
            self.assertEqual(st.get("admin_username"), "boss")
            k = st.get_key(key="key_0123456789")
            self.assertEqual(k["services"], "telegram")
            self.assertEqual([s["slug"] for s in st.list_services()], ["telegram", "openrouter", "gemini", "anthropic", "groq"])
            st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bootstrap_file(self):
        from gozar.store import Store
        tmp = tempfile.mkdtemp(prefix="gozar-boot-")
        try:
            boot = os.path.join(tmp, "bootstrap.json")
            with open(boot, "w", encoding="utf-8") as f:
                json.dump({"admin_username": "admin", "admin_password_hash": security.hash_password("pw"),
                           "public_url": "https://relay.test",
                           "keys": [{"name": "k", "key": "gz_bootstrapkey123", "services": "*"}]}, f)
            st = Store(os.path.join(tmp, "x.db"))
            self.assertTrue(st.import_bootstrap(boot))
            self.assertFalse(os.path.exists(boot))
            self.assertTrue(st.is_initialized())
            self.assertTrue(security.verify_password("pw", st.get("admin_password_hash")))
            self.assertIsNotNone(st.get_key(key="gz_bootstrapkey123"))
            st.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class VariablesTests(unittest.TestCase):
    def test_parse_and_mask(self):
        from gozar import variables as V
        self.assertEqual(V.parse("# c\nA=1\nB = two=2\n", "vars"), {"A": "1", "B": "two=2"})
        self.assertEqual(V.parse("X-T: a: b\nY?: 1", "headers"), {"X-T": "a: b", "Y?": "1"})
        with self.assertRaises(ValueError):
            V.parse("bad line", "vars")
        with self.assertRaises(ValueError):
            V.parse("Host: x", "headers")
        old = {"API_KEY": "secret-value-123456"}
        text = V.to_text(old, "vars", mask=True)
        self.assertNotIn("secret-value", text)
        self.assertEqual(V.merge_secrets(V.parse(text, "vars"), old), old)


class SecurityTests(unittest.TestCase):
    def test_password_hash_formats(self):
        h = security.hash_password("secret")
        self.assertTrue(security.verify_password("secret", h))
        self.assertFalse(security.verify_password("nope", h))
        import hashlib
        legacy = "abc:" + hashlib.pbkdf2_hmac("sha256", b"old", b"abc", 100000).hex()
        self.assertTrue(security.verify_password("old", legacy))

    def test_session_generation_invalidates(self):
        t = security.make_session("admin", "s", 1)
        self.assertEqual(security.verify_session(t, "s", 1), "admin")
        self.assertIsNone(security.verify_session(t, "s", 2))
        self.assertIsNone(security.verify_session(t, "other", 1))

    def test_redact(self):
        self.assertEqual(security.redact("/bot12:AAbb-cc/getMe?key=xyz&a=1"), "/bot12:***/getMe?key=***&a=1")


if __name__ == "__main__":
    unittest.main()
