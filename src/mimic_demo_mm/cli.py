"""mimic-demo-mm: assemble a local multimodal MIMIC-IV demo.

  mimic-demo-mm sources                         list the datasets
  mimic-demo-mm download --user NAME            download everything (asks for the password)
  mimic-demo-mm download --local mimic-iv-note=/data/mimic-iv-note/2.2 ...
                                                take subsets from local copies instead
  mimic-demo-mm check [--fix]                   verify every file; re-fetch broken ones
  mimic-demo-mm figure [--readme README.md]     draw the modality coverage / co-occurrence overview
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from . import __version__
from .check import report, verify
from .download import Runner, demo_ids, make_origins, plan, summarize_plan
from .http import Client, PhysioNetError
from .manifest import Manifest
from .sources import BY_KEY, SOURCES, select


def _local_map(pairs: list[str] | None, man: Manifest | None = None) -> dict[str, Path]:
    out = {}
    if man is not None:  # remember local copies used by earlier runs (for check --fix)
        out.update({k: Path(v["local_dir"]) for k, v in man.sources.items() if v.get("local_dir")})
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--local expects SOURCE=FOLDER, got '{p}'")
        k, d = p.split("=", 1)
        if k not in BY_KEY:
            raise SystemExit(f"--local: unknown source '{k}'. See: mimic-demo-mm sources")
        out[k] = Path(d)
    return out


def _client(sources, local, user) -> Client:
    remote_cred = [s.key for s in sources if s.credentialed and s.key not in local]
    if not remote_cred:
        return Client()
    user = user or os.environ.get("PHYSIONET_USER") or input("PhysioNet username: ").strip()
    pw = os.environ.get("PHYSIONET_PASSWORD") or getpass.getpass(f"PhysioNet password for {user}: ")
    return Client(user, pw)


def cmd_sources(a) -> int:
    print(f"{'source':<19}{'access':<14}{'what is fetched':<26}{'default':<9}description")
    what = {"full": "everything", "demo": "demo patients' files+rows", "tables": "demo patients' rows"}
    for s in SOURCES:
        print(f"{s.key:<19}{s.access:<14}{what[s.mode]:<26}{'yes' if s.default else 'no':<9}{s.title}")
    print("\nPhysioNet project: https://physionet.org/content/<source>/<version>/  "
          "(versions: " + ", ".join(f"{s.key} {s.version}" for s in SOURCES) + ")")
    return 0


def _download(root: Path, sources, local, link, user, jobs, yes, plan_only, quick) -> int:
    root.mkdir(parents=True, exist_ok=True)
    client = _client(sources, local, user)
    origins = make_origins(sources, client, local, link, root)
    man = Manifest.load(root)
    ids = demo_ids(client, root, local)
    man.demo_subjects = len(ids)
    print(f"mimic-demo-mm {__version__}: {len(ids)} demo patients -> {root}\n\nListing files")
    items = plan(origins, sources, ids, man, jobs)
    files, tables, store, free = summarize_plan(root, sources, items, origins)
    man.save()
    if plan_only:
        return 0
    if store > free:
        print("  x not enough free space: choose fewer sources (--only/--skip), use --link with --local, "
              "or --out on a bigger disk")
        return 2
    if (files or tables) and not yes:
        if input("\n  Start? [Y/n] ").strip().lower() in ("n", "no"):
            print("  Nothing downloaded. Re-run any time.")
            return 0
    if files or tables:
        print()
        Runner(origins, root, man, ids, jobs).run(files, tables)
    res = verify(root, man, [s.key for s in sources], quick)
    return 0 if report(root, man, res, quick) else 1


def cmd_download(a) -> int:
    sources = select(a.only, a.skip, a.include)
    local = _local_map(a.local)
    return _download(Path(a.out).resolve(), sources, local, a.link, a.user, a.jobs, a.yes, a.plan, a.quick_check)


def cmd_check(a) -> int:
    root = Path(a.out).resolve()
    man = Manifest.load(root)
    if not man.items:
        print(f"No manifest in {root}. Run `mimic-demo-mm download` first (or pass --out).")
        return 2
    res = verify(root, man, None, a.quick)
    ok = report(root, man, res, a.quick)
    if ok or not a.fix:
        return 0 if ok else 1
    bad = {k for k, v in res.items() if v in ("missing", "incomplete", "corrupt")}
    for k in bad:
        it = man.items[k]
        it.status = "pending"
        p = root / BY_KEY[it.source].rel / it.path
        if res[k] == "corrupt" and p.exists():
            p.unlink()
    print(f"\nFixing {len(bad):,} file(s)...")
    sources = [BY_KEY[k] for k in man.sources if k in BY_KEY]
    local = _local_map(a.local, man)
    return _download(root, sources, local, a.link, a.user, a.jobs, True, False, False)


def cmd_figure(a) -> int:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("x the figure needs matplotlib: run `uv run --extra figure mimic-demo-mm figure ...`")
        return 2
    from .figure import run
    if a.min_count < 1:
        print("x --min-count must be at least 1")
        return 2
    return run(Path(a.out).resolve(), Path(a.to), Path(a.readme) if a.readme else None, a.min_count)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mimic-demo-mm", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sources", help="list the datasets").set_defaults(fn=cmd_sources)

    def common(p):
        p.add_argument("--out", default="mimic-demo-multimodal", help="output folder (default: %(default)s)")
        p.add_argument("--user", help="PhysioNet username (or env PHYSIONET_USER; password: env PHYSIONET_PASSWORD or prompt)")
        p.add_argument("--local", action="append", metavar="SOURCE=FOLDER",
                       help="take this source from a local copy instead of PhysioNet (repeatable), "
                            "e.g. mimic-iv-note=/data/mimic-iv-note/2.2")
        p.add_argument("--link", choices=["copy", "hardlink", "symlink"], default="copy",
                       help="for --local sources: copy files (default), or hard-link / symlink to save space")
        p.add_argument("--jobs", type=int, default=4, help="parallel downloads (default: %(default)s)")

    d = sub.add_parser("download", help="download / extract everything, then check it")
    common(d)
    d.add_argument("--only", nargs="+", metavar="SOURCE", help="only these sources")
    d.add_argument("--skip", nargs="+", metavar="SOURCE", help="leave these sources out")
    d.add_argument("--include", nargs="+", metavar="SOURCE", help="add optional sources (e.g. mimic-cxr)")
    d.add_argument("--yes", "-y", action="store_true", help="don't ask before starting")
    d.add_argument("--plan", action="store_true", help="only list what would be fetched and how big it is")
    d.add_argument("--quick-check", action="store_true", help="final check by size only (skip checksums)")
    d.set_defaults(fn=cmd_download)

    c = sub.add_parser("check", help="verify every file against its checksum")
    common(c)
    c.add_argument("--quick", action="store_true", help="sizes only (skip checksums)")
    c.add_argument("--fix", action="store_true", help="re-fetch missing, partial or corrupt files")
    c.set_defaults(fn=cmd_check)

    g = sub.add_parser("figure", help="draw the modality coverage and co-occurrence overview (counts only)")
    g.add_argument("--out", default="mimic-demo-multimodal", help="data folder (default: %(default)s)")
    g.add_argument("--to", default="docs", help="folder for the SVGs (default: %(default)s)")
    g.add_argument("--readme", help="also update the overview section of this README")
    g.add_argument("--min-count", type=int, default=5,
                   help="show smaller counts as '<N' and merge smaller combinations into 'other' "
                        "(default: %(default)s; 1 shows everything)")
    g.set_defaults(fn=cmd_figure)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except PhysioNetError as e:
        print(f"x {e}")
        return 2
    except SystemExit as e:
        if isinstance(e.code, str):   # a readable error message from deeper down
            print(e.code)
            return 2
        raise
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
