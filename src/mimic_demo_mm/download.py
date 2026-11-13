"""Plan and run the download (from PhysioNet or from local copies)."""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .http import Client, NotFound, PhysioNetError
from .listing import is_table
from .manifest import Item, Manifest
from .origins import LocalOrigin, RemoteOrigin, same_file
from .sources import BY_KEY, DEMO_IDS, Source
from .tables import NoSubjectColumn, filter_stream, sha256_file

SMALL_FILE = 10 * 2 ** 20      # other top-level files (LICENSE, README...) kept if at most this big
WHOLE_TABLE = 200 * 2 ** 20    # tables without subject_id kept whole if at most this big
TTY = sys.stderr.isatty()


def human(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000 or unit == "TB":
            return f"{n:,.0f} {unit}" if unit in ("B", "KB") else f"{n:,.1f} {unit}"
        n /= 1000


def bar(**kw):
    return tqdm(mininterval=0.5 if TTY else 30, dynamic_ncols=True, **kw)


def local_path(root: Path, item: Item) -> Path:
    return root / BY_KEY[item.source].rel / item.path


def make_origins(sources: list[Source], client: Client, local: dict[str, Path], link: str, root: Path) -> dict:
    origins = {}
    for s in sources:
        if s.key in local:
            o = LocalOrigin(s, local[s.key], link)
            if o.dir == (root / s.rel).resolve():
                raise SystemExit(f"--local {s.key} points at the output folder itself; choose a different --out")
            origins[s.key] = o
        else:
            origins[s.key] = RemoteOrigin(client, s)
    return origins


# ---------------------------------------------------------------- demo IDs
def demo_ids(client: Client, root: Path, local: dict[str, Path]) -> set[str]:
    candidates = [root / DEMO_IDS[0] / DEMO_IDS[1]]
    if "mimic-iv-demo" in local:
        d = Path(local["mimic-iv-demo"]).expanduser()
        candidates += [d / DEMO_IDS[1], d / "2.2" / DEMO_IDS[1]]
    p = next((c for c in candidates if c.exists()), None)
    text = p.read_text() if p else client.request("GET", f"{DEMO_IDS[0]}/{DEMO_IDS[1]}", auth=False).text
    ids = set(re.findall(r"\b\d{8}\b", text))
    if not ids:
        raise SystemExit("could not read the demo patient IDs")
    return ids


# ---------------------------------------------------------------- planning
def plan(origins: dict, sources: list[Source], ids: set[str], man: Manifest, jobs: int) -> list[Item]:
    planned: list[Item] = []
    for src in sources:
        o = origins[src.key]
        try:
            entries, how = o.list(ids)
        except PhysioNetError as e:
            raise SystemExit(f"  x {src.key}: {e}")
        man.sources[src.key] = {"rel": src.rel, "access": src.access, "mode": src.mode,
                                "origin": o.describe(), "listing": how,
                                "local_dir": str(o.dir) if isinstance(o, LocalOrigin) else None}
        for path, sha in entries:
            kind = "table" if (src.mode != "full" and is_table(path, src)) else "file"
            planned.append(Item(src.key, path, kind, sha256=sha))
        print(f"  {src.key:<18} {len(entries):>7,} files/tables listed  [{o.describe()}, {how}]")
    items = man.merge(planned)

    need = [i for i in items if i.size is None or isinstance(origins[i.source], LocalOrigin)]
    if need:
        with bar(total=len(need), desc="  checking sizes", unit="file", leave=False) as b, \
                ThreadPoolExecutor(max(jobs * 2, 4)) as ex:
            futs = {ex.submit(origins[i.source].size, i.path): i for i in need}
            for f in as_completed(futs):
                try:
                    futs[f].size = f.result()
                except (PhysioNetError, OSError):
                    pass
                b.update()
    for it in items:  # other large top-level files are not needed (e.g. IMAGE_FILENAMES, report zips)
        src = BY_KEY[it.source]
        if src.mode != "full" and it.kind == "file" and not src.in_files(it.path) \
                and (it.size or 0) > SMALL_FILE:
            it.status, it.note = "skipped", "large top-level file, not needed for the demo patients"
    return items


def on_disk(root: Path, it: Item) -> bool:
    p = local_path(root, it)
    if not p.exists():
        return False
    if it.kind == "table":
        return it.status == "done" and it.out_size == p.stat().st_size
    return it.size is None or p.stat().st_size == it.size


# ---------------------------------------------------------------- execution
class _NullBar:
    def update(self, n):
        pass


class Runner:
    def __init__(self, origins: dict, root: Path, man: Manifest, ids: set[str], jobs: int):
        self.origins, self.root, self.man, self.ids, self.jobs = origins, root, man, ids, jobs
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def _bump(self, b, n):
        with self.lock:
            b.update(n)

    def fetch_file(self, it: Item, total_bar) -> None:
        o = self.origins[it.source]
        dest = local_path(self.root, it)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(o, LocalOrigin):
            srcfile = o.file(it.path)
            if not srcfile.exists():
                it.status, it.note = "failed", "not in the local copy"
                return
            if same_file(srcfile, dest) or (o.link != "copy" and o.place(it.path, dest)):
                ok = not it.sha256 or sha256_file(srcfile) == it.sha256
                self._bump(total_bar, it.size or 0)
                it.status, it.note = ("done", "") if ok else ("failed", "checksum mismatch in the local copy")
                return
        part = dest.with_name(dest.name + ".part")
        for attempt in range(3):
            have = part.stat().st_size if part.exists() else 0
            h = hashlib.sha256()
            if have:
                with open(part, "rb") as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
            blocks, restarted, close = o.blocks(it.path, have)
            try:
                if restarted:
                    self._bump(total_bar, -have)
                    have, h = 0, hashlib.sha256()
                with open(part, "ab" if have else "wb") as f:
                    for block in blocks:
                        if self.stop.is_set():
                            raise KeyboardInterrupt
                        f.write(block)
                        h.update(block)
                        self._bump(total_bar, len(block))
            except KeyboardInterrupt:
                raise
            except Exception as e:   # connection dropped mid-file: keep the .part and resume
                it.note = f"transfer interrupted ({type(e).__name__}), resumed"
                continue
            finally:
                close()
            size = part.stat().st_size
            if (it.sha256 and h.hexdigest() != it.sha256) or (it.size is not None and size != it.size):
                self._bump(total_bar, -size)
                part.unlink(missing_ok=True)
                it.note = "incomplete or checksum mismatch, retried"
                continue
            part.replace(dest)
            it.status, it.note = "done", ""
            return
        it.status = "failed"
        it.note = "checksum mismatch in the local copy" if isinstance(o, LocalOrigin) else \
            "could not download a complete, matching copy"

    def fetch_table(self, it: Item) -> None:
        o = self.origins[it.source]
        dest = local_path(self.root, it)
        with bar(total=it.size, unit="B", unit_scale=True, desc=f"  {it.source}: {Path(it.path).name}") as b:
            for attempt in range(3):
                read, close = o.open_raw(it.path)
                try:
                    res = filter_stream(read, it.path, dest, self.ids, b, self.stop)
                except NoSubjectColumn:
                    close()
                    b.close()
                    if (it.size or 0) <= WHOLE_TABLE:
                        it.kind = "file"   # no patient column (e.g. a data dictionary): keep it whole
                        self.fetch_file(it, _NullBar())
                    else:
                        it.status, it.note = "skipped", "large table without a subject_id column"
                    return
                except (FileNotFoundError, NotFound, KeyboardInterrupt):
                    raise
                except Exception as e:   # connection dropped mid-table: start that table over
                    if isinstance(e, PhysioNetError) and not str(e).startswith(("giving up", "HTTP 5")):
                        raise
                    it.note = f"attempt {attempt + 1} failed ({type(e).__name__})"
                    b.reset()
                    continue
                finally:
                    close()
                it.rows, it.scanned, it.subjects = res["rows"], res["scanned"], res["subjects"]
                it.out_sha256, it.out_size = res["out_sha256"], res["out_size"]
                it.status, it.note = "done", ""
                b.set_postfix_str(f"kept {it.rows:,} of {it.scanned:,} rows, {len(it.subjects)} patients")
                return
        it.status = "failed"

    def _safe(self, fn, it, *a):
        try:
            fn(it, *a)
        except KeyboardInterrupt:
            raise
        except NotFound:
            it.status, it.note = "failed", "not found on the server"
        except FileNotFoundError:
            it.status, it.note = "failed", "not in the local copy"
        except PhysioNetError as e:
            it.status, it.note = "failed", str(e)

    def run(self, files: list[Item], tables: list[Item]) -> None:
        try:
            if files:
                with bar(total=sum(i.size or 0 for i in files), unit="B", unit_scale=True,
                         desc="  files") as tb, ThreadPoolExecutor(self.jobs) as ex:
                    futs = [ex.submit(self._safe, self.fetch_file, it, tb) for it in files]
                    for n, f in enumerate(as_completed(futs), 1):
                        f.result()
                        tb.set_postfix_str(f"{n:,}/{len(files):,} files")
                        if n % 50 == 0:
                            self.man.save()
            for it in tables:
                self._safe(self.fetch_table, it)
                self.man.save()
        except KeyboardInterrupt:
            self.stop.set()
            self.man.save()
            print("\nInterrupted. Progress is saved; run the same command again to resume.")
            raise SystemExit(130)
        finally:
            self.man.save()


def summarize_plan(root: Path, sources: list[Source], items: list[Item], origins: dict):
    files, tables, store = [], [], 0
    print(f"\n  {'source':<18}{'from':<11}{'files':>8}{'present':>9}{'to get':>8}{'tables':>8}{'to store':>12}  streamed")
    for src in sources:
        its = [i for i in items if i.source == src.key and i.status != "skipped"]
        f = [i for i in its if i.kind == "file"]
        t = [i for i in its if i.kind == "table"]
        f_todo = [i for i in f if not on_disk(root, i)]
        t_todo = [i for i in t if not on_disk(root, i)]
        todo = {id(i) for i in f_todo + t_todo}
        for i in f + t:
            if id(i) not in todo:
                i.status = "done"
        o = origins[src.key]
        linked = isinstance(o, LocalOrigin) and o.link != "copy"
        nbytes = 0 if linked else sum(i.size or 0 for i in f_todo)
        files += f_todo
        tables += t_todo
        store += nbytes
        frm = "local" if isinstance(o, LocalOrigin) else "PhysioNet"
        print(f"  {src.key:<18}{frm:<11}{len(f):>8,}{len(f) - len(f_todo):>9,}{len(f_todo):>8,}{len(t):>8,}"
              f"{human(nbytes):>12}  {human(sum(i.size or 0 for i in t_todo)) if t_todo else '-'}")
    free = shutil.disk_usage(root).free
    print(f"\n  to store: {human(store)} in {len(files):,} files + {len(tables)} filtered tables "
          f"(tables keep only demo-patient rows); free space: {human(free)}")
    return files, tables, store, free
