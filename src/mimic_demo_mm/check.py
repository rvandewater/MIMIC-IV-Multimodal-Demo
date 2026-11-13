"""Final file check: is everything there, complete and uncorrupted?

Every file is compared with its PhysioNet checksum (SHA256SUMS.txt); every
filtered table with the checksum recorded when it was written. Results are
printed as counts only; the paths of problem files go to a local report."""
from __future__ import annotations

import gzip
import csv
from collections import Counter, defaultdict
from pathlib import Path

from .download import bar, human, local_path
from .listing import subject_of
from .manifest import Item, Manifest
from .sources import BY_KEY
from .tables import sha256_file

OK, MISSING, INCOMPLETE, CORRUPT, SKIPPED = "ok", "missing", "incomplete", "corrupt", "skipped"
REPORT = "mimic-demo-mm.check-report.txt"


def verify_item(root: Path, it: Item, quick: bool) -> str:
    if it.status == "skipped":
        return SKIPPED
    p = local_path(root, it)
    if not p.exists():
        return INCOMPLETE if p.with_name(p.name + ".part").exists() else MISSING
    size = p.stat().st_size
    if it.kind == "table":
        if it.out_sha256 is None:
            return MISSING
        if size != it.out_size:
            return CORRUPT
        return OK if quick or sha256_file(p) == it.out_sha256 else CORRUPT
    if it.size is not None and size != it.size:
        return INCOMPLETE if size < it.size else CORRUPT
    if not quick and it.sha256 and sha256_file(p) != it.sha256:
        return CORRUPT
    return OK


def verify(root: Path, man: Manifest, keys: list[str] | None = None, quick: bool = False) -> dict[tuple, str]:
    items = [i for i in man.items.values() if keys is None or i.source in keys]
    total = sum((i.out_size if i.kind == "table" else i.size) or 0 for i in items if i.status != "skipped")
    res = {}
    with bar(total=total, unit="B", unit_scale=True, desc="  checking files" + (" (sizes only)" if quick else ""),
             leave=False) as b:
        for it in items:
            res[it.key] = verify_item(root, it, quick)
            b.update((it.out_size if it.kind == "table" else it.size) or 0)
    return res


def _ed_subjects(root: Path) -> set[str]:
    p = root / "mimic-iv-ed-demo/2.2/ed/edstays.csv.gz"
    if not p.exists():
        return set()
    with gzip.open(p, "rt", newline="") as f:
        r = csv.DictReader(f)
        return {row["subject_id"] for row in r}


def coverage(root: Path, man: Manifest, res: dict) -> list[tuple[str, set[str] | None, str]]:
    """-> [(label, demo patients with it or None for all of them, modality group)]."""
    ok = [man.items[k] for k, v in res.items() if v == OK]
    present = set(man.sources)

    def files_of(src, exts):
        return {subject_of(i.path) for i in ok if i.source == src and BY_KEY[src].in_files(i.path)
                and i.path.lower().endswith(exts)} - {None}

    def tables_of(src, name):
        s = set()
        for i in ok:
            if i.source == src and i.kind == "table" and name in Path(i.path).name:
                s.update(i.subjects)
        return s

    rows = []
    if "mimic-iv-demo" in present:
        rows.append(("structured, categorical and numeric events (EHR)", None, "EHR"))
    if "mimic-iv-ed-demo" in present:
        rows.append(("emergency department stays", _ed_subjects(root), "ED stay"))
    for key, label, kind, arg, group in (
            ("mimic-iv-ecg-demo", "ECG waveforms", "files", (".hea",), "ECG"),
            ("mimic-iv-ecg", "ECG machine reports (text)", "tables", "machine_measurements", "ECG"),
            ("mimic4wdb", "ICU bedside-monitor waveforms", "files", (".hea",), "ICU waveforms"),
            ("mimic-cxr-jpg", "chest X-ray images (JPG)", "files", (".jpg",), "Chest X-ray"),
            ("mimic-cxr", "chest X-ray DICOMs", "files", (".dcm",), "Chest X-ray"),
            ("mimic-iv-echo", "echo DICOMs", "files", (".dcm",), "Echo"),
            ("mimic-iv-echo", "echo measurements", "tables", "measurement", "Echo"),
            ("mimic-iv-note", "discharge summaries", "tables", "discharge.csv", "Notes"),
            ("mimic-iv-note", "radiology reports", "tables", "radiology.csv", "Notes")):
        if key in present:
            rows.append((label, files_of(key, arg) if kind == "files" else tables_of(key, arg), group))
    return rows


def report(root: Path, man: Manifest, res: dict, quick: bool) -> bool:
    per = defaultdict(Counter)
    sizes = Counter()
    for (src, _), st in res.items():
        per[src][st] += 1
        it = man.items[(src, _)]
        if st == OK:
            sizes[src] += (it.out_size if it.kind == "table" else it.size) or 0
    print(f"\n== File check{' (sizes only)' if quick else ' (checksums)'} ==")
    print(f"  {'source':<18}{'ok':>8}{'missing':>9}{'partial':>9}{'corrupt':>9}{'skipped':>9}{'size':>11}  status")
    complete = True
    for key in man.sources:
        c = per.get(key, Counter())
        bad = c[MISSING] + c[INCOMPLETE] + c[CORRUPT]
        complete &= bad == 0 and c[OK] > 0
        status = "complete" if bad == 0 and c[OK] else ("EMPTY" if not c[OK] and not bad else "INCOMPLETE")
        print(f"  {key:<18}{c[OK]:>8,}{c[MISSING]:>9,}{c[INCOMPLETE]:>9,}{c[CORRUPT]:>9,}{c[SKIPPED]:>9,}"
              f"{human(sizes[key]):>11}  {status}")
    n_demo = man.demo_subjects or 0
    print(f"\n== Demo patients per modality (of {n_demo}) ==")
    rows = coverage(root, man, res)
    for label, s, _ in rows:
        print(f"  {label:<48}{n_demo if s is None else len(s):>5}")
    optional = ("emergency department stays", "ICU bedside-monitor waveforms")   # few patients have these
    sets = [s for label, s, _ in rows if s is not None and label not in optional]
    if len(sets) > 1:
        label = "with all of the above (ED, waveforms optional)"
        print(f"  {label:<48}{len(set.intersection(*sets)):>5}")

    bad = [(k, v) for k, v in res.items() if v in (MISSING, INCOMPLETE, CORRUPT)]
    rep = root / REPORT
    if bad:
        with open(rep, "w") as f:
            for (src, path), st in sorted(bad):
                note = man.items[(src, path)].note
                f.write(f"{st}\t{BY_KEY[src].rel}/{path}\t{note}\n")
        print(f"\nINCOMPLETE: {len(bad):,} problem file(s), listed in {rep} (local file).")
        print("Run `mimic-demo-mm check --fix` (or the same download command again) to fetch them.")
    else:
        rep.unlink(missing_ok=True)
        print("\nCOMPLETE: every expected file is present and matches its checksum." if not quick else
              "\nCOMPLETE (sizes only): run `mimic-demo-mm check` for full checksum verification.")
    return complete and not bad
