# MIMIC-IV Multimodal Demo

[![tests](https://github.com/rvandewater/MIMIC-IV-Multimodal-Demo/actions/workflows/tests.yaml/badge.svg)](https://github.com/rvandewater/MIMIC-IV-Multimodal-Demo/actions/workflows/tests.yaml)
[![build](https://github.com/rvandewater/MIMIC-IV-Multimodal-Demo/actions/workflows/python-build.yaml/badge.svg)](https://github.com/rvandewater/MIMIC-IV-Multimodal-Demo/actions/workflows/python-build.yaml)
[![live PhysioNet test](https://github.com/rvandewater/MIMIC-IV-Multimodal-Demo/actions/workflows/live.yaml/badge.svg)](https://github.com/rvandewater/MIMIC-IV-Multimodal-Demo/actions/workflows/live.yaml)
[![PyPI](https://img.shields.io/pypi/v/mimic-demo-mm)](https://pypi.org/project/mimic-demo-mm/)
![python](https://img.shields.io/badge/-Python_3.10--3.14-blue?logo=python&logoColor=white)
[![data: PhysioNet](https://img.shields.io/badge/data-PhysioNet-blue)](https://physionet.org/)
[![cite](https://img.shields.io/badge/cite-datasets-informational)](#citing)

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
| [`mimic-iv-demo` 2.2](https://physionet.org/content/mimic-iv-demo/2.2/) | open | everything: structured, categorical and numeric EHR events |
| [`mimic-iv-ed-demo` 2.2](https://physionet.org/content/mimic-iv-ed-demo/2.2/) | open | everything: ED stays, triage, vitals |
| [`mimic-iv-ecg-demo` 0.1](https://physionet.org/content/mimic-iv-ecg-demo/0.1/) | open | everything: 12-lead ECG waveforms |
| [`mimic-iv-ecg` 1.0](https://physionet.org/content/mimic-iv-ecg/1.0/) | open | tables only (machine measurements, ECG report text), demo patients' rows |
| [`mimic4wdb` 0.1.0](https://physionet.org/content/mimic4wdb/0.1.0/) | open | demo patients' ICU bedside-monitor waveforms and numerics (WFDB records under `waves/`) |
| [`mimic-cxr-jpg` 2.1.0](https://physionet.org/content/mimic-cxr-jpg/2.1.0/) | credentialed | demo patients' chest X-ray JPGs; metadata and label tables filtered to them |
| [`mimic-iv-echo` 1.0.1](https://physionet.org/content/mimic-iv-echo/1.0.1/) | credentialed | demo patients' echo DICOMs; record list and measurements filtered to them |
| [`mimic-iv-note` 2.2](https://physionet.org/content/mimic-iv-note/2.2/) | credentialed | discharge summaries and radiology reports (plus detail tables), demo patients' rows |
| [`mimic-cxr` 2.0.0](https://physionet.org/content/mimic-cxr/2.0.0/) | credentialed | optional (`--include mimic-cxr`): chest X-ray DICOMs and per-study report text |

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
pip install mimic-demo-mm              # or "mimic-demo-mm[figure]" for the overview figure
physionet login                        # once: sign in through your browser, no password stored
mimic-demo-mm download
```

Or, without installing anything: `uvx mimic-demo-mm download`. In a clone of this repository, use
`uv run mimic-demo-mm ...`.

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
- **Cite every dataset you use:** see [Citing](#citing).

## Citing

Cite every dataset you use, as its PhysioNet page asks. The citations below are copied from those pages (retrieved 2026-11-13); check the page for the version you use.

**PhysioNet** (every project page asks for this standard citation):

- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. Nature Health. <https://doi.org/10.1038/s44360-026-00096-z>. Available from: <https://pmc.ncbi.nlm.nih.gov/articles/PMC13641116/>

**The datasets this tool downloads:**

- **[MIMIC-IV Clinical Database Demo, version 2.2](https://physionet.org/content/mimic-iv-demo/2.2/)** (`mimic-iv-demo`)
  - Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023). MIMIC-IV Clinical Database Demo (version 2.2). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/dp1f-ex47>
  - Derived from [MIMIC-IV 1.0](https://physionet.org/content/mimiciv/1.0/): the page asks you to cite it too (see below).

- **[MIMIC-IV-ED Demo, version 2.2](https://physionet.org/content/mimic-iv-ed-demo/2.2/)** (`mimic-iv-ed-demo`)
  - Johnson, A., Bulgarelli, L., Pollard, T., Celi, L. A., Horng, S., & Mark, R. (2023). MIMIC-IV-ED Demo (version 2.2). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/jzz5-vs76>
  - Derived from [MIMIC-IV-ED 2.2](https://physionet.org/content/mimic-iv-ed/2.2/): the page asks you to cite it too (see below).

- **[MIMIC-IV-ECG Demo - Diagnostic Electrocardiogram Matched Subset Demo, version 0.1](https://physionet.org/content/mimic-iv-ecg-demo/0.1/)** (`mimic-iv-ecg-demo`)
  - Gow, B., Pollard, T., Nathanson, L. A., Moody, B., Johnson, A., Moukheiber, D., Greenbaum, N., Berkowitz, S., Eslami, P., Herbst, E., Mark, R., & Horng, S. (2022). MIMIC-IV-ECG Demo - Diagnostic Electrocardiogram Matched Subset Demo (version 0.1). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/4eqn-kt76>
  - Derived from [MIMIC-IV 2.0](https://physionet.org/content/mimiciv/2.0/), [MIMIC-IV Clinical Database Demo 1.0](https://physionet.org/content/mimic-iv-demo/1.0/): the page asks you to cite them too (see below).

- **[MIMIC-IV-ECG: Diagnostic Electrocardiogram Matched Subset, version 1.0](https://physionet.org/content/mimic-iv-ecg/1.0/)** (`mimic-iv-ecg`)
  - Gow, B., Pollard, T., Nathanson, L. A., Johnson, A., Moody, B., Fernandes, C., Greenbaum, N., Waks, J. W., Eslami, P., Carbonati, T., Chaudhari, A., Herbst, E., Moukheiber, D., Berkowitz, S., Mark, R., & Horng, S. (2023). MIMIC-IV-ECG: Diagnostic Electrocardiogram Matched Subset (version 1.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/4nqg-sb35>
  - Derived from [MIMIC-IV 2.2](https://physionet.org/content/mimiciv/2.2/): the page asks you to cite it too (see below).

- **[MIMIC-IV Waveform Database, version 0.1.0](https://physionet.org/content/mimic4wdb/0.1.0/)** (`mimic4wdb`)
  - Moody, B., Hao, S., Gow, B., Pollard, T., Zong, W., & Mark, R. (2022). MIMIC-IV Waveform Database (version 0.1.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/a2mw-f949>
  - Derived from [MIMIC-IV 2.0](https://physionet.org/content/mimiciv/2.0/): the page asks you to cite it too (see below).

- **[MIMIC-CXR-JPG - chest radiographs with structured labels, version 2.1.0](https://physionet.org/content/mimic-cxr-jpg/2.1.0/)** (`mimic-cxr-jpg`)
  - Johnson, A., Lungren, M., Peng, Y., Lu, Z., Mark, R., Berkowitz, S., & Horng, S. (2024). MIMIC-CXR-JPG - chest radiographs with structured labels (version 2.1.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/jsn5-t979>
  - Original publication, which the page also asks you to cite: Johnson AE, Pollard TJ, Berkowitz S, Greenbaum NR, Lungren MP, Deng CY, Mark RG, Horng S. MIMIC-CXR: A large publicly available database of labeled chest radiographs. arXiv preprint arXiv:1901.07042. 2019 Jan 21. <https://arxiv.org/abs/1901.07042>
  - Derived from [MIMIC-CXR Database 2.0.0](https://physionet.org/content/mimic-cxr/2.0.0/): the page asks you to cite it too (see below).

- **[MIMIC-IV-Echo: Echocardiogram Matched Subset, version 1.0.1](https://physionet.org/content/mimic-iv-echo/1.0.1/)** (`mimic-iv-echo`)
  - Gow, B., Pollard, T., Greenbaum, N., Moody, B., Han, A., Waks, J. W., Johnson, A., Herbst, E., Eslami, P., Chaudhari, A., Carbonati, T., Berkowitz, S., Mark, R., & Horng, S. (2026). MIMIC-IV-Echo: Echocardiogram Matched Subset (version 1.0.1). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/307c-mr50>
  - Derived from [MIMIC-IV 2.2](https://physionet.org/content/mimiciv/2.2/), [MIMIC-IV 3.1](https://physionet.org/content/mimiciv/3.1/): the page asks you to cite them too (see below).

- **[MIMIC-IV-Note: Deidentified free-text clinical notes, version 2.2](https://physionet.org/content/mimic-iv-note/2.2/)** (`mimic-iv-note`)
  - Johnson, A., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023). MIMIC-IV-Note: Deidentified free-text clinical notes (version 2.2). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/1n74-ne17>

- **[MIMIC-CXR Database, version 2.0.0](https://physionet.org/content/mimic-cxr/2.0.0/)** (`mimic-cxr`)
  - Johnson, A., Pollard, T., Mark, R., Berkowitz, S., & Horng, S. (2019). MIMIC-CXR Database (version 2.0.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/C2JT1Q>
  - Original publication, which the page also asks you to cite: Johnson, A.E.W., Pollard, T.J., Berkowitz, S.J. et al. MIMIC-CXR, a de-identified publicly available database of chest radiographs with free-text reports. Sci Data 6, 317 (2019). <https://doi.org/10.1038/s41597-019-0322-0>

**Projects the datasets above were derived from** (their pages list them under "Parent Projects", with "Please cite them when using this project"):

- **[MIMIC-CXR Database, version 2.0.0](https://physionet.org/content/mimic-cxr/2.0.0/)**: listed above.
- **[MIMIC-IV Clinical Database Demo, version 1.0](https://physionet.org/content/mimic-iv-demo/1.0/)**: Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2022). MIMIC-IV Clinical Database Demo (version 1.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/jwtp-v091>
- **[MIMIC-IV-ED, version 2.2](https://physionet.org/content/mimic-iv-ed/2.2/)**: Johnson, A., Bulgarelli, L., Pollard, T., Celi, L. A., Mark, R., & Horng, S. (2023). MIMIC-IV-ED (version 2.2). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/5ntk-km72>
- **[MIMIC-IV, version 1.0](https://physionet.org/content/mimiciv/1.0/)**: Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2021). MIMIC-IV (version 1.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/s6n6-xd98>
- **[MIMIC-IV, version 2.0](https://physionet.org/content/mimiciv/2.0/)**: Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2022). MIMIC-IV (version 2.0). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/7vcr-e114>
- **[MIMIC-IV, version 2.2](https://physionet.org/content/mimiciv/2.2/)**: Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023). MIMIC-IV (version 2.2). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/6mm1-ek67>
  - Original publication, which the page also asks you to cite: Johnson, A.E.W., Bulgarelli, L., Shen, L. et al. MIMIC-IV, a freely accessible electronic health record dataset. Sci Data 10, 1 (2023). <https://doi.org/10.1038/s41597-022-01899-x>
- **[MIMIC-IV, version 3.1](https://physionet.org/content/mimiciv/3.1/)**: Johnson, A., Bulgarelli, L., Pollard, T., Gow, B., Moody, B., Horng, S., Celi, L. A., & Mark, R. (2024). MIMIC-IV (version 3.1). PhysioNet. RRID:SCR_007345. <https://doi.org/10.13026/kpb9-mt58>
  - Original publication, which the page also asks you to cite: Johnson, A.E.W., Bulgarelli, L., Shen, L. et al. MIMIC-IV, a freely accessible electronic health record dataset. Sci Data 10, 1 (2023). <https://doi.org/10.1038/s41597-022-01899-x>

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

**Releasing.** Push a tag such as `v0.2.0`. The `python-build.yaml` workflow
builds the package on every push. For a tag, it also publishes to PyPI through
trusted publishing, signs the files with Sigstore, and creates a GitHub release.
The version comes from the tag (hatch-vcs).

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

The `live.yaml` workflow runs it weekly and on demand, with open data only.
Never give that workflow a PhysioNet sign-in: credentialed data must not be
downloaded to GitHub's machines.
