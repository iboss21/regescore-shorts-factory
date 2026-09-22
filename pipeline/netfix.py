"""
netfix.py — make outbound HTTP survive a flaky connection (phone hotspot, IPv6-only DNS answers).

Importing this module:
  1. prefers IPv4 for every socket lookup (hotspot DNS often returns AAAA records that don't route);
  2. retries DNS resolution a few times before giving up;
  3. installs urllib3 retries on every `requests` session created afterwards.

Import it before anything that makes network calls. No configuration needed.
Disable with NETFIX=0 in .env if you ever need raw behaviour.
"""
from __future__ import annotations

import os
import socket
import time

if os.getenv("NETFIX", "1") not in ("0", "false", "False"):
    # ---- 1 + 2: IPv4-first resolution with retries -------------------------
    _orig_getaddrinfo = socket.getaddrinfo

    def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        last = None
        for attempt in range(3):
            try:
                # ask for IPv4 first; fall back to whatever the caller wanted
                try:
                    res = _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
                    if res:
                        return res
                except socket.gaierror:
                    pass
                return _orig_getaddrinfo(host, port, family, type, proto, flags)
            except socket.gaierror as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise last  # type: ignore[misc]

    socket.getaddrinfo = _getaddrinfo  # type: ignore[assignment]

    # ---- 3: transport-level retries for requests ---------------------------
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        _retry = Retry(
            total=3, connect=3, read=2, backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "PUT", "HEAD"]),
            raise_on_status=False,
        )

        class _RetryAdapter(HTTPAdapter):
            def __init__(self, *a, **kw):
                kw.setdefault("max_retries", _retry)
                super().__init__(*a, **kw)

        _orig_session_init = requests.Session.__init__

        def _session_init(self, *a, **kw):
            _orig_session_init(self, *a, **kw)
            self.mount("https://", _RetryAdapter())
            self.mount("http://", _RetryAdapter())

        requests.Session.__init__ = _session_init  # type: ignore[assignment]
    except Exception:  # noqa: BLE001  - requests not installed yet; nothing to harden
        pass
