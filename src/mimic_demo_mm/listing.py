"""What files does a project version contain?

Primary: the project's SHA256SUMS.txt (exact paths + checksums), streamed and
filtered on the fly so huge lists (hundreds of thousands of files) stay cheap.
Fallback: crawl the server's directory listings (no checksums).
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

from tqdm import tqdm

from .http import Client, NotFound
from .sources import Source

SUBJECT_DIR = re.compile(r"(?:^|/)p(\d{8})/")
HREF = re.compile(r'href="([^"?#]+)"')


def is_table(path: str) -> bool:
    return not path.startswith("files/") and path.lower().endswith((".csv", ".csv.gz"))


def subject_of(path: str) -> str | None:
    m = SUBJECT_DIR.search(path)
    return m.group(1) if m else None


def keep_fn(src: Source, demo_ids: set[str]) -> Callable[[str], bool]:
    if src.mode == "full":
        return lambda p: True
    if src.mode == "tables":
        return lambda p: not p.startswith("files/")
    return lambda p: (not p.startswith("files/")) or subject_of(p) in demo_ids


def _parse_sums(lines: Iterable[str], keep) -> list[tuple[str, str | None]]:
    out = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        path = parts[1].lstrip("*").removeprefix("./")
        if path != "SHA256SUMS.txt" and keep(path):
            out.append((path, parts[0].lower()))
    return out


def _crawl(client: Client, src: Source, auth: bool, roots: list[str], keep, deep_files: bool):
    out, seen = [], set()
    todo = list(roots)
    while todo:
        d = todo.pop()
        if d in seen:
            continue
        seen.add(d)
        try:
            html = client.request("GET", f"{src.rel}/{d}", auth=auth).text
        except NotFound:
            continue
        for href in HREF.findall(html):
            if href.startswith(("../", "/", "http:", "https:")) or href in ("./",):
                continue
            path = d + href
            if href.endswith("/"):
                if path == "files/" and not deep_files:
                    continue
                todo.append(path)
            elif path != "SHA256SUMS.txt" and keep(path):
                out.append((path, None))
    return out


def list_files(client: Client, src: Source, demo_ids: set[str]) -> tuple[list[tuple[str, str | None]], str]:
    """-> ([(relative path, sha256 or None)], how the list was obtained)."""
    auth = src.credentialed
    keep = keep_fn(src, demo_ids)
    try:
        r = client.request("GET", f"{src.rel}/SHA256SUMS.txt", auth=auth, stream=True)
        total = int(r.headers.get("Content-Length") or 0) or None
        bar = tqdm(total=total, unit="B", unit_scale=True, desc=f"  listing {src.key}", leave=False)

        def lines():
            for raw in r.iter_lines():
                bar.update(len(raw) + 1)
                yield raw.decode("utf-8", "replace")
        try:
            return _parse_sums(lines(), keep), "SHA256SUMS.txt"
        finally:
            bar.close()
            r.close()
    except NotFound:
        pass
    if src.mode == "demo":
        roots = [""] + [f"files/p{i[:2]}/p{i}/" for i in sorted(demo_ids)]
        return _crawl(client, src, auth, roots, keep, deep_files=False), "directory listing"
    return _crawl(client, src, auth, [""], keep, deep_files=src.mode == "full"), "directory listing"
