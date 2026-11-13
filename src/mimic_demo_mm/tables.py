"""Stream a CSV table from PhysioNet and keep only the demo patients' rows.

The full table is never written to disk. Handles multi-GB gzipped tables and
very long quoted multi-line fields (clinical notes)."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))


class NoSubjectColumn(Exception):
    pass


class _Counting(io.RawIOBase):
    def __init__(self, read, bar, stop):
        self.read_fn, self.bar, self.stop = read, bar, stop

    def readable(self):
        return True

    def readinto(self, b):
        if self.stop.is_set():
            raise KeyboardInterrupt
        data = self.read_fn(len(b))
        n = len(data)
        b[:n] = data
        if self.bar is not None:
            self.bar.update(n)
        return n


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def filter_stream(read, path: str, dest: Path, ids: set[str], bar, stop) -> dict:
    """Read the bytes of table ``path`` through ``read(n)`` (from PhysioNet or a
    local copy) and write the rows whose subject_id is in ``ids`` to ``dest``
    (gzipped if dest ends .gz). Raises NoSubjectColumn if there is no subject_id column."""
    gz = path.endswith(".gz")
    buf = io.BufferedReader(_Counting(read, bar, stop), buffer_size=1 << 20)
    text = io.TextIOWrapper(gzip.GzipFile(fileobj=buf) if gz else buf, encoding="utf-8", newline="")
    reader = csv.reader(text)
    header = next(reader)
    names = [h.strip().lower() for h in header]
    if "subject_id" not in names:
        raise NoSubjectColumn(path)
    idx = names.index("subject_id")
    tmp = dest.with_name(dest.name + ".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    rows = scanned = 0
    subjects: set[str] = set()
    opener = (lambda p: gzip.open(p, "wt", encoding="utf-8", newline="")) if dest.name.endswith(".gz") \
        else (lambda p: open(p, "w", encoding="utf-8", newline=""))
    with opener(tmp) as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for row in reader:
            scanned += 1
            if len(row) > idx and row[idx].strip() in ids:
                w.writerow(row)
                rows += 1
                subjects.add(row[idx].strip())
    tmp.replace(dest)
    return {"rows": rows, "scanned": scanned, "subjects": sorted(subjects),
            "out_sha256": sha256_file(dest), "out_size": dest.stat().st_size}
