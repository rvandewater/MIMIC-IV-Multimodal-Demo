# mimic-demo-mm

Assemble a **local multimodal MIMIC-IV demo**: the 100 patients of the open
MIMIC-IV demo, gathered across every MIMIC module. One command downloads (or
extracts from local copies), shows progress, and finishes with a file check
that verifies every file against its checksum.

Downloads go through the official [`physionet`](https://github.com/MIT-LCP/physionet)
package (sign-in, resume, retries, checksums). See
[How and where data is saved](#how-and-where-data-is-saved) for exactly what
ends up on your disk.

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
must have signed each project's data use agreement. Python 3.10 or later.

## Run

With [uv](https://docs.astral.sh/uv/), no installation step is needed:

```bash
uv run physionet login                 # once: sign in through your browser, no password stored
uv run mimic-demo-mm download
```

The output goes to `./mimic-demo-multimodal`; change it with `--out DIR`.

**Signing in.** Only the credentialed sources need it. The first of these that
is set is used:
1. `--user NAME` (or `PHYSIONET_USER` / `PHYSIONET_USERNAME`), with the
   password from `PHYSIONET_PASSWORD` or asked once;
2. `PHYSIONET_TOKEN`, a personal access token from PhysioNet (Settings > Tokens),
   for unattended runs;
3. the sign-in saved by `physionet login`;
4. otherwise the tool asks for a username and password.

Credentials are only sent to physionet.org, and this tool stores none of them.
`physionet login` keeps its sign-in in `~/.config/physionet/credentials.json`
(the `physionet` package manages that file).

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
   - **Files** are downloaded by `physionet.download`, one source at a time,
     with one overall progress bar. Each file is checked against PhysioNet's
     checksum. Open projects that are on the AWS open-data mirror come from
     there (`--source auto`, the default); `--source physionet` always uses
     physionet.org.
   - **Interrupted files** resume where they stopped. Ctrl-C is safe: run the
     same command again to continue.
   - **Tables** are streamed and filtered on the fly, keeping only demo-patient
     rows. Each table gets its own progress bar, and the full tables never
     touch your disk. The `physionet` package can only download whole files,
     so this part, and projects without a `SHA256SUMS.txt`, use the tool's own
     code with the package's sign-in.
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
uv run mimic-demo-mm download --subjects 10000032 10039708     # only these demo patients
```

`--subjects` limits the per-patient files and filtered tables to the patients
you name, for a quick test or a partial copy. Sources fetched whole (the open
demos) stay whole.

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

## How and where data is saved

Everything goes into one folder (`--out`, default `./mimic-demo-multimodal`).
Nothing is written anywhere else: no cache, no temporary copies of full tables.

### Folder layout

One folder per project, named **`<project>-<version>`**, the name
`physionet.download` gives it. Inside, every path is the same as on PhysioNet.

```
mimic-demo-multimodal/
  mimic-iv-demo-2.2/                hosp/ icu/ demo_subject_id.csv ...  (whole project)
  mimic-iv-ed-demo-2.2/             ed/ ...                              (whole project)
  mimic-iv-ecg-demo-0.1/            files/p1000/p1000xxxx/s.../...       (whole project)
  mimic-iv-ecg-1.0/                 machine_measurements.csv ...         (demo rows only)
  mimic4wdb-0.1.0/                  waves/p100/p100xxxxx/<record>/...    (demo patients only)
  mimic-cxr-jpg-2.1.0/              files/p10/p10xxxxxx/s.../*.jpg       (demo patients only)
                                    mimic-cxr-2.0.0-metadata.csv.gz ...  (demo rows only)
  mimic-iv-echo-1.0.1/              files/... echo-record-list.csv ...
  mimic-iv-note-2.2/                note/discharge.csv.gz ...            (demo rows only)
  mimic-demo-mm.manifest.json       what was planned and fetched
  mimic-demo-mm.check-report.txt    only while the check finds problems
```

So a file at `https://physionet.org/files/mimic-iv-note/2.2/note/discharge.csv.gz`
is saved as `mimic-iv-note-2.2/note/discharge.csv.gz`.

### What each file is

| kind | what is saved | how it is verified |
|---|---|---|
| **Exact copy** | the file as published: everything in the open demos, and the demo patients' files under `files/` or `waves/` | PhysioNet's SHA-256 checksum |
| **Filtered table** | a top-level table (`.csv` / `.csv.gz`) with a `subject_id` column: same name, same columns, same compression, only the demo patients' rows | the checksum of the filtered file, recorded in the manifest when it was written |
| **Kept whole** | a table without a `subject_id` column, 200 MB or smaller (data dictionaries, the echo study list) | PhysioNet's checksum |
| **Not saved** | other top-level files over 10 MB (such as `IMAGE_FILENAMES`), and tables without a `subject_id` column over 200 MB | listed in the manifest as skipped |

### While downloading

- **Filtered tables** are written to `<name>.part` and renamed when complete,
  so a table under its real name is always complete.
- **Files from `physionet.download`** are written under their final name. If a
  download is interrupted, a shorter file stays there until the next run
  resumes it. `check` reports such a file as *partial*.
- **Files from local copies** (`--local`) are copied, hard-linked or symlinked
  (`--link`). A symlink points into your local copy, so moving that copy breaks it.

### The manifest

`mimic-demo-mm.manifest.json` lists every item the tool planned, per source:
- the path inside the project folder, and whether it's an exact copy or a
  filtered table;
- PhysioNet's checksum and size, and its status (done, skipped or failed);
- for a filtered table: the checksum and size of the filtered file, how many
  rows were kept of how many, and which demo patients it covers.

`check` and `figure` read it. Because it names demo patients and their files,
treat it as credentialed data, like the rest of the folder.

### Upgrading from 0.1

Version 0.1 of this tool saved projects as `<project>/<version>/` (for example
`mimic4wdb/0.1.0/`). Version 0.2 uses `<project>-<version>/` to match the
`physionet` package. The tool never renames folders on its own. If it finds the
old layout, `download`, `check` and `figure` stop and tell you which folders are
affected. Then:

```bash
uv run mimic-demo-mm migrate --out DIR --dry-run   # show what would be renamed
uv run mimic-demo-mm migrate --out DIR             # rename them
```

Only the project folders are renamed: nothing inside them changes. Update any
code that reads the old paths. `migrate` only works on a folder that has this
tool's manifest, so it never touches a copy of PhysioNet made some other way.

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
for PhysioNet with synthetic data. The real `physionet` package downloads
from it. It reproduces:
- credentialed-project passwords, including a rejected password and an account
  with no signed agreement;
- resumable downloads, size checks and folder listings, and the API endpoint
  that lists a project's versions;
- a project without checksums;
- a file whose connection drops halfway.

**Live test.** `tests/test_live.py` runs against the real PhysioNet and uses
about 2 MB. It takes one to two minutes, mostly spent reading the waveform
checksum list. It is off by default:

```bash
MIMIC_DEMO_MM_LIVE=1 uv run --extra test pytest tests/test_live.py -v
```

It downloads the MIMIC-IV-ED demo (about 120 KB) through `physionet.download`,
checks it, confirms a second run fetches nothing, and draws the figure. It also
plans one waveform patient without downloading their files. With a PhysioNet
sign-in it also plans MIMIC-IV-Note, reading only each table's header.
