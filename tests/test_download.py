"""End-to-end tests against a mock PhysioNet (tests/mock_physionet.py)."""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import mock_physionet as mp
from mimic_demo_mm.cli import main
from mimic_demo_mm.manifest import NAME


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("physionet")
    facts = mp.build(root)
    srv, url = mp.serve(root)
    yield root, url, facts
    srv.shutdown()


@pytest.fixture(autouse=True)
def env(server, monkeypatch):
    _, url, _ = server
    monkeypatch.setenv("PHYSIONET_BASE_URL", url)
    monkeypatch.delenv("PHYSIONET_TOKEN", raising=False)
    monkeypatch.delenv("PHYSIONET_USERNAME", raising=False)
    monkeypatch.setenv("PHYSIONET_USER", mp.USER)
    monkeypatch.setenv("PHYSIONET_PASSWORD", mp.PASSWORD)


def run(*args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(args))
    return code, buf.getvalue()


def rows(path: Path) -> list[dict]:
    op = gzip.open if path.name.endswith(".gz") else open
    with op(path, "rt", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def full(server, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    mp.Handler.flaky_done.clear()
    os.environ.pop("PHYSIONET_TOKEN", None)
    os.environ.update(PHYSIONET_BASE_URL=server[1], PHYSIONET_USER=mp.USER, PHYSIONET_PASSWORD=mp.PASSWORD)
    code, text = run("download", "--out", str(out), "--yes", "--jobs", "3")
    return out, code, text


def test_download_completes_and_check_passes(full):
    out, code, text = full
    assert code == 0, text
    assert "COMPLETE: every expected file is present and matches its checksum" in text
    for src in ("mimic-iv-demo", "mimic-iv-ed-demo", "mimic-iv-ecg-demo", "mimic-iv-ecg", "mimic4wdb",
                "mimic-cxr-jpg", "mimic-iv-echo", "mimic-iv-note"):
        assert f"{src}" in text


def test_only_demo_patients_files_and_rows(full, server):
    out, _, _ = full
    _, _, facts = server
    demo = set(mp.DEMO)
    jpgs = list((out / "mimic-cxr-jpg-2.1.0/files").rglob("*.jpg"))
    assert jpgs and all(p.parent.parent.name[1:] in demo for p in jpgs)
    dcm = list((out / "mimic-iv-echo-1.0.1/files").rglob("*.dcm"))
    assert len(dcm) == 3 * len(facts["who"]["echo"])                     # crawl fallback, demo patients only
    assert not (out / "mimic-iv-ecg-1.0/files").exists()                 # tables-only source: no waveforms
    assert not (out / "mimic-cxr-jpg-2.1.0/IMAGE_FILENAMES").exists()    # big non-table file skipped
    d = rows(out / "mimic-iv-note-2.2/note/discharge.csv.gz")
    assert len(d) == facts["demo_notes_discharge"] and {r["subject_id"] for r in d} <= demo
    assert d[0]["text"].startswith("Name: ___\nHistory, with commas and \"quotes\".")   # long multi-line text intact
    assert len(d[0]["text"]) > 150_000
    r = rows(out / "mimic-iv-note-2.2/note/radiology.csv.gz")
    assert len(r) == facts["demo_rad"]
    mm = rows(out / "mimic-iv-ecg-1.0/machine_measurements.csv")
    assert len(mm) == facts["demo_ecg_reports"] and "\n" in mm[0]["report_1"]
    assert len(rows(out / "mimic-iv-echo-1.0.1/echo_structured_measurements.csv")) == facts["demo_echo_meas"]
    # waveform database: demo patients' records under waves/p100/..., numerics copied byte for byte
    wdb = out / "mimic4wdb-0.1.0"
    heas = list((wdb / "waves").rglob("*.hea"))
    assert len(heas) == len(facts["who"]["wdb"])
    assert all(p.parent.parent.name[1:] in demo and p.parents[2].name == p.parent.parent.name[:4] for p in heas)
    nums = list((wdb / "waves").rglob("*n.csv.gz"))
    assert len(nums) == len(facts["who"]["wdb"])
    assert all(n.read_bytes() == (server[0] / "mimic4wdb/0.1.0" / n.relative_to(wdb)).read_bytes() for n in nums)
    assert (wdb / "RECORDS").exists() and (wdb / "LICENSE.txt").exists()
    # tables without subject_id are kept whole
    assert (out / "mimic-iv-echo-1.0.1/echo-study-list.csv").exists()
    assert (out / "mimic-iv-ecg-1.0/machine_measurements_data_dictionary.csv").exists()


def test_flaky_file_was_resumed(full):
    out, _, _ = full
    assert (out / "mimic-cxr-jpg-2.1.0" / mp.FLAKY).stat().st_size == 400_000
    assert mp.Handler.flaky_done                                          # the cut-off really happened


def test_coverage_counts(full, server):
    _, _, text = full
    who = server[2]["who"]
    lines = {l.strip().rsplit(None, 1)[0]: int(l.strip().rsplit(None, 1)[1])
             for l in text.splitlines() if l.startswith("  ") and l.strip()[-1:].isdigit() and "%" not in l}
    assert lines["chest X-ray images (JPG)"] == len(who["cxr"])
    assert lines["echo DICOMs"] == len(who["echo"])
    assert lines["ECG waveforms"] == len(who["ecg"])
    assert lines["ICU bedside-monitor waveforms"] == len(who["wdb"])
    assert lines["emergency department stays"] == len(who["ed"])
    assert lines["discharge summaries"] == 15


def test_figure_and_readme_overview(full, tmp_path):
    pytest.importorskip("matplotlib")
    out, _, _ = full
    readme = tmp_path / "README.md"
    readme.write_text("# x\n\n<!-- modality-overview:start -->\nold\n<!-- modality-overview:end -->\n\nafter\n")
    code, text = run("figure", "--out", str(out), "--to", str(tmp_path / "docs"), "--readme", str(readme))
    assert code == 0, text
    svgs = [tmp_path / "docs" / f"modality-overview-{t}.svg" for t in ("light", "dark")]
    assert all(p.exists() and p.read_text().lstrip().startswith("<?xml") for p in svgs)
    md = readme.read_text()
    assert "old" not in md and md.endswith("after\n")
    assert 'srcset="docs/modality-overview-dark.svg"' in md
    for line in ("| EHR (hosp, ICU) | 20 |", "| Notes | 20 |", "| ECG | 16 |", "| ED stay | 9 |",
                 "| Chest X-ray | 12 |", "| Echo | 8 |", "| ICU waveforms | <5 |"):   # 3 is below 5
        assert line in md
    assert "<5 of 20 patients have every modality above" in md
    assert "Counts below 5 are shown as <5" in md and "<5" in text
    blob = md + text + "".join(p.read_text() for p in svgs)
    assert not any(s in blob for s in mp.DEMO + mp.OTHER)
    assert ">other<" in svgs[0].read_text()                                # small combinations merged
    # --min-count 1 shows every count
    code, text = run("figure", "--out", str(out), "--to", str(tmp_path / "docs"), "--readme", str(readme),
                     "--min-count", "1")
    md = readme.read_text()
    assert code == 0 and "| ICU waveforms | 3 |" in md and "3 of 20 patients have every modality" in md
    assert "<1" not in md + text


def test_rerun_fetches_nothing(full):
    out, _, _ = full
    code, text = run("download", "--out", str(out), "--yes")
    assert code == 0
    assert "to store: 0 B in 0 files + 0 filtered tables" in text


def test_output_contains_no_ids_or_text(full):
    _, _, text = full
    assert not any(s in text for s in mp.DEMO + mp.OTHER)
    assert "History, with commas" not in text and "Sinus rhythm" not in text


def test_check_detects_and_fixes(full):
    out, _, _ = full
    jpgs = sorted((out / "mimic-cxr-jpg-2.1.0/files").rglob("*.jpg"))
    jpgs[0].write_bytes(b"corrupted")                     # wrong size
    b = bytearray(jpgs[1].read_bytes()); b[100] ^= 0xFF; jpgs[1].write_bytes(bytes(b))   # same size, bad checksum
    jpgs[2].unlink()                                      # missing
    note = out / "mimic-iv-note-2.2/note/radiology.csv.gz"
    note.write_bytes(note.read_bytes()[:-10])            # truncated table
    code, text = run("check", "--out", str(out))
    assert code == 1 and "INCOMPLETE: 4 problem file(s)" in text
    assert (out / "mimic-demo-mm.check-report.txt").exists()
    code, text = run("check", "--out", str(out), "--fix")
    assert code == 0, text
    code, text = run("check", "--out", str(out))
    assert code == 0 and "COMPLETE" in text


def test_quick_check_misses_same_size_corruption_but_full_check_finds_it(full):
    out, _, _ = full
    jpg = sorted((out / "mimic-cxr-jpg-2.1.0/files").rglob("*.jpg"))[3]
    b = bytearray(jpg.read_bytes()); b[0] ^= 0xFF; jpg.write_bytes(bytes(b))
    assert run("check", "--out", str(out), "--quick")[0] == 0
    assert run("check", "--out", str(out))[0] == 1
    assert run("check", "--out", str(out), "--fix")[0] == 0


def test_bad_password_and_missing_agreement(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSIONET_PASSWORD", "wrong")
    code, text = run("download", "--out", str(tmp_path / "a"), "--only", "mimic-iv-note", "--yes")
    assert code == 2 and "mimic-iv-note" in text and "rejected the sign-in" in text
    monkeypatch.setenv("PHYSIONET_USER", mp.NO_DUA_USER)
    monkeypatch.setenv("PHYSIONET_PASSWORD", mp.PASSWORD)
    code, text = run("download", "--out", str(tmp_path / "b"), "--only", "mimic-cxr-jpg", "--yes")
    assert code == 2 and "data use agreement" in text


def test_local_copies_need_no_password_and_can_hardlink(server, tmp_path, monkeypatch):
    root, _, facts = server
    monkeypatch.setenv("PHYSIONET_USER", "")
    monkeypatch.setenv("PHYSIONET_PASSWORD", "")
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("should not ask for credentials"))
    out = tmp_path / "out"
    code, text = run("download", "--out", str(out), "--yes", "--link", "hardlink",
                     "--only", "mimic-iv-demo", "mimic-cxr-jpg", "mimic-iv-echo", "mimic-iv-note",
                     "--local", f"mimic-cxr-jpg={root / 'mimic-cxr-jpg'}",          # project folder: version found
                     "--local", f"mimic-iv-echo={root / 'mimic-iv-echo/1.0.1'}",    # no SHA256SUMS: folder walk
                     "--local", f"mimic-iv-note={root / 'mimic-iv-note/2.2'}")
    assert code == 0, text
    assert "local SHA256SUMS.txt" in text and "local folder" in text
    jpg = next((out / "mimic-cxr-jpg-2.1.0/files").rglob("*.jpg"))
    src = root / "mimic-cxr-jpg/2.1.0" / jpg.relative_to(out / "mimic-cxr-jpg-2.1.0")
    assert os.stat(jpg).st_ino == os.stat(src).st_ino                    # hard link, no extra space
    assert len(list((out / "mimic-iv-echo-1.0.1/files").rglob("*.dcm"))) == 3 * len(facts["who"]["echo"])
    assert len(rows(out / "mimic-iv-note-2.2/note/discharge.csv.gz")) == facts["demo_notes_discharge"]
    man = json.loads((out / NAME).read_text())
    assert man["sources"]["mimic-iv-note"]["local_dir"].endswith("mimic-iv-note/2.2")


def test_local_must_not_be_the_output_folder(server, tmp_path):
    root, _, _ = server
    code, text = run("download", "--out", str(root), "--yes", "--only", "mimic-iv-note",
                     "--local", f"mimic-iv-note={root / 'mimic-iv-note/2.2'}")
    assert code != 0 or "output folder itself" in text


def test_local_waveform_copy_without_checksums(server, tmp_path):
    root, _, facts = server
    local = tmp_path / "mimic4wdb/0.1.0"
    shutil.copytree(root / "mimic4wdb/0.1.0", local)
    (local / "SHA256SUMS.txt").unlink()                                   # force the folder walk
    out = tmp_path / "out"
    code, text = run("download", "--out", str(out), "--yes", "--only", "mimic-iv-demo", "mimic4wdb",
                     "--local", f"mimic4wdb={local}")
    assert code == 0, text
    heas = list((out / "mimic4wdb-0.1.0/waves").rglob("*.hea"))
    assert len(heas) == len(facts["who"]["wdb"])


def test_only_reports_the_sources_it_checked(tmp_path):
    out = tmp_path / "o"
    assert run("download", "--out", str(out), "--yes", "--only", "mimic-iv-demo", "mimic4wdb")[0] == 0
    code, text = run("download", "--out", str(out), "--yes", "--only", "mimic-iv-ed-demo")
    assert code == 0 and "EMPTY" not in text and "mimic4wdb" not in text.split("== File check")[1]
    code, text = run("check", "--out", str(out))           # check covers every source in the manifest
    assert code == 0 and "mimic4wdb" in text


def test_old_layout_is_only_renamed_on_request(full):
    out, _, _ = full
    new, old = out / "mimic-iv-ed-demo-2.2", out / "mimic-iv-ed-demo/2.2"
    old.parent.mkdir()
    new.rename(old)                                        # as mimic-demo-mm 0.1 left it
    for cmd in (["download", "--yes"], ["check"], ["figure", "--to", str(out / "docs")]):
        code, text = run(*cmd, "--out", str(out))
        assert code == 2 and "mimic-demo-mm migrate" in text and old.is_dir() and not new.exists()
    code, text = run("migrate", "--out", str(out), "--dry-run")
    assert code == 0 and "would move mimic-iv-ed-demo/2.2/ -> mimic-iv-ed-demo-2.2/" in text and old.is_dir()
    code, text = run("migrate", "--out", str(out))
    assert code == 0 and new.is_dir() and not old.parent.exists()
    code, text = run("download", "--out", str(out), "--yes")
    assert code == 0 and "to store: 0 B in 0 files + 0 filtered tables" in text


def test_migrate_refuses_folders_it_did_not_make(server):
    root, _, _ = server                                    # the mock server's own <slug>/<version> folders
    code, text = run("migrate", "--out", str(root))
    assert code == 2 and "not a folder this tool made" in text and (root / "mimic4wdb/0.1.0").is_dir()


def test_plan_only_downloads_nothing(tmp_path):
    out = tmp_path / "p"
    code, text = run("download", "--out", str(out), "--plan", "--only", "mimic-cxr-jpg")
    assert code == 0 and "to store:" in text
    assert not (out / "mimic-cxr-jpg-2.1.0/files").exists()
