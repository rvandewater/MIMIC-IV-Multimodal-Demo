"""Where a source's files come from: PhysioNet, or a local copy you already have."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterator

from .http import Client
from .listing import _parse_sums, keep_fn, list_files
from .sources import Source

CHUNK = 1 << 20


class RemoteOrigin:
    def __init__(self, client: Client, src: Source):
        self.client, self.src = client, src

    def describe(self) -> str:
        return "PhysioNet"

    def list(self, ids: set[str]):
        return list_files(self.client, self.src, ids)

    def size(self, path: str) -> int | None:
        return self.client.head_size(f"{self.src.rel}/{path}", self.src.credentialed)

    def blocks(self, path: str, start: int) -> tuple[Iterator[bytes], bool, Callable]:
        """-> (byte blocks from ``start``, whether the server restarted from 0, close)."""
        headers = {"Range": f"bytes={start}-"} if start else {}
        r = self.client.request("GET", f"{self.src.rel}/{path}", auth=self.src.credentialed,
                                stream=True, headers=headers)
        if r.status_code == 416:
            r.close()
            return iter(()), False, lambda: None
        restarted = bool(start) and r.status_code != 206
        return r.raw.stream(CHUNK, decode_content=False), restarted, r.close

    def open_raw(self, path: str) -> tuple[Callable[[int], bytes], Callable]:
        r = self.client.request("GET", f"{self.src.rel}/{path}", auth=self.src.credentialed, stream=True)
        enc = r.headers.get("Content-Encoding", "").lower()
        decode = enc in ("gzip", "deflate") and not path.endswith(".gz")
        return (lambda n: r.raw.read(n, decode_content=decode)), r.close


class LocalOrigin:
    """A local copy of a PhysioNet project version (the folder that holds
    SHA256SUMS.txt / files/ / the tables)."""

    def __init__(self, src: Source, folder: Path, link: str = "copy"):
        self.src, self.link = src, link
        folder = Path(folder).expanduser().resolve()
        if not folder.is_dir():
            raise SystemExit(f"--local {src.key}: {folder} is not a folder")
        if (folder / src.version).is_dir() and not (folder / "SHA256SUMS.txt").exists():
            folder = folder / src.version   # accept the project folder as well as the version folder
        self.dir = folder

    def describe(self) -> str:
        return f"local copy ({self.link})"

    def file(self, path: str) -> Path:
        return self.dir / path

    def list(self, ids: set[str]):
        keep = keep_fn(self.src, ids)
        sums = self.dir / "SHA256SUMS.txt"
        if sums.exists():
            with open(sums, encoding="utf-8", errors="replace") as f:
                entries = _parse_sums(f, keep)
            return entries, "local SHA256SUMS.txt"
        # No checksum list: walk the folder, but only the demo patients' part of files/.
        out = []
        top = [p for p in self.dir.iterdir()]
        stack = [p for p in top if not (p.name == "files" and p.is_dir())]
        files_dir = self.dir / "files"
        if files_dir.is_dir() and self.src.mode == "full":
            stack.append(files_dir)
        elif files_dir.is_dir() and self.src.mode == "demo":
            stack += [files_dir / f"p{i[:2]}" / f"p{i}" for i in sorted(ids)]
        while stack:
            p = stack.pop()
            if p.is_dir():
                stack.extend(p.iterdir())
            elif p.is_file() and not p.name.endswith(".part"):
                rel = p.relative_to(self.dir).as_posix()
                if rel != "SHA256SUMS.txt" and keep(rel):
                    out.append((rel, None))
        return out, "local folder"

    def size(self, path: str) -> int | None:
        p = self.file(path)
        return p.stat().st_size if p.exists() else None

    def blocks(self, path: str, start: int):
        p = self.file(path)
        if not p.exists():
            raise FileNotFoundError(path)
        f = open(p, "rb")
        f.seek(start)
        return iter(lambda: f.read(CHUNK), b""), False, f.close

    def open_raw(self, path: str):
        p = self.file(path)
        if not p.exists():
            raise FileNotFoundError(path)
        f = open(p, "rb")
        return f.read, f.close

    def place(self, path: str, dest: Path) -> bool:
        """Hard-link or symlink instead of copying. Returns False to fall back to copying."""
        srcfile = self.file(path)
        if dest.exists() or dest.is_symlink():
            if dest.resolve() == srcfile.resolve():
                return True
            dest.unlink()
        try:
            if self.link == "hardlink":
                os.link(srcfile, dest)
            elif self.link == "symlink":
                os.symlink(srcfile, dest)
            else:
                return False
            return True
        except OSError:
            return False   # e.g. hard link across disks: copy instead


def same_file(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False

