"""A small stand-in for PhysioNet's file server, with synthetic data.

Behaves like the real server where it matters: Basic auth on credentialed
projects (401 bad password, 403 no data use agreement), HEAD with
Content-Length, Range requests (206 / 416), directory listings,
SHA256SUMS.txt in every project except one (to exercise the crawl fallback),
and the API endpoint that lists a project's versions (used by physionet.download).
One file drops the connection halfway on its first request (resume test).
"""
from __future__ import annotations

import base64
import csv
import json
import gzip
import hashlib
import io
import os
import random
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CREDENTIALED = ("mimic-cxr-jpg", "mimic-iv-echo", "mimic-iv-note", "mimic-cxr")
USER, PASSWORD = "tester", "s3cret"
NO_DUA_USER = "nodua"
DEMO = [str(10000000 + 37 * i) for i in range(20)]
OTHER = [str(18000000 + 11 * i) for i in range(30)]
FLAKY = "files/p10/p10000037/s50000001/img0.jpg"   # first GET is cut off halfway


def _w(path: Path, data: bytes | str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)


def _csv(rows, header, gz=False) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    b = buf.getvalue().encode()
    return gzip.compress(b, mtime=0) if gz else b


def _sums(root: Path):
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()} {p.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")


def build(root: Path) -> dict:
    rng = random.Random(0)
    who = {"cxr": DEMO[:12], "echo": DEMO[2:6], "ecg": DEMO[:16], "ed": DEMO[:9], "wdb": DEMO[3:6]}
    # --- open demo releases
    d = root / "mimic-iv-demo/2.2"
    _w(d / "demo_subject_id.csv", _csv([[s] for s in DEMO], ["subject_id"]))
    _w(d / "hosp/patients.csv.gz", _csv([[s, "F", 60] for s in DEMO], ["subject_id", "gender", "anchor_age"], gz=True))
    _w(d / "LICENSE.txt", "ODbL\n")
    _sums(d)
    d = root / "mimic-iv-ed-demo/2.2"
    _w(d / "ed/edstays.csv.gz", _csv([[s, 30000000 + i] for i, s in enumerate(who["ed"])], ["subject_id", "stay_id"], gz=True))
    _sums(d)
    d = root / "mimic-iv-ecg-demo/0.1"
    rl = []
    for i, s in enumerate(who["ecg"]):
        st = 40000000 + i
        for ext in ("hea", "dat"):
            _w(d / f"files/p{s[:4]}/p{s}/s{st}/{st}.{ext}", os.urandom(3000))
        rl.append([s, st, f"files/p{s[:4]}/p{s}/s{st}/{st}"])
    _w(d / "record_list.csv", _csv(rl, ["subject_id", "study_id", "path"]))
    _sums(d)
    # --- open full ECG release: tables only should be taken
    d = root / "mimic-iv-ecg/1.0"
    mm = [[s, 41000000 + i, "Sinus rhythm, normal ECG", "Borderline \"T\" waves\nconsider ischemia"]
          for i, s in enumerate(DEMO[:10] + OTHER)]
    _w(d / "machine_measurements.csv", _csv(mm, ["subject_id", "study_id", "report_0", "report_1"]))
    _w(d / "machine_measurements_data_dictionary.csv", _csv([["report_0", "text"]], ["variable", "description"]))
    _w(d / f"files/p1800/p{OTHER[0]}/s1/1.dat", os.urandom(5000))   # must NOT be fetched
    _sums(d)
    # --- open waveform database: waves/pXXX/pXXXXXXXX/<record>/, numerics as .csv.gz (files, not tables)
    d = root / "mimic4wdb/0.1.0"
    recs = []
    for i, s in enumerate(who["wdb"] + OTHER[:4]):
        pdir = f"waves/p{s[:3]}/p{s}/"
        rec = str(80000000 + i)
        _w(d / pdir / rec / f"{rec}.hea", f"{rec}/3 2 62.4725 1000\n")
        for seg in range(2):
            _w(d / pdir / rec / f"{rec}_{seg:04d}.dat", os.urandom(rng.randint(5_000, 20_000)))
        _w(d / pdir / rec / f"{rec}n.csv.gz", _csv([[0, 72], [1, 74]], ["time", "HR"], gz=True))
        _w(d / pdir / "RECORDS", f"{rec}/\n")
        recs.append(pdir)
    _w(d / "RECORDS", "\n".join(recs) + "\n")
    _w(d / "LICENSE.txt", "ODbL\n")
    _sums(d)
    # --- credentialed: CXR-JPG
    d = root / "mimic-cxr-jpg/2.1.0"
    meta = []
    for s in who["cxr"] + OTHER[:5]:
        for k in range(2):
            st = 50000000 + int(s[-3:]) * 10 + k
            for v in range(2):
                did = f"img{v}" if s == "10000037" and k == 0 and v == 0 else f"d{s}{k}{v}"
                _w(d / f"files/p{s[:2]}/p{s}/s{st}/{did}.jpg", os.urandom(rng.randint(20_000, 90_000)))
                meta.append([did, s, st, "PA" if v == 0 else "LATERAL", 21500101, 120000.0])
    # make the flaky file's study id match FLAKY
    _w(d / FLAKY, os.urandom(400_000))
    meta.append(["img0", "10000037", 50000001, "PA", 21500101, 120000.0])
    _w(d / "mimic-cxr-2.0.0-metadata.csv.gz",
       _csv(meta, ["dicom_id", "subject_id", "study_id", "ViewPosition", "StudyDate", "StudyTime"], gz=True))
    _w(d / "mimic-cxr-2.0.0-chexpert.csv.gz",
       _csv([[m[1], m[2], "1.0"] for m in meta], ["subject_id", "study_id", "Edema"], gz=True))
    _w(d / "mimic-cxr-2.1.0-test-set-labeled.csv", _csv([[1, "0"]], ["study_id", "Edema"]))
    _w(d / "IMAGE_FILENAMES", b"x" * (11 * 2 ** 20))     # big non-table file: should be skipped
    _sums(d)
    # --- credentialed: ECHO, *no* SHA256SUMS (crawl fallback), measurement table under another name
    d = root / "mimic-iv-echo/1.0.1"
    rec = []
    for s in who["echo"] + OTHER[:3]:
        st = 90000000 + int(s[-3:])
        for v in range(3):
            p = f"files/p{s[:2]}/p{s}/s{st}/{st}_{v:04d}.dcm"
            _w(d / p, os.urandom(rng.randint(50_000, 150_000)))
            rec.append([p, "2150-01-01 10:00:00", st, s])
    _w(d / "echo-record-list.csv", _csv(rec, ["dicom_filepath", "acquisition_datetime", "study_id", "subject_id"]))
    _w(d / "echo_structured_measurements.csv",
       _csv([[s, i, "LVEF, biplane", 55] for i, s in enumerate(DEMO[:8] + OTHER)],
            ["subject_id", "measurement_id", "measurement_description", "result"]))
    _w(d / "echo-study-list.csv", _csv([[1, 2, "", ""]], ["study_id", "measurement_id", "note_id", "note_charttime"]))
    # --- credentialed: notes (long, multi-line, quoted text)
    d = root / "mimic-iv-note/2.2"
    long_text = ("Name: ___\nHistory, with commas and \"quotes\".\n" + "word " * 40000).strip()
    dis = [[f"{s}-DS-{i}", s, 20000000 + i, "DS", 1, "2150-01-02 00:00:00", long_text]
           for i, s in enumerate(DEMO[:15] + OTHER)]
    rad = [[f"{s}-RR-{i}", s, "", "RR", 1, "2150-01-02 00:00:00", "Chest radiograph.\nNo acute process."]
           for i, s in enumerate(DEMO + OTHER * 3)]
    hdr = ["note_id", "subject_id", "hadm_id", "note_type", "note_seq", "charttime", "text"]
    _w(d / "note/discharge.csv.gz", _csv(dis, hdr, gz=True))
    _w(d / "note/radiology.csv.gz", _csv(rad, hdr, gz=True))
    _w(d / "note/discharge_detail.csv.gz",
       _csv([[r[0], r[1], "author", "___"] for r in dis], ["note_id", "subject_id", "field_name", "field_value"], gz=True))
    _sums(d)
    return {"who": who, "demo_notes_discharge": 15, "demo_rad": len(DEMO), "demo_ecg_reports": 10, "demo_echo_meas": 8}


class Handler(SimpleHTTPRequestHandler):
    flaky_done: set = set()

    def log_message(self, *a):
        pass

    def _auth_ok(self, rel: str) -> bool:
        proj = rel.split("/", 1)[0]
        if proj not in CREDENTIALED:
            return True
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            self._deny(401)
            return False
        user, _, pw = base64.b64decode(h[6:]).decode().partition(":")
        if user == NO_DUA_USER and pw == PASSWORD:
            self._deny(403)
            return False
        if (user, pw) != (USER, PASSWORD):
            self._deny(401)
            return False
        return True

    def _deny(self, code):
        self.send_response(code)
        if code == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="PhysioNet"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _api(self, head: bool):
        """GET /api/v1/projects/<slug>/versions/ (physionet.download looks up versions here)."""
        m = re.fullmatch(r"/api/v1/projects/([^/]+)/versions/", self.path.split("?")[0])
        proj = Path(self.directory) / m.group(1) if m else None
        if proj is None or not proj.is_dir():
            return self._deny(404)
        body = json.dumps([{"slug": proj.name, "title": proj.name, "version": v.name, "abstract": "",
                            "citation": ""} for v in sorted(proj.iterdir()) if v.is_dir()]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _serve(self, head: bool):
        if self.path.startswith("/api/v1/"):
            return self._api(head)
        if not self.path.startswith("/files/"):
            return self._deny(404)
        rel = self.path[len("/files/"):].split("?")[0]
        if not self._auth_ok(rel):
            return
        p = Path(self.directory) / rel
        if p.is_dir():
            body = "".join(f'<a href="{c.name}{"/" if c.is_dir() else ""}">{c.name}</a>\n'
                           for c in sorted(p.iterdir())).encode()
            body = b'<a href="../">../</a>\n' + body
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return
        if not p.is_file():
            return self._deny(404)
        data = p.read_bytes()
        start, code = 0, 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            start = int(rng[6:].split("-")[0] or 0)
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        body = data[start:]
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        self.end_headers()
        if head:
            return
        if rel.endswith(FLAKY) and rel not in Handler.flaky_done and start == 0:
            Handler.flaky_done.add(rel)
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            self.connection.shutdown(2)     # drop the connection mid-transfer
            return
        self.wfile.write(body)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)


def serve(root: Path) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
