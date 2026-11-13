"""Modality overview figure: how many demo patients have each modality, and which
modalities occur together (an UpSet plot).

Built from a finished download (the files that pass the check). The figure,
the table and the console show patient counts only, never IDs. Counts below
``min_count`` (default 5) are shown as "<5", and combinations with fewer patients
are merged into one "other" column, so no small group is visible.

Writes two SVGs, one for light and one for dark backgrounds, and can update the
overview section of a README between the markers below.
"""
from __future__ import annotations

import os
import re
import time
from collections import Counter
from pathlib import Path

from .check import OK, coverage, verify
from .manifest import Manifest
from .sources import BY_KEY, DEMO_IDS

START, END = "<!-- modality-overview:start -->", "<!-- modality-overview:end -->"
# Matrix rows, top to bottom. EHR is left out: every demo patient has it.
GROUPS = ["Notes", "ECG", "ED stay", "Chest X-ray", "Echo", "ICU waveforms"]
MAX_COLUMNS = 16
MIN_COUNT = 5
OTHER = None   # the merged column of small combinations

THEMES = {   # single series: one hue, neutral ink (validated against both surfaces)
    "light": dict(bar="#2a78d6", ink="#0b0b0b", ink2="#52514e", grid="#e4e3df", off="#d9d8d4"),
    "dark": dict(bar="#3987e5", ink="#f0efec", ink2="#c3c2b7", grid="#33332f", off="#45453f"),
}


# ---------------------------------------------------------------- data
def modality_sets(root: Path, man: Manifest, res: dict) -> tuple[set[str], dict[str, set[str]], bool]:
    """-> (all demo patients, {group: patients with it}, whether EHR covers everyone)."""
    p = root / BY_KEY["mimic-iv-demo"].rel / DEMO_IDS
    universe = set(re.findall(r"\b\d{8}\b", p.read_text())) if p.exists() else set()
    groups: dict[str, set[str]] = {}
    has_ehr = False
    for _, s, group in coverage(root, man, res):
        if s is None:
            has_ehr = True
            continue
        groups.setdefault(group, set()).update(s)
    universe |= set().union(*groups.values()) if groups else set()
    return universe, {g: groups[g] for g in GROUPS if g in groups}, has_ehr


def intersections(universe: set[str], groups: dict[str, set[str]]) -> list[tuple[tuple[str, ...], int]]:
    """Exclusive combinations: each patient counted once, under exactly the modalities they have."""
    combos = Counter(tuple(g for g in groups if pid in groups[g]) for pid in universe)
    return sorted(combos.items(), key=lambda kv: (-kv[1], len(kv[0]), [GROUPS.index(g) for g in kv[0]]))


def fmt(k: int, min_count: int) -> str:
    return str(k) if k == 0 or k >= min_count else f"<{min_count}"


def columns(universe, groups, min_count: int) -> list[tuple[tuple[str, ...] | None, int]]:
    """Combinations with at least ``min_count`` patients (at most MAX_COLUMNS), then
    one OTHER column holding everyone else."""
    combos = intersections(universe, groups)
    big = [(c, k) for c, k in combos if k >= min_count][:MAX_COLUMNS]
    other = sum(k for _, k in combos) - sum(k for _, k in big)
    return big + ([(OTHER, other)] if other else [])


# ---------------------------------------------------------------- drawing
def _rounded_bar(ax, x0, y0, w, h, color, horizontal, radius_px=4):
    """A bar with a 4px rounded data end and a square baseline."""
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath

    if (w if horizontal else h) <= 0:
        return
    inv = ax.transData.inverted()
    (ox, oy), (px, py) = inv.transform([(0, 0), (radius_px, radius_px)])
    rx, ry = abs(px - ox), abs(py - oy)
    M, L, C, Z = MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CLOSEPOLY
    x1, y1 = x0 + w, y0 + h
    if horizontal:   # grows right from x0; round the right end
        rx, ry = min(rx, w), min(ry, h / 2)
        v = [(x0, y0), (x1 - rx, y0), (x1, y0), (x1, y0 + ry), (x1, y1 - ry), (x1, y1),
             (x1 - rx, y1), (x0, y1), (x0, y0)]
        codes = [M, L, C, C, L, C, C, L, Z]
    else:            # grows up from y0; round the top end
        rx, ry = min(rx, w / 2), min(ry, h)
        v = [(x0, y0), (x1, y0), (x1, y1 - ry), (x1, y1), (x1 - rx, y1), (x0 + rx, y1), (x0, y1),
             (x0, y1 - ry), (x0, y0)]
        codes = [M, L, L, C, C, L, C, C, Z]
    ax.add_patch(PathPatch(MPath(v, codes), facecolor=color, edgecolor="none", lw=0))


def _style(ax, t):
    ax.set_facecolor("none")
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=t["ink2"], labelcolor=t["ink2"], length=0, labelsize=8.5)


def draw(universe, groups, has_ehr, theme: str, dest: Path, min_count: int = MIN_COUNT) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = THEMES[theme]
    plt.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "mimic-demo-mm",
                         "font.family": ["Helvetica", "Arial", "DejaVu Sans", "sans-serif"]})
    n = len(universe)
    names = list(groups)
    shown = columns(universe, groups, min_count)
    ncol, nrow = len(shown), len(names)
    visible = lambda k: k == 0 or k >= min_count   # a suppressed count gets no bar: its length would tell

    fig = plt.figure(figsize=(1.9 + 0.36 * max(ncol, 6) + 0.6, 1.5 + 0.3 * nrow + 1.6))
    fig.patch.set_alpha(0)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.9, 0.36 * max(ncol, 6)], height_ratios=[1.6, 0.3 * nrow],
                          wspace=0.05, hspace=0.06, left=0.17, right=0.98, top=0.80, bottom=0.09)
    ax_cov = fig.add_subplot(gs[1, 0])
    ax_mat = fig.add_subplot(gs[1, 1], sharey=ax_cov)
    ax_int = fig.add_subplot(gs[0, 1], sharex=ax_mat)
    for ax in (ax_cov, ax_mat, ax_int):
        _style(ax, t)

    # fix every limit before drawing: the rounded ends are sized in pixels from them
    ys = list(range(nrow))[::-1]
    top = max([c for _, c in shown if visible(c)] + [min_count, 1])
    ax_cov.set_xlim(0, n * 1.35 or 1)
    ax_cov.set_ylim(-0.6, nrow - 0.4)
    ax_int.set_xlim(-0.6, max(ncol, 6) - 0.4)
    ax_int.set_ylim(0, top * 1.22)
    for ax in (ax_cov, ax_mat, ax_int):
        ax.set_autoscale_on(False)
    fig.canvas.draw()

    # coverage: patients with >= 1 record of each modality, one row per modality
    for y, g in zip(ys, names):
        k = len(groups[g])
        if visible(k):
            _rounded_bar(ax_cov, 0, y - 0.28, k, 0.56, t["bar"], horizontal=True)
        ax_cov.text((k if visible(k) else 0) + n * 0.03, y, fmt(k, min_count), va="center", ha="left",
                    fontsize=8.5, color=t["ink"])
    ax_cov.set_yticks(ys, names, fontsize=9, color=t["ink"])
    ax_cov.set_xticks([])
    ax_cov.set_title(f"Patients with ≥ 1\n(of {n})", fontsize=8.5, color=t["ink2"], loc="left", pad=4)

    # intersection sizes (exclusive)
    ax_int.yaxis.grid(True, color=t["grid"], lw=0.8)
    ax_int.set_axisbelow(True)
    ax_int.tick_params(axis="x", labelbottom=False)
    ax_int.set_ylabel("Patients", fontsize=8.5, color=t["ink2"])
    for x, (combo, c) in enumerate(shown):
        if visible(c):
            _rounded_bar(ax_int, x - 0.3, 0, 0.6, c, t["bar"], horizontal=False)
        ax_int.text(x, (c if visible(c) else 0) + top * 0.03, fmt(c, min_count), ha="center", va="bottom",
                    fontsize=8.5, color=t["ink"])

    # membership matrix
    ax_mat.tick_params(axis="y", labelleft=False)
    ax_mat.set_xticks([])
    for x, (combo, _) in enumerate(shown):
        if combo is OTHER:
            ax_mat.text(x, (nrow - 1) / 2, "other", ha="center", va="center", rotation=90,
                        fontsize=8, color=t["ink2"])
            continue
        on = [y for y, g in zip(ys, names) if g in combo]
        ax_mat.scatter([x] * nrow, ys, s=42, color=t["off"], zorder=1, linewidths=0)
        if len(on) > 1:
            ax_mat.plot([x, x], [min(on), max(on)], color=t["ink"], lw=2, zorder=2, solid_capstyle="round")
        if on:
            ax_mat.scatter([x] * len(on), on, s=42, color=t["ink"], zorder=3, linewidths=0)
        else:
            ax_mat.text(x, -0.75, "EHR\nonly" if has_ehr else "none", ha="center", va="top",
                        fontsize=7.5, color=t["ink2"], clip_on=False)

    title = "Modality coverage and co-occurrence"
    sub = (f"{n} MIMIC-IV demo patients" + (", all with EHR data." if has_ehr else ".")
           + "\nEach column counts the patients with exactly that set of modalities (each patient once)."
           + (f"\nCounts below {min_count} are shown as <{min_count}; combinations with fewer than {min_count} "
              "patients are merged into \"other\"." if min_count > 1 else ""))
    fig.text(0.02, 0.965, title, fontsize=11.5, fontweight="bold", color=t["ink"], va="top")
    fig.text(0.02, 0.918, sub, fontsize=8, color=t["ink2"], va="top", linespacing=1.4)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, transparent=True, dpi=200, bbox_inches="tight", pad_inches=0.15,   # never clip labels
                **({"metadata": {"Date": None}} if dest.suffix == ".svg" else {}))
    plt.close(fig)


# ---------------------------------------------------------------- README section
def markdown(universe, groups, has_ehr, light: str, dark: str, min_count: int = MIN_COUNT) -> str:
    n = len(universe)
    combos = intersections(universe, groups)
    alt = "; ".join(f"{g} {fmt(len(s), min_count)}" for g, s in groups.items())
    lines = [START, "",
             "<picture>",
             f'  <source media="(prefers-color-scheme: dark)" srcset="{dark}">',
             f'  <img alt="Demo patients per modality (of {n}): {alt}" src="{light}">',
             "</picture>", "",
             f"| modality | demo patients (of {n}) |", "|---|---:|"]
    if has_ehr:
        lines.append(f"| EHR (hosp, ICU) | {n} |")
    lines += [f"| {g} | {fmt(len(s), min_count)} |" for g, s in groups.items()]
    every = sum(c for combo, c in combos if len(combo) == len(groups))
    lines += ["", f"{fmt(every, min_count)} of {n} patients have every modality above. "
              + (f"Counts below {min_count} are shown as <{min_count}. " if min_count > 1 else "") +
              f"Generated by `mimic-demo-mm figure` on {time.strftime('%Y-%m-%d')} from a complete download "
              "(counts only).", "", END]
    return "\n".join(lines)


def update_readme(readme: Path, block: str) -> bool:
    text = readme.read_text()
    if START not in text or END not in text:
        return False
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    readme.write_text(head + block + tail)
    return True


def run(root: Path, to: Path, readme: Path | None, min_count: int = MIN_COUNT) -> int:
    from .download import require_current_layout
    require_current_layout(root)
    man = Manifest.load(root)
    if not man.items:
        print(f"No manifest in {root}. Run `mimic-demo-mm download` first (or pass --out).")
        return 2
    res = verify(root, man, None, quick=True)
    bad = sum(v not in (OK, "skipped") for v in res.values())
    universe, groups, has_ehr = modality_sets(root, man, res)
    if not groups:
        print("No modality data found on disk.")
        return 1
    if bad:
        print(f"  ! {bad:,} file(s) missing or incomplete: the figure counts only what is on disk. "
              "Run `mimic-demo-mm check --fix` first for a complete picture.")
    paths = {th: to / f"modality-overview-{th}.svg" for th in THEMES}
    for th, p in paths.items():
        draw(universe, groups, has_ehr, th, p, min_count)
    print(f"  wrote {paths['light']} and {paths['dark']}")
    print(f"\n  {'modality':<16}{'patients':>9}  (of {len(universe)})")
    for g, s in groups.items():
        print(f"  {g:<16}{fmt(len(s), min_count):>9}")
    if readme is not None:
        base = readme.resolve().parent
        rel = {th: os.path.relpath(p.resolve(), base).replace(os.sep, "/") for th, p in paths.items()}
        block = markdown(universe, groups, has_ehr, rel["light"], rel["dark"], min_count)
        if update_readme(readme, block):
            print(f"  updated the overview in {readme}")
        else:
            print(f"  x {readme} has no {START} ... {END} markers; nothing changed there")
            return 1
    return 0
