"""PhysioNet access, built on the official ``physionet`` package.

The package's client handles authentication: a username and password, a
personal access token (``PHYSIONET_TOKEN``) or the sign-in saved by
``physionet login``. Credentials are only ever sent to the PhysioNet origin.
This module adds retries and readable errors for the requests the tool makes
itself (checksum lists, sizes, and streaming the tables it filters); whole files
are downloaded by ``physionet.download`` (see download.py).
"""
from __future__ import annotations

import os
import threading
import time

import requests
from physionet import PhysioNetClient

from . import __version__

DEFAULT_BASE_URL = "https://physionet.org"
RETRY_STATUS = {429, 500, 502, 503, 504}


class PhysioNetError(Exception):
    pass


class AuthError(PhysioNetError):
    pass


class AccessError(PhysioNetError):
    pass


class NotFound(PhysioNetError):
    pass


def base_url() -> str:
    return (os.environ.get("PHYSIONET_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


class Client:
    """Requests to ``<base_url>/files/...`` through ``physionet.PhysioNetClient`` sessions."""

    def __init__(self, user: str | None = None, password: str | None = None, token: str | None = None,
                 base: str | None = None, timeout: float = 60, retries: int = 5):
        self.base_url = (base or base_url()).rstrip("/")
        self.user, self.password, self.token = user, password, token
        self.timeout, self.retries = timeout, retries
        self._local = threading.local()

    @property
    def credentials(self) -> dict:
        """For physionet.download(); empty values fall back to its own lookup (saved sign-in)."""
        return {"username": self.user, "password": self.password, "token": self.token}

    def _client(self) -> PhysioNetClient:
        c = getattr(self._local, "c", None)
        if c is None:   # one client per thread: requests sessions are not shared across threads
            c = PhysioNetClient(base_url=self.base_url, username=self.user, password=self.password,
                                token=self.token, timeout=int(self.timeout))
            c.session.headers["User-Agent"] = f"multi-mimic/{__version__} ({c.session.headers['User-Agent']})"
            c.session.headers["Accept"] = "*/*"
            self._local.c = c
        return c

    @property
    def signed_in(self) -> bool:
        return self._client().auth_method is not None

    def url(self, rel: str) -> str:
        return f"{self.base_url}/files/{rel.lstrip('/')}"

    def request(self, method: str, rel: str, *, auth: bool = True, stream: bool = False,
                headers: dict | None = None, ok=(200, 206)) -> requests.Response:
        session = self._client().session
        url = self.url(rel)
        last = None
        for attempt in range(self.retries):
            try:
                kw = {} if auth else {"auth": lambda r: r}   # open files: send no credentials
                r = session.request(method, url, stream=stream, headers=headers or {},
                                    timeout=self.timeout, allow_redirects=True, **kw)
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
                raise AuthError("PhysioNet rejected the sign-in (username/password or token)"
                                if self.signed_in else
                                "this project needs a PhysioNet sign-in: use --user, PHYSIONET_TOKEN "
                                "or `physionet login`")
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
