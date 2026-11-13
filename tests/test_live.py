"""Live end-to-end test against the real PhysioNet, using about 2 MB of bandwidth.

It takes one to two minutes, almost all of it spent reading the waveform
database's checksum list, which PhysioNet serves slowly.

Off by default. Run it with:

    MULTI_MIMIC_LIVE=1 uv run --extra test pytest tests/test_live.py -v

What it covers, and what it costs:
- MIMIC-IV-ED demo: a real download through physionet.download (7 files, about
  120 KB), checksum verification, the file check, and a second run that fetches
  nothing.
- MIMIC-IV Waveform Database: a plan for one demo patient (--subjects), which
  reads the 1.7 MB checksum list and the sizes of that patient's 30 files without
  downloading them.
- The overview figure, drawn from the ED download (no network).
- MIMIC-IV-Note, only with a PhysioNet sign-in (PHYSIONET_TOKEN, PHYSIONET_USER
  and PHYSIONET_PASSWORD, or `physionet login`): a plan that lists the files,
  checks their sizes and reads each table's header (a few hundred KB).

Output is checked for patient IDs: the console must show counts only.
"""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout

import pytest

from multi_mimic.cli import main
from multi_mimic.manifest import NAME

pytestmark = pytest.mark.skipif(os.environ.get("MULTI_MIMIC_LIVE") != "1",
                                reason="live PhysioNet test: set MULTI_MIMIC_LIVE=1")

WAVEFORM_PATIENT = "10039708"   # the demo patient with the least waveform data (30 files, 25 MB)


def run(*args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(args))
    return code, buf.getvalue()


def items(out, source):
    return [i for i in json.loads((out / NAME).read_text())["items"] if i["source"] == source]


def signed_in() -> bool:
    if os.environ.get("PHYSIONET_TOKEN"):
        return True
    if (os.environ.get("PHYSIONET_USER") or os.environ.get("PHYSIONET_USERNAME")) and \
            os.environ.get("PHYSIONET_PASSWORD"):
        return True
    from physionet.auth import load_saved_login
    return load_saved_login() is not None


@pytest.fixture(autouse=True)
def real_physionet(monkeypatch):
    monkeypatch.delenv("PHYSIONET_BASE_URL", raising=False)


@pytest.fixture(scope="module")
def ed(tmp_path_factory):
    os.environ.pop("PHYSIONET_BASE_URL", None)
    out = tmp_path_factory.mktemp("live-ed")
    code, text = run("download", "--out", str(out), "--yes", "--only", "mimic-iv-ed-demo")
    return out, code, text


def test_open_download_through_physionet_package(ed):
    out, code, text = ed
    assert code == 0, text
    assert "COMPLETE: every expected file is present and matches its checksum" in text
    its = items(out, "mimic-iv-ed-demo")
    assert len(its) >= 6 and all(i["status"] == "done" and i["sha256"] for i in its)
    folder = out / "mimic-iv-ed-demo-2.2"                    # physionet.download's <slug>-<version>/
    assert (folder / "ed/edstays.csv.gz").stat().st_size > 0
    stored = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    assert stored < 1_000_000                                 # the whole download stays small


def test_rerun_fetches_nothing_and_check_passes(ed):
    out, _, _ = ed
    code, text = run("download", "--out", str(out), "--yes", "--only", "mimic-iv-ed-demo")
    assert code == 0 and "to store: 0 B in 0 files + 0 filtered tables" in text
    code, text = run("check", "--out", str(out))
    assert code == 0 and "COMPLETE" in text


def test_plan_one_waveform_patient_downloads_nothing(tmp_path):
    out = tmp_path / "plan"
    code, text = run("download", "--out", str(out), "--plan", "--only", "mimic4wdb",
                     "--subjects", WAVEFORM_PATIENT)
    assert code == 0, text
    its = items(out, "mimic4wdb")
    waves = [i for i in its if i["path"].startswith("waves/")]
    assert len(waves) == 30 and all(i["sha256"] and i["size"] for i in waves)
    assert 20e6 < sum(i["size"] for i in waves) < 30e6
    assert not (out / "mimic4wdb-0.1.0/waves").exists()      # --plan fetches nothing
    assert WAVEFORM_PATIENT not in text                       # counts only, even for a patient given on the command line


def test_figure_from_live_download(ed, tmp_path):
    pytest.importorskip("matplotlib")
    out, _, _ = ed
    code, text = run("figure", "--out", str(out), "--to", str(tmp_path / "docs"))
    assert code == 0, text
    assert (tmp_path / "docs/modality-overview-light.svg").exists()
    assert "ED stay" in text


@pytest.mark.skipif(not signed_in(), reason="needs a PhysioNet sign-in with access to MIMIC-IV-Note")
def test_credentialed_plan_reads_only_headers(tmp_path):
    out = tmp_path / "note"
    code, text = run("download", "--out", str(out), "--plan", "--only", "mimic-iv-note")
    assert code == 0, text
    tables = {i["path"]: i for i in items(out, "mimic-iv-note") if i["path"].endswith(".csv.gz")}
    assert tables.get("note/discharge.csv.gz", {}).get("kind") == "table"   # has subject_id: filtered later
    assert not any(p.is_file() and p.suffix == ".gz" for p in out.rglob("*"))   # nothing stored
