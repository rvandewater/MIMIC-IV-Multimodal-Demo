# mimic-demo-mm

Assemble a **local multimodal MIMIC-IV demo**: the 100 patients of the open
MIMIC-IV demo, gathered across every MIMIC module. One command downloads (or
extracts from local copies), shows progress, and finishes with a file check
that verifies every file against its checksum.

| source | access | what is fetched |
|---|---|---|
| `mimic-iv-demo` 2.2 | open | everything: structured, categorical and numeric EHR events |
| `mimic-iv-ed-demo` 2.2 | open | everything: ED stays, triage, vitals |
| `mimic-iv-ecg-demo` 0.1 | open | everything: 12-lead ECG waveforms |
| `mimic-iv-ecg` 1.0 | open | tables only (machine measurements, ECG report text), demo patients' rows |
| `mimic4wdb` 0.1.0 | open | demo patients' ICU bedside-monitor waveforms and numerics (WFDB records under `waves/`) |
| `mimic-cxr-jpg` 2.1.0 | credentialed | demo patients' chest X-ray JPGs; metadata and label tables filtered to them |
| `mimic-iv-echo` 1.0.1 | credentialed | demo patients' echo DICOMs; record list and measurements filtered to them |
| `mimic-iv-note` 2.2 | credentialed | discharge summaries and radiology reports (plus detail tables), demo patients' rows |
| `mimic-cxr` 2.0.0 | credentialed | optional (`--include mimic-cxr`): chest X-ray DICOMs and per-study report text |

The waveform database is an early pre-release with about 200 patients, so only
a handful of the 100 demo patients (4 in 0.1.0, about 330 MB) have waveforms.
Its top-level `RECORDS` file is copied as is, so it still lists every record in
the release, including ones that aren't downloaded.

## What the demo patients have

How many of the demo patients have each modality, and which modalities occur
together. Each column of the co-occurrence plot counts the patients with exactly
that set of modalities.

<!-- modality-overview:start -->
_Not generated yet: run `uv run --extra figure mimic-demo-mm figure --readme README.md`
after a complete download (see [Overview figure](#overview-figure))._
<!-- modality-overview:end -->

## Access

For the credentialed sources you need a credentialed PhysioNet account, and you
must have signed each project's data use agreement.

## Run

With [uv](https://docs.astral.sh/uv/), no installation step is needed:

```bash
uv run mimic-demo-mm download --user YOUR_PHYSIONET_USERNAME
```

This asks for your password once. You can instead set `PHYSIONET_USER` and
`PHYSIONET_PASSWORD`. The output goes to `./mimic-demo-multimodal`; change it with `--out DIR`.

The run goes through four stages:

1. **Listing.** It reads each project's `SHA256SUMS.txt`, which gives exact
   paths and checksums. Lists with hundreds of thousands of files are filtered
   to the demo patients as they stream in. A project without that file falls
   back to its folder listings.
2. **Plan.** For each source it shows how many files there are, how many are
   already on disk, and how many still need fetching. It also shows the size
   to store and your free space, then asks before starting. `--yes` skips the
   question; `--plan` stops here.
3. **Download.**
   - **Files** download in parallel (`--jobs`, default 4) with one overall
     progress bar. Each file is checked against its checksum.
   - **Interrupted files** resume where they stopped. Ctrl-C is safe: run the
     same command again to continue.
   - **Tables** are streamed and filtered on the fly, keeping only demo-patient
     rows. Each table gets its own progress bar, and the full tables never
     touch your disk.
4. **File check.** Every expected file is verified against its checksum.
   - **Per-source result:** a table of ok, missing, partial and corrupt counts,
     with COMPLETE or INCOMPLETE for each source.
   - **Coverage:** how many demo patients have each modality.

### Local copies instead of downloading

If you already have a full project on disk, extract the demo subset from it:

```bash
uv run mimic-demo-mm download \
    --local mimic-iv-note=/data/mimic-iv-note/2.2 \
    --local mimic-cxr-jpg=/data/mimic-cxr-jpg/2.1.0 \
    --link hardlink          # or symlink; default is copy
```

- **Where checksums come from:** the local `SHA256SUMS.txt` is used when
  present. Otherwise the tool reads the folders directly, and only the demo
  patients' parts of `files/`.
- **No password needed** when every credentialed source is local.
- **Saving space:** `--link hardlink` or `--link symlink` avoids storing
  images twice. A hard link falls back to a copy when the two folders are on
  different disks.

### Choosing sources

```bash
uv run mimic-demo-mm sources                                  # list them
uv run mimic-demo-mm download --only mimic-iv-demo mimic-cxr-jpg
uv run mimic-demo-mm download --skip mimic-iv-echo
uv run mimic-demo-mm download --include mimic-cxr             # add the DICOM release
```

### Checking later

```bash
uv run mimic-demo-mm check              # verify every checksum
uv run mimic-demo-mm check --quick      # sizes only
uv run mimic-demo-mm check --fix        # re-fetch anything missing, partial or corrupt
```

The exit code is 0 when complete, 1 when incomplete, and 2 on an error such as
a wrong password or an unsigned agreement. Paths of problem files go to
`mimic-demo-mm.check-report.txt` next to the data.

### Overview figure

```bash
uv run --extra figure mimic-demo-mm figure                       # writes docs/modality-overview-{light,dark}.svg
uv run --extra figure mimic-demo-mm figure --readme README.md    # and refreshes the overview above
```

It counts the files that pass a size check, so run it after a complete
download. Modalities are grouped:
- **ECG:** waveforms or machine reports
- **Chest X-ray:** JPG or DICOM
- **Echo:** DICOMs or measurements
- **Notes:** discharge summaries or radiology reports

EHR is left out of the co-occurrence plot because every demo patient has it.
The figure and table show patient counts only, never IDs.

**Small counts are hidden.** A count below 5 is shown as `<5`, with no bar.
Combinations with fewer than 5 patients are merged into one "other" column.
Change the threshold with `--min-count N`; `--min-count 1` shows everything.

## Output layout

```
mimic-demo-multimodal/
  mimic-iv-demo/2.2/...                        (PhysioNet's own layout)
  mimic4wdb/0.1.0/waves/p100/p100xxxxx/<record>/<record>.hea ...
  mimic-cxr-jpg/2.1.0/files/p10/p10000032/s.../....jpg
  mimic-cxr-jpg/2.1.0/mimic-cxr-2.0.0-metadata.csv.gz   (demo patients' rows only)
  mimic-iv-echo/1.0.1/files/...  echo-record-list.csv ...
  mimic-iv-note/2.2/note/discharge.csv.gz ...           (demo patients' rows only)
  mimic-demo-mm.manifest.json                  every expected item, checksums, row counts
```

**How tables are kept:**
- **Same name as on PhysioNet, demo patients' rows only.** This holds for
  every table outside `files/` in the `demo` and `tables` sources.
- **Kept whole:** tables without a `subject_id` column that are 200 MB or
  smaller, such as data dictionaries and the echo study list.
- **Skipped:** other top-level files over 10 MB, such as `IMAGE_FILENAMES`.

## Privacy and data use

- The console shows **counts only**: never IDs, paths of individual patients, or note text.
- Everything under the output folder, apart from the open demo sources, is **credentialed data**.
  - **Keep it on approved machines.** The PhysioNet Credentialed Health Data
    Use Agreement applies to the filtered tables and the manifest too.
  - **Don't upload it to online AI services.** See PhysioNet's guidance:
    https://physionet.org/news/post/llm-responsible-use/
- Cite each project as its PhysioNet page asks.

## Development

```bash
uv run --extra test pytest -q
```

The tests run end to end against `tests/mock_physionet.py`, a local stand-in
for PhysioNet's file server with synthetic data. It reproduces:
- credentialed-project passwords, including a rejected password and an account
  with no signed agreement;
- resumable downloads, size checks and folder listings;
- a project without checksums;
- a file whose connection drops halfway.
