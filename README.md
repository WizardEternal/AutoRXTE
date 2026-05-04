# AutoRXTE

Batch processing for RXTE/PCA observations: download from the HEASARC S3
mirror, run the standard `pcaprep* / seextrct / maketime / pcaextlc* /
pcaextspect2 / powspec` chain, and apply your XSPEC fits across many
ObsIDs. Each stage is its own subcommand and runs unattended on a fresh
download with no manual XSPEC sessions until you actually want to fit.

For a fully programmatic XSPEC fitting API (parameter manipulation,
steppar, MCMC, contour grids), use
[pyxspec](https://heasarc.gsfc.nasa.gov/xanadu/xspec/python/html/index.html)
or [Sherpa](https://cxc.cfa.harvard.edu/sherpa/). The `xspec` subcommand
here is template-driven: you craft one `.xcm` interactively, AutoRXTE
distributes it across many ObsIDs and aggregates results.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Requirements

- Python 3.8 or later
- HEASoft initialised in the shell (`source $HEADAS/headas-init.sh`).
  Tested with HEASoft 6.33.
- Python packages: `astropy`, `astroquery`, `boto3`, `numpy`, `pyyaml`.

```bash
git clone https://github.com/WizardEternal/AutoRXTE.git
cd AutoRXTE
pip install -r requirements.txt
```

`pip install -e .` installs the `autorxte` console script. Otherwise run
the modules with `python -m autorxte.cli.main <command>`.

## Pipeline

The core pipeline is a linear chain. Each step writes outputs that the
next step reads, all under `<obsid>-results/Analysis/`.

| Step          | Output                          | Tool                    |
|---------------|---------------------------------|-------------------------|
| download      | `<obsid>/`                      | (S3 archive)            |
| prepare       | `<obsid>-results/`              | pcaprepobsid            |
| organize      | `Analysis/fits_files.god`       | FITS scan + path list   |
| bitmask       | `Analysis/bitmask_event`        | (file copy)             |
| filter        | `Analysis/good.gti`             | maketime                |
| extract       | `Analysis/event.lc`             | seextrct (full band)    |
| lightcurves   | `Analysis/std1.lc, light.lc`    | pcaextlc1, pcaextlc2    |
| spectra       | `Analysis/{src,bkg,rsp}.pha`    | pcaextspect2            |
| pds           | `Analysis/pds-{src,rsp}.pha`    | powspec + fplot + flx2xsp |

Advanced steps (`color-extract`, `color-plot`, `xspec`, `xenon`, `plot`)
read the same `Analysis/` outputs.

## End-to-end example

A full run from search to XSPEC fit on the smallest GRS 1915+105 ObsID:

```bash
WORK=./data

autorxte download --source "GRS 1915+105" --bottom-n 1 \
                  --directory $WORK --no-interactive
DL=$WORK/download_RXTE_GRS1915+105

autorxte prepare      --directory $DL --no-interactive
autorxte organize     --directory $DL --no-interactive
autorxte bitmask      --directory $DL --no-interactive
autorxte filter       --directory $DL --no-interactive
autorxte extract      --directory $DL --no-interactive
autorxte lightcurves  --directory $DL --type std2 --no-interactive
autorxte lightcurves  --directory $DL --type std1 --no-interactive
autorxte spectra      --directory $DL --no-interactive
autorxte pds          --directory $DL --no-interactive
autorxte color-extract --directory $DL --no-interactive
```

On a small ObsID (~18 MB), the full chain runs in roughly 35 seconds
end-to-end (most of that is the download).

## Subcommands

Every subcommand supports `--no-interactive` and exposes its parameters
as flags. Without `--no-interactive`, missing arguments are prompted for
with sensible defaults shown in `[brackets]`.

### download

Downloads from `s3://nasa-heasarc/xte/data/archive/AOn/Pnnnnn/<obsid>/`
in parallel via boto3. Resume is automatic via a per-source
`downloaded_RXTE_<source>.json` ledger.

```bash
autorxte download --source "GRS 1915+105" --top-n 5 --directory ./data
autorxte download --source "Cyg X-1" --obsids 10408-01-01-00,10408-01-01-01
autorxte download --source "GX 339-4" --bottom-n 1 --auto-detect-region
```

Notable flags: `--top-n / --bottom-n / --obsids` to pick observations,
`--min-exposure / --start-date / --end-date` to filter,
`--region / --auto-detect-region` for AWS region selection,
`--bucket` to override the S3 bucket.

The archive prefix is configurable via `download.s3.archive_prefix` in
`autorxte_config.yaml`. HEASARC has reorganised the layout once before
(`rxte/` to `xte/`); when listings come back empty the tool prints the
exact `aws s3 ls --no-sign-request s3://<bucket>/` command to inspect.

### prepare

Runs `pcaprepobsid` on each ObsID directory. Creates `<obsid>-results/`
with the standard `FP_*.lis` lists and `appid.lis` sentinel.

```bash
autorxte prepare --directory ./data/download_RXTE_GRS1915+105 --workers 4
```

`--no-skip-existing` re-prepares ObsIDs whose `-results/` already has
the sentinel.

### organize

Scans every ObsID's `pca/` for FITS files, reads the `DATAMODE` and
`DDESC` headers from the `XTE_SE` (event-mode) and `XTE_SP` (Good Xenon)
extensions, and writes path lists into `Analysis/`:

- `fits_data_summary.csv`, `fits_files.god` for event-mode files
- `xenon_data_summary.csv`, `xenon_files.god` for Xenon-mode files

`fits_files.god` is the input to `seextrct` in the `extract` step. If
this step is skipped, downstream extraction has nothing to read.

### bitmask

Copies a `seextrct` bitmask file into every `<obsid>-results/Analysis/`,
renamed to `bitmask_event` (the canonical filename downstream tools
expect).

```bash
autorxte bitmask --list                                  # show available
autorxte bitmask --bitmask bitfile_gx_d012 --directory ./data
autorxte bitmask --bitmask /custom/path/mybitmask.txt --directory ./data
```

The repo ships the full HEASARC PCA bitmask catalog (35 files: D-token,
Good Xenon, Z-token modes) under `bitmasks/`. See
[`bitmasks/README.md`](bitmasks/README.md) for the index and a guide to
which to use for which `DATAMODE`.

### filter

Runs `maketime` to build `Analysis/good.gti` from the prep-stage filter
file. Default selection expression is the typical RXTE PCA cuts:

```
(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0)
&& .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)
```

Override with `--filter '<expr>'`.

### extract

Runs `seextrct` against `Analysis/fits_files.god` and `Analysis/good.gti`
to produce `Analysis/event.lc`, the full-band lightcurve. `--token xenon`
switches to `Analysis/xenon_event_files.txt` (built by the `xenon`
subcommand).

### lightcurves

`pcaextlc1` for STD1 single-channel, `pcaextlc2` for STD2 multi-channel.

```bash
autorxte lightcurves --type std2 --directory ./data
autorxte lightcurves --type std1 --bin-size 0.125 --directory ./data
```

`pcaextlc1/2` has a fixed-size internal buffer for the temp filename it
allocates next to your output. Long output paths overflow it and the
tool aborts with the unhelpful "COLUMNS parameter may be too long" error.
AutoRXTE works around this by running the tool in a short tempdir and
moving the lightcurve into `Analysis/` afterwards. See the comment in
`autorxte/core/lightcurves_07.py` if you need to dig into it.

### spectra

`pcaextspect2` produces `src.pha`, `bkg.pha`, and `rsp.pha` together.
Same path-length workaround as lightcurves.

### pds

Runs `powspec`, then `fplot`, then `flx2xsp` to produce `pds-src.pha`
and `pds-rsp.pha`, an XSPEC-readable spectrum representation of the
power spectrum suitable for fitting QPO models.

The default plot device is `/null` so this works on headless boxes
without `DISPLAY`. Pass `--plot-device pds.png/png` to also save a PGPLOT
PNG of the spectrum.

### color-extract

Runs `seextrct` once per energy band to make per-band lightcurves
(`soft.lc`, `medium.lc`, `hard.lc` by default).

```bash
autorxte color-extract --directory ./data \
                       --ranges 0-13 14-35 36-255 \
                       --names soft medium hard
```

Energy ranges here are PCA channel IDs, **not keV**. See
[`bitmasks/README.md`](bitmasks/README.md) for the conversion.

### xspec

Template-driven XSPEC runner. You craft one `.xcm` interactively (`xspec`,
fit, `save all best.xcm`), then this distributes it across every
`<obsid>-results/Analysis/` and runs the operations you ask for.

```bash
autorxte xspec --xcm best.xcm --directory ./data \
               --energy 3-30 \
               --error 1,2,3,4,5 \
               --flux 3-30 \
               --output fit_results.csv
```

What it does for each ObsID:

1. Copies the template into `Analysis/<name>.xcm`. By default rewrites
   the `data`, `response`, `backgrnd`, `arf`, and `corfile` lines so each
   instance points at that ObsID's spectra (basename preserved). Pass
   `--no-rewrite` to use the template verbatim with `cwd=Analysis/`.
2. Builds the XSPEC stdin script:
   `@<name>.xcm; [ignore]; freeze/thaw; gain fit; fit N; error i,j,...;
    flux Emin Emax; save all <name>_bestfit.xcm; exit`.
3. Runs `xspec`, captures the log, and verifies `<name>_bestfit.xcm`
   exists (catches XSPEC's silent-failure mode).
4. Parses the log for χ², dof, reduced χ², per-parameter values and
   quoted errors, the `error` command's confidence ranges
   (lo, hi, Δ−, Δ+), and integrated flux (photons and ergs).

All ObsIDs aggregate into one CSV at `--output`.

What this is not: a wrapper for steppar, contour grids, MCMC, F-tests,
add-component / del-component, multi-dataset joint loads, or programmatic
parameter manipulation between fit phases. Those want pyxspec or Sherpa.

### xenon

Good-Xenon preprocessing: `make_se` + the `xenon_event_files.txt`
generation that lets `extract --token xenon` work. Requires Xenon-mode
data (`XTE_SP` extension) in `pca/`.

### plot

Wrapper around `lcurve` for batch lightcurve plotting. Default device is
`/null` (headless). PGPLOT's hardcopy-to-PNG behaviour through `lcurve`
stdin scripts is finicky and version-dependent; the data files are the
primary product, the plot is best-effort.

## Configuration

Most of the runtime parameters can also be set in `autorxte_config.yaml`
in any of these locations (first match wins):

1. `./autorxte_config.yaml` (current working directory)
2. `~/.autorxte/config.yaml`
3. The package default

See [`CONFIG_GUIDE.md`](CONFIG_GUIDE.md) for the full key reference.
Most flags on the command line accept the same values; explicit flags
override the config.

## How HEASoft tools are run

HEASoft's parameter-driven FTOOLS (`pcaprepobsid`, `seextrct`,
`maketime`, `lcurve`, `xspec`, etc.) open `/dev/tty` for prompts even
when every parameter is supplied on the command line. Under a non-tty
stdin, they typically fail with `Unable to redirect prompts to the
/dev/tty` and exit with OS code **0**, leaving no output and no error
visible to the caller.

AutoRXTE runs all of them through a small pty wrapper
(`autorxte/utils/subprocess_utils.py:run_heasoft_pty`) that:

1. Allocates a pseudo-terminal and makes the slave the controlling tty
   in the child via `setsid + TIOCSCTTY`.
2. Captures combined stdout/stderr.
3. Parses the HEASoft `Task <name> ... terminating with status N` line
   and raises if N is non-zero (catching the OS-exit-0 silent-failure
   mode).
4. Verifies a list of expected output files actually exist after the
   call returns.
5. Enforces a per-call timeout.

If you are wrapping a new HEASoft tool, use this helper instead of
calling `subprocess.run` directly.

## Resume / skip semantics

Every subcommand checks for its own primary output before starting and
skips ObsIDs that already have it. `--no-skip-existing` overrides.

What each step looks for:

| step          | sentinel that triggers SKIP                |
|---------------|--------------------------------------------|
| download      | per-file paths in `downloaded_*.json`      |
| prepare       | `<obsid>-results/appid.lis`                |
| organize      | `Analysis/fits_files.god`                  |
| bitmask       | `Analysis/bitmask_event`                   |
| filter        | `Analysis/good.gti` (non-empty)            |
| extract       | `Analysis/<prefix>.lc` (non-empty)         |
| lightcurves   | `Analysis/<lc-name>` (non-empty)           |
| spectra       | `Analysis/<src-name>` (non-empty)          |
| pds           | `Analysis/pds-src.pha` (non-empty)         |
| color-extract | `Analysis/<color>.lc` per band (non-empty) |
| xspec         | `Analysis/<name>_bestfit.xcm` (non-empty)  |

This means the safe way to retry a flaky run is to just re-invoke the
same command. No manual cleanup needed.

## Logging

All modules log via `logging.getLogger(__name__)`. The CLI configures it
to `INFO` by default, `--verbose` for `DEBUG`, `--quiet` for
`WARNING`-and-up.

```bash
autorxte --verbose extract --directory ./data
autorxte --quiet pds --directory ./data
```

`--verbose` also makes the CLI print full Python tracebacks on error
instead of the one-line `error: <type>: <msg>` summary.

## Known issues

- `lcurve` plot output. PGPLOT's hardcopy-to-PNG inside an `lcurve`
  stdin script depends on the PGPLOT build and sometimes does not
  produce the file even when the device is set. The `.lc` data is fine;
  the PNG is not always.
- The `gnome-terminal` mode in `xenon` (used historically for
  side-by-side `make_se` runs) only works on systems with that terminal
  emulator installed. The default path runs `make_se` in-process via the
  pty wrapper.
- `pcaextlc1/pcaextlc2` and `pcaextspect2` cannot tolerate long output
  paths. The wrappers run them in a short tempdir and move outputs
  afterwards. If you bypass the wrappers, expect "COLUMNS parameter may
  be too long" errors and use shorter paths.

## Module layout

```
autorxte/
├── core/
│   ├── download_01.py        S3 download + resume
│   ├── preparation_02.py     pcaprepobsid
│   ├── organization_03.py    FITS scan + .god generation
│   ├── bitmasks_04.py        bitmask distribution + auto-discover
│   ├── filtering_05.py       maketime
│   ├── extraction_06.py      seextrct (+ split_gti helper)
│   ├── lightcurves_07.py     pcaextlc1, pcaextlc2
│   ├── spectra_08.py         pcaextspect2
│   └── pds_09.py             powspec + fplot + flx2xsp
├── advanced/
│   ├── color_color_01.py     per-band seextrct + lcurve
│   ├── xspec_fit_02.py       template .xcm runner
│   ├── xenon_mode_03.py      Good-Xenon make_se chain
│   └── plotting_04.py        batch lcurve
├── utils/
│   ├── subprocess_utils.py   run_heasoft_pty + HEASoftToolError
│   ├── interactive.py        get_input/get_path/get_choice helpers
│   └── fits_utils.py         GTI splitting
├── cli/
│   └── main.py               argparse dispatcher
├── config.py                 YAML loader (singleton)
└── autorxte_config.yaml      default config (in package)
```

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

NASA HEASARC for hosting the RXTE archive on the public S3 mirror, and
the HEASoft team for the FTOOLS this is built around.
