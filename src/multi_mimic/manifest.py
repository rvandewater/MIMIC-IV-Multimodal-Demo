"""The manifest: every expected item and what was fetched. Stored next to the
data as multi-mimic.manifest.json; ``check`` verifies against it."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

NAME = "multi-mimic.manifest.json"
LEGACY_NAME = "mimic-demo-mm.manifest.json"   # the tool's pre-release name


def manifest_file(root: Path) -> Path | None:
    """The manifest in ``root``, under its current or its pre-0.2 name, or None."""
    for name in (NAME, LEGACY_NAME):
        if (Path(root) / name).exists():
            return Path(root) / name
    return None


@dataclass
class Item:
    source: str
    path: str                     # relative to <out>/<project>/<version>/
    kind: str                     # "file" (exact copy) | "table" (filtered to demo patients)
    sha256: str | None = None     # PhysioNet checksum of the original file
    size: int | None = None       # size on the server
    status: str = "pending"       # pending | done | skipped | failed
    out_sha256: str | None = None  # tables: checksum of the filtered output we wrote
    out_size: int | None = None
    rows: int | None = None
    scanned: int | None = None
    subjects: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.path)


@dataclass
class Manifest:
    root: Path
    items: dict[tuple[str, str], Item] = field(default_factory=dict)
    sources: dict[str, dict] = field(default_factory=dict)
    demo_subjects: int = 0

    @property
    def file(self) -> Path:
        return self.root / NAME

    @classmethod
    def load(cls, root: Path) -> "Manifest":
        m = cls(Path(root))
        f = manifest_file(m.root)
        if f is not None:
            d = json.loads(f.read_text())
            m.sources = d.get("sources", {})
            m.demo_subjects = d.get("demo_subjects", 0)
            for it in d.get("items", []):
                item = Item(**it)
                m.items[item.key] = item
        return m

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "tool": "multi-mimic", "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "demo_subjects": self.demo_subjects, "sources": self.sources,
            "items": [asdict(i) for i in self.items.values()],
        }, indent=1))
        tmp.replace(self.file)
        (self.root / LEGACY_NAME).unlink(missing_ok=True)   # superseded by the file just written

    def merge(self, fresh: list[Item]) -> list[Item]:
        """Add newly planned items, keeping what earlier runs recorded."""
        out = []
        for it in fresh:
            old = self.items.get(it.key)
            if old is not None:
                old.sha256 = it.sha256 or old.sha256
                old.size = it.size if it.size is not None else old.size
                if old.kind != it.kind and old.status != "done":
                    old.kind = it.kind
                it = old
            self.items[it.key] = it
            out.append(it)
        return out

    def for_source(self, key: str) -> list[Item]:
        return [i for i in self.items.values() if i.source == key]
