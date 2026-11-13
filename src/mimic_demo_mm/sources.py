"""The PhysioNet projects that make up the multimodal demo.

mode
  full    every file of the project (small, open demo releases)
  demo    the demo patients' files under files/pXX/pXXXXXXXX/ plus every
          top-level table filtered to the demo patients
  tables  only the top-level tables (anything outside files/), filtered to the
          demo patients

Most projects keep per-patient files under files/pXX/pXXXXXXXX/. A project that
differs sets ``files_dir`` and ``group_digits`` (the waveform database uses
waves/pXXX/pXXXXXXXX/).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    slug: str
    version: str
    access: str          # "open" | "credentialed"
    mode: str            # "full" | "demo" | "tables"
    title: str
    default: bool = True
    files_dir: str = "files"   # folder holding the per-patient folders
    group_digits: int = 2      # files/p10/p10000032/ -> 2; waves/p100/p100xxxxx/ -> 3

    def in_files(self, path: str) -> bool:
        return path.startswith(self.files_dir + "/")

    def patient_dir(self, subject: str) -> str:
        return f"{self.files_dir}/p{subject[:self.group_digits]}/p{subject}/"

    @property
    def rel(self) -> str:
        return f"{self.slug}/{self.version}"

    @property
    def credentialed(self) -> bool:
        return self.access == "credentialed"


SOURCES: list[Source] = [
    Source("mimic-iv-demo", "mimic-iv-demo", "2.2", "open", "full",
           "MIMIC-IV clinical database demo: structured, categorical and numeric events"),
    Source("mimic-iv-ed-demo", "mimic-iv-ed-demo", "2.2", "open", "full",
           "MIMIC-IV-ED demo: emergency department stays, triage, vitals"),
    Source("mimic-iv-ecg-demo", "mimic-iv-ecg-demo", "0.1", "open", "full",
           "MIMIC-IV-ECG demo: 12-lead ECG waveforms"),
    Source("mimic-iv-ecg", "mimic-iv-ecg", "1.0", "open", "tables",
           "MIMIC-IV-ECG: machine measurements and ECG report text (tables only)"),
    Source("mimic4wdb", "mimic4wdb", "0.1.0", "open", "demo",
           "MIMIC-IV Waveform Database: ICU bedside-monitor waveforms and numerics",
           files_dir="waves", group_digits=3),
    Source("mimic-cxr-jpg", "mimic-cxr-jpg", "2.1.0", "credentialed", "demo",
           "MIMIC-CXR-JPG: chest X-ray images, metadata, labels"),
    Source("mimic-iv-echo", "mimic-iv-echo", "1.0.1", "credentialed", "demo",
           "MIMIC-IV-ECHO: echocardiogram DICOMs and measurements"),
    Source("mimic-iv-note", "mimic-iv-note", "2.2", "credentialed", "tables",
           "MIMIC-IV-Note: discharge summaries and radiology reports"),
    Source("mimic-cxr", "mimic-cxr", "2.0.0", "credentialed", "demo",
           "MIMIC-CXR (DICOM): chest X-ray DICOMs and report text", default=False),
]

BY_KEY = {s.key: s for s in SOURCES}
DEMO_IDS = ("mimic-iv-demo/2.2", "demo_subject_id.csv")


def select(only=None, skip=None, include=None) -> list[Source]:
    unknown = [k for k in (only or []) + (skip or []) + (include or []) if k not in BY_KEY]
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(unknown)}. See: mimic-demo-mm sources")
    if only:
        chosen = [BY_KEY[k] for k in only]
    else:
        chosen = [s for s in SOURCES if s.default or s.key in (include or [])]
    return [s for s in chosen if s.key not in (skip or [])]
