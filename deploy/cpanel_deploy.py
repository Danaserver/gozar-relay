#!/usr/bin/env python3
"""
Deploy Gozar to a cPanel account (Apache/LiteSpeed CGI) through the cPanel API.

  export CPANEL_TOKEN=xxxxxxxx            # cPanel » Security » Manage API Tokens
  python3 deploy/cpanel_deploy.py \\
      --host server.example.com --user cpuser --domain relay.example.com

What it does:
  1. creates the subdomain (if missing) with its own document root
  2. uploads relay.py, .htaccess and the gozar/ package
  3. keeps the database OUTSIDE the web root (~/.gozar/<domain>)
  4. on first install, uploads a one-shot bootstrap with a fresh admin password
     and access key, and prints them
  5. asks AutoSSL for a certificate and checks /_health

The API token is read from $CPANEL_TOKEN and never written anywhere.
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", "data"}


class CPanel:
    def __init__(self, host, user, token, port=2083, verify=True):
        self.base = "https://{}:{}".format(host, port)
        self.user = user
        self.auth = "cpanel {}:{}".format(user, token)
        self.ctx = ssl.create_default_context()
        if not verify:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def _open(self, req, timeout=60):
        req.add_header("Authorization", self.auth)
        with urllib.request.urlopen(req, context=self.ctx, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def uapi(self, module, func, **params):
        url = "{}/execute/{}/{}".format(self.base, module, func)
        data = urllib.parse.urlencode(params).encode()
        res = self._open(urllib.request.Request(url, data=data))
        if not res.get("status"):
            raise RuntimeError("{}::{} failed: {}".format(module, func, "; ".join(res.get("errors") or [])))
        return res.get("data")

    def api2(self, module, func, **params):
        q = dict(cpanel_jsonapi_user=self.user, cpanel_jsonapi_apiversion=2,
                 cpanel_jsonapi_module=module, cpanel_jsonapi_func=func, **params)
        url = "{}/json-api/cpanel?{}".format(self.base, urllib.parse.urlencode(q))
        return self._open(urllib.request.Request(url)).get("cpanelresult", {})

    def upload(self, remote_dir, files):
        """files: list of (filename, bytes). Overwrites existing files."""
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in (("dir", remote_dir), ("overwrite", "1")):
            parts.append('--{}\r\nContent-Disposition: form-data; name="{}"\r\n\r\n{}\r\n'.format(
                boundary, name, value).encode())
        for i, (fname, content) in enumerate(files, 1):
            parts.append('--{}\r\nContent-Disposition: form-data; name="file-{}"; filename="{}"\r\n'
                         'Content-Type: application/octet-stream\r\n\r\n'.format(boundary, i, fname).encode())
            parts.append(content + b"\r\n")
        parts.append("--{}--\r\n".format(boundary).encode())
        req = urllib.request.Request("{}/execute/Fileman/upload_files".format(self.base), data=b"".join(parts))
        req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
        res = self._open(req, timeout=180)
        if not res.get("status"):
            raise RuntimeError("upload to {} failed: {}".format(remote_dir, res.get("errors")))

    def mkdir(self, path):
        parent, name = path.rstrip("/").rsplit("/", 1)
        self.api2("Fileman", "mkdir", path=parent, name=name, permissions="0755")

    def exists(self, path):
        parent, name = path.rstrip("/").rsplit("/", 1)
        try:
            entries = self.uapi("Fileman", "list_files", dir=parent, include_mime=0) or []
        except RuntimeError:
            return False
        return any(e.get("file") == name for e in entries)

    def chmod(self, path, mode):
        self.api2("Fileman", "fileop", op="chmod", sourcefiles=path, metadata=mode)


def collect_files(python_bin):
    """Return {remote_relative_dir: [(name, bytes)]} for everything that must be uploaded."""
    out = {}
    with open(os.path.join(ROOT, "relay.py"), "rb") as f:
        relay = f.read()
    if python_bin:
        relay = b"#!" + python_bin.encode() + relay[relay.index(b"\n"):]
    out[""] = [("relay.py", relay.replace(b"\r\n", b"\n"))]
    with open(os.path.join(ROOT, ".htaccess"), "rb") as f:
        out[""].append((".htaccess", f.read()))
    pkg = os.path.join(ROOT, "gozar")
    for dirpath, dirnames, filenames in os.walk(pkg):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = os.path.relpath(dirpath, ROOT).replace("\\", "/")
        for fn in sorted(filenames):
            if fn.endswith((".pyc", ".pyo")):
                continue
            with open(os.path.join(dirpath, fn), "rb") as f:
                out.setdefault(rel, []).append((fn, f.read()))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True, help="cPanel hostname")
    ap.add_argument("--user", required=True, help="cPanel username")
    ap.add_argument("--domain", required=True, help="relay hostname, e.g. relay.example.com")
    ap.add_argument("--docroot", help="document root (default: /home/<user>/<domain>)")
    ap.add_argument("--data-dir", help="database dir (default: /home/<user>/.gozar/<domain>)")
    ap.add_argument("--python", default="/usr/bin/python3",
                    help="python interpreter for the CGI shebang (CloudLinux: /opt/alt/python311/bin/python3)")
    ap.add_argument("--port", type=int, default=2083)
    ap.add_argument("--insecure", action="store_true", help="do not verify the cPanel TLS certificate")
    ap.add_argument("--no-subdomain", action="store_true", help="do not try to create the subdomain")
    args = ap.parse_args()

    if ":" in args.python or "\\" in args.python:
        sys.exit("--python looks like a Windows path ({}). In Git Bash run with MSYS_NO_PATHCONV=1."
                 .format(args.python))
    token = os.environ.get("CPANEL_TOKEN")
    if not token:
        sys.exit("Set CPANEL_TOKEN in the environment.")
    cp = CPanel(args.host, args.user, token, args.port, verify=not args.insecure)
    home = "/home/" + args.user
    docroot = args.docroot or "{}/{}".format(home, args.domain)
    data_dir = args.data_dir or "{}/.gozar/{}".format(home, args.domain)

    # 1. subdomain
    if not args.no_subdomain:
        domains = cp.uapi("DomainInfo", "list_domains") or {}
        known = set(domains.get("sub_domains") or []) | set(domains.get("addon_domains") or [])
        if args.domain in known:
            print("• subdomain {} already exists".format(args.domain))
        else:
            sub, root = args.domain.split(".", 1)
            cp.uapi("SubDomain", "addsubdomain", domain=sub, rootdomain=root,
                    dir=os.path.relpath(docroot, home).replace("\\", "/"))
            print("✓ created subdomain {} → {}".format(args.domain, docroot))

    # 2. directories + files
    for d in ("{}/.gozar".format(home), data_dir):
        if not cp.exists(d):
            cp.mkdir(d)
    cp.chmod(data_dir, "0700")

    files = collect_files(args.python)
    for rel in sorted(files):
        remote = docroot + ("/" + rel if rel else "")
        if rel:
            parts = rel.split("/")
            for i in range(1, len(parts) + 1):
                path = docroot + "/" + "/".join(parts[:i])
                if not cp.exists(path):
                    cp.mkdir(path)
        cp.upload(remote, files[rel])
        print("✓ uploaded {:<22} ({} files)".format((rel or ".") + "/", len(files[rel])))

    ht = dict(files[""])[".htaccess"].decode()
    ht = "SetEnv GOZAR_DATA_DIR {}\n\n{}".format(data_dir, ht)
    cp.upload(docroot, [(".htaccess", ht.encode())])
    cp.chmod(docroot + "/relay.py", "0755")
    cp.chmod(docroot + "/.htaccess", "0644")

    # 3. first-run bootstrap
    creds = None
    if not cp.exists(data_dir + "/gozar.db"):
        with tempfile.TemporaryDirectory() as tmp:
            boot = os.path.join(tmp, "bootstrap.json")
            out = subprocess.check_output([sys.executable, os.path.join(ROOT, "relay.py"), "bootstrap",
                                           "--out", boot, "--public-url", "https://" + args.domain, "--json"],
                                          env=dict(os.environ, GOZAR_DATA_DIR=tmp))
            creds = json.loads(out.decode())
            with open(boot, "rb") as f:
                cp.upload(data_dir, [("bootstrap.json", f.read())])
            cp.chmod(data_dir + "/bootstrap.json", "0600")
        print("✓ uploaded first-run bootstrap")
    else:
        print("• existing database kept ({}/gozar.db)".format(data_dir))

    # 4. SSL + health
    try:
        cp.uapi("SSL", "start_autossl_check")
        print("✓ AutoSSL check requested")
    except Exception as exc:  # not fatal (may be disabled on the account)
        print("! AutoSSL: {}".format(exc))

    health = None
    for scheme in ("https", "http"):
        try:
            ctx = ssl.create_default_context() if scheme == "https" else None
            with urllib.request.urlopen("{}://{}/_health".format(scheme, args.domain), timeout=15, context=ctx) as r:
                health = "{} → {}".format(scheme, r.read().decode()[:120])
                break
        except Exception as exc:
            health = "{} → {}".format(scheme, exc)
    print("• health: {}".format(health))

    print("\n" + "=" * 60)
    print("Panel     : https://{}/".format(args.domain))
    if creds:
        print("Username  : {}".format(creds["username"]))
        print("Password  : {}".format(creds["password"]))
        print("Access key: {}".format(creds["key"]))
    print("=" * 60)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.time()
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit("cPanel API error: HTTP {} {}".format(e.code, e.read()[:300]))
    print("done in {:.1f}s".format(time.time() - t0))
