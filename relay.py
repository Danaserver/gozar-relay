#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gozar — universal API relay (entry point).

  * Under Apache / LiteSpeed / cPanel this file is executed as a CGI script.
  * On a VPS run it directly:  python3 relay.py serve --port 8080
  * See `python3 relay.py --help` for management commands.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

if __name__ == "__main__":
    if "GATEWAY_INTERFACE" in os.environ:
        from gozar.runners import run_cgi
        run_cgi()
    else:
        from gozar.cli import main
        sys.exit(main())
