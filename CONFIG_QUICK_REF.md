# Config Quick Reference

The full reference is in [CONFIG_GUIDE.md](CONFIG_GUIDE.md). This is just
the cheatsheet for the keys people change most often.

## Ranges are PCA channel IDs (0-255), not keV

The one rule worth printing out and taping to a monitor.

```yaml
# Right
color_analysis:
  ranges:
    soft:   "0-13"     # ~2-6 keV
    medium: "14-35"    # ~6-13 keV
    hard:   "36-255"   # ~13-60 keV

# Wrong: this means "channels 2 through 6", not "2 to 6 keV"
color_analysis:
  ranges:
    soft: "2-6"
```

The exception is anything inside `xspec:` and the `--energy` / `--flux`
CLI flags on `autorxte xspec` and `autorxte pds`, which are in keV
because XSPEC and the PDS power-spectrum bands work on energy.

## Where the config is loaded from

First match wins:

1. `./autorxte_config.yaml` (cwd)
2. `~/.autorxte/config.yaml`
3. The package default

Or pass `autorxte --config /path/to/config.yaml <subcommand> ...`.

## Keys you actually change

```yaml
download:
  s3:
    bucket: nasa-heasarc
    region: us-east-1
    archive_prefix: "xte/data/archive/{cycle}/{prnb}/{obsid}/"

filtering:
  filter_expression: "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) && .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)"

extraction:
  time_bin: 0.004        # 4 ms standard, 0.000125 for kHz QPOs

lightcurves:
  std2:
    time_bins: 16        # bin size in seconds, multiple of 16
    chmin: 0             # required when layerlist=ALL
    chmax: 255

color_analysis:
  ranges:
    soft:   "0-13"
    medium: "14-35"
    hard:   "36-255"

pds:
  binning: -1            # auto
  rebin: -1.03           # geometric
  max_bins: 8192
```

## Loading a config in Python

```python
from autorxte.config import load_config
load_config('my_config.yaml')

from autorxte.core import generate_lightcurves
generate_lightcurves(interactive=False)
```

CLI flags override config values; config values override hard-coded
defaults.

## Common mistakes

- Setting `time_bin: 0.000125` and getting empty output: the binning is
  finer than the source's frame time. Check the original PCA mode.
- `extract_color_ranges` produces no events: ranges are written as keV
  (`"2-6"`) instead of channels (`"0-13"`).
- `pcaextlc2` aborts with "COLUMNS parameter may be too long": use the
  CLI / Python wrapper, which handles this automatically. If you must
  call `pcaextlc2` directly, run it with a short output path.
