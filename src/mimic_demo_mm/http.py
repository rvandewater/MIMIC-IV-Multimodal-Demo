"""Thin, retrying HTTP client for PhysioNet's file server."""
from __future__ import annotations

import os
import threading
import time

import requests
from requests.adapters import HTTPAdapter

from . import __version__

DEFAULT_BASE = "https://physionet.org/files"
RETRY_STATUS = {429, 500, 502, 503, 504}


class PhysioNetError(Exception):
    pass


class AuthError(PhysioNetError):
    pass


class AccessError(PhysioNetError):
    pass


class NotFound(PhysioNetError):
    pass


class Client:
    def __init__(self, user: str | None = None, password: str | None = None,
                 base: str | None = None, timeout: float = 60, retries: int = 5):
        self.base = (base or os.environ.get("PHYSIONET_BASE") or DEFAULT_BASE).rstrip("/")
        self.auth = (user, password) if user else None
        self.timeout, self.retries = timeout, retries
        self._local = threading.local()

    def _session(self) -> requests.Session:
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers["User-Agent"] = f"mimic-demo-mm/{__version__}"
            s.mount("https://", HTTPAdapter(pool_maxsize=32))
            s.mount("http://", HTTPAdapter(pool_maxsize=32))
            self._local.s = s
        return s

    def url(self, rel: str) -> str:
        return f"{self.base}/{rel.lstrip('/')}"

    def request(self, method: str, rel: str, *, auth: bool = True, stream: bool = False,
                headers: dict | None = None, ok=(200, 206)) -> requests.Response:
        url = self.url(rel)
        last = None
        for attempt in range(self.retries):
            try:
                r = self._session().request(method, url, auth=self.auth if auth else None, stream=stream,
                                            headers=headers or {}, timeout=self.timeout, allow_redirects=True)
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code in ok or r.status_code == 416:
                return r
            if r.status_code in RETRY_STATUS:
                last = PhysioNetError(f"HTTP {r.status_code}")
                r.close()
                time.sleep(min(2 ** attempt, 30))
                continue
            r.close()
            if r.status_code == 401:
                raise AuthError("PhysioNet rejected the username/password")
            if r.status_code == 403:
                raise AccessError("access refused: sign this project's data use agreement on PhysioNet")
            if r.status_code == 404:
                raise NotFound(rel)
            raise PhysioNetError(f"HTTP {r.status_code} for {rel}")
        raise PhysioNetError(f"giving up after {self.retries} attempts ({last})")

    def head_size(self, rel: str, auth: bool = True) -> int | None:
        r = self.request("HEAD", rel, auth=auth)
        n = r.headers.get("Content-Length")
        return int(n) if n and n.isdigit() else None
