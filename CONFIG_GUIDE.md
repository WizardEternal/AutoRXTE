# AutoRXTE Configuration System - User Guide

## Overview

AutoRXTE uses a comprehensive YAML configuration system that lets you customize **every single parameter** without editing code. This includes:

- Energy ranges (in CHANNEL IDs, NOT keV!)
- Time bin sizes
- Filter expressions
- XSPEC models and parameters
- Parallel workers
- Output file names
- And much more...

## Quick Start

### 1. Copy the Default Config

```bash
# Copy default config to your working directory
cp autorxte_config.yaml my_project_config.yaml
```

### 2. Edit Parameters

```yaml
# Example: Change color analysis ranges
color_analysis:
  ranges:
    soft: "0-10"      # Channels 0-10
    medium: "11-30"   # Channels 11-30
    hard: "31-255"    # Channels 31-255
```

### 3. Use Your Config

```python
from autorxte.config import load_config
from autorxte.core import *

# Load your custom config
load_config('my_project_config.yaml')

# Now all functions use your config
extract_color_ranges(interactive=False)  # Uses your ranges!
```

## Understanding Energy Ranges

### ⚠️ CRITICAL: Channels vs keV

**Energy ranges in AutoRXTE configs are CHANNEL IDs (0-255), NOT keV!**

```yaml
# ✅ CORRECT - Channel IDs
ranges:
  soft: "0-13"
  medium: "14-35"
  hard: "36-255"

# ❌ WRONG - Don't use keV values!
ranges:
  soft: "2-6"     # This means channels 2-6, NOT 2-6 keV!
```

### Channel to Energy Conversion

RXTE PCA channel-to-energy conversion varies by gain epoch, but approximate conversion:

| Channels | Approximate Energy | Name |
|----------|-------------------|------|
| 0-13 | ~2-6 keV | Soft X-ray |
| 14-35 | ~6-13 keV | Medium |
| 36-255 | ~13-60 keV | Hard X-ray |

**For precise conversion**, check RXTE gain files for your observation epoch.

### Example Range Definitions

```yaml
# Standard black hole analysis
ranges:
  soft: "0-13"      # ~2-6 keV
  medium: "14-35"   # ~6-13 keV
  hard: "36-255"    # ~13-60 keV

# High-energy focus
ranges:
  low: "0-20"       # ~2-7 keV
  mid: "21-50"      # ~7-18 keV
  high: "51-255"    # ~18-60 keV

# Soft source focus
ranges:
  verysoft: "0-5"   # ~2-4 keV
  soft: "6-15"      # ~4-7 keV
  medium: "16-40"   # ~7-15 keV
```

## Config File Locations

AutoRXTE searches for configs in this order:

1. `./autorxte_config.yaml` (current directory) ← **Highest priority**
2. `~/.autorxte/config.yaml` (user home)
3. Package default config ← Lowest priority

**Tip:** Place project-specific configs in your project directory!

## Configuration Sections

### Download Module

```yaml
download:
  workers: auto               # auto = CPU count
  search:
    catalog: xtemaster
    search_radius_arcmin: 5.0
```

### Preparation Module

```yaml
preparation:
  workers: auto
  skip_existing: true         # Don't reprocess existing results
```

### GTI Filtering (CRITICAL!)

```yaml
filtering:
  # Default filter - tested and reliable
  filter_expression: "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) && .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)"
  
  # Stricter filter for clean data
  # strict_filter: "(ELV > 10) && (OFFSET < 0.02) && (NUM_PCU_ON == 3)"
```

**⚠️ WARNING:** Changing filter expressions affects your entire analysis! Test carefully!

### Event Extraction

```yaml
extraction:
  token: e                    # 'e' or 'xenon'
  bitmask: bitmask_event
  prefix: event
  time_bin: 0.004            # Seconds - extraction binning
  split_gti: false
  workers: auto
```

**Time bin notes:**
- `0.004` = 4 ms (standard)
- `0.001` = 1 ms (fast timing)
- `0.000125` = 125 μs (kHz QPOs)

### Lightcurves

```yaml
lightcurves:
  type: std2                  # 'std1' or 'std2'
  
  std1:
    output_name: std1.lc
    pcu_selection: 2
    bin_size_sec: 0.125      # 125 ms bins
  
  std2:
    output_name: light.lc
    pcu_selection: 2
    energy_channels: ALL      # Or specific range
    time_bins: 16            # Number of bins
```

### Spectra

```yaml
spectra:
  pcu_selection: 2            # PCU 2 most reliable
  energy_channels: ALL
  source_file: src.pha
  background_file: bkg.pha    # Auto-generated!
  response_file: rsp.pha      # Auto-generated!
```

**Remember:** Background and response are generated automatically by pcaextspect2!

### Power Spectra (PDS)

```yaml
pds:
  input_lightcurve: event.lc
  binning: -1                 # -1 = auto
  rebin: -1.03               # Geometric rebinning
  max_bins: 8192
  window: none
  norm: -2                    # Leahy normalization
  workers: auto
```

**Variants for different analyses:**

```yaml
powspec_variants:
  # High-frequency QPO search
  high_freq:
    binning: -1
    max_bins: 16384
    nyquist_freq: 1000
    rebin: -1.03
  
  # Low-frequency analysis
  low_freq:
    binning: 0.04
    max_bins: 8192
    rebin: -1.03
```

### Color-Color Analysis

```yaml
color_analysis:
  # THESE ARE CHANNEL IDs, NOT keV!
  ranges:
    soft: "0-13"
    medium: "14-35"
    hard: "36-255"
  
  color_names:
    - soft
    - medium
    - hard
  
  time_bin: 0.04              # Extraction binning
  lcurve_bin_size: -1         # Plotting binning (-1 = auto)
  workers: auto
```

### XSPEC Fitting

```yaml
xspec:
  default_model: diskbb_pexrav
  
  energy_range:
    min: 3.0                  # keV (this IS in keV!)
    max: 30.0                 # keV
  
  models:
    diskbb_pexrav:
      expression: "tbabs(diskbb + pexrav)"
      params:
        nH: [5.5, 2.0, 10.0]           # [value, min, max]
        diskbb_kT: [1.2, 1.0, 4.0]
        diskbb_norm: 400                # Single value = frozen
        pexrav_PhoIndex: [2.0, 1.3, 4.0]
        # ... more params
  
  max_iterations: 1000
  save_plots: true
```

**Model parameter formats:**
- `value` - Frozen parameter
- `[value, min, max]` - Free parameter with bounds
- Set to `-1` to freeze at current value

### Xenon Mode

```yaml
xenon:
  fits_extension: XTE_SP
  output_root: event
  event_pattern: xenon_event_gx*
  use_terminals: false        # Linux terminal mode
```

### Plotting

```yaml
plotting:
  bin_size: 1.0              # Seconds
  max_bins: 10000
  format: png                # or 'eps'
  workers: auto
```

## Using Config in Code

### Method 1: Use Config Defaults

```python
from autorxte.core import *

# All functions use config defaults
extract_all_events(interactive=False)
generate_lightcurves(interactive=False)
```

### Method 2: Load Custom Config

```python
from autorxte.config import load_config
from autorxte.core import *

# Load your custom config
load_config('my_analysis_config.yaml')

# Now uses your custom parameters
extract_all_events(interactive=False)
```

### Method 3: Override Config with Parameters

```python
from autorxte.core import *

# Parameters override config
extract_all_events(
    time_bin=0.001,          # Override config time_bin
    workers=8,               # Override config workers
    interactive=False
)
```

### Method 4: Access Config Directly

```python
from autorxte.config import get_config

config = get_config()

# Get specific values
time_bin = config.get('extraction.time_bin', 0.004)
filter_expr = config.get_filter_expression()

# Get entire sections
pds_config = config.get_section('pds')

# Get color ranges
ranges, names = config.get_color_ranges()
```

## Example Workflows

### Workflow 1: High-Energy Analysis

```python
from autorxte.config import load_config
from autorxte.core import *
from autorxte.advanced import *

# Load high-energy config
load_config('config_high_energy.yaml')

# Run analysis - all uses high-energy parameters
search_and_download("Cyg X-1", top_n=10)
prepare_all_obsids()
extract_all_events()          # Uses time_bin=0.001 from config
generate_lightcurves()
extract_spectra()
fit_all_spectra()             # Uses powerlaw model from config
extract_color_ranges()        # Uses high-energy channel ranges
```

### Workflow 2: QPO Search

```python
load_config('config_qpo_analysis.yaml')

# Fine time resolution for QPOs
extract_all_events()          # Uses time_bin=0.000125
compute_pds()                 # Uses max_bins=16384
```

### Workflow 3: Mixed Parameters

```python
load_config('my_config.yaml')

# Some from config, some override
extract_all_events(
    token='xenon',            # Override
    time_bin=0.01,           # Override
    # workers, bitmask, etc from config
    interactive=False
)
```

## Example Configs Provided

We provide several example configs for common analyses:

1. **config_high_energy.yaml** - Hard X-ray focus
2. **config_soft_thermal.yaml** - Thermal/soft state
3. **config_qpo_analysis.yaml** - QPO detection

Copy and modify these for your needs!

## Best Practices

### 1. One Config Per Project

```
my_project/
├── data/
├── autorxte_config.yaml    # Project-specific config
└── analysis.py
```

### 2. Document Your Changes

```yaml
# Custom config for GX 339-4 outburst analysis
# Modified: 2025-01-15
# Changes: Increased time resolution for QPO search

extraction:
  time_bin: 0.000125  # 125 μs for kHz QPOs
```

### 3. Version Control Your Configs

```bash
git add autorxte_config.yaml
git commit -m "Add QPO analysis config"
```

### 4. Test Filter Changes

```python
# Test new filter on one observation first
create_gti_filters(
    filter_expression="(ELV > 10) && (OFFSET < 0.02)",
    interactive=False
)
# Check outputs before running on all data
```

## Common Customizations

### Change Time Resolution

```yaml
# Standard timing
extraction:
  time_bin: 0.004    # 4 ms

# Fast timing
extraction:
  time_bin: 0.001    # 1 ms

# Ultra-fast (kHz QPOs)
extraction:
  time_bin: 0.000125 # 125 μs
```

### Adjust Energy Ranges

```yaml
# Remember: CHANNELS not keV!

# For harder source
color_analysis:
  ranges:
    low: "0-25"
    mid: "26-60"
    high: "61-255"

# For softer source  
color_analysis:
  ranges:
    verysoft: "0-8"
    soft: "9-20"
    medium: "21-50"
```

### Change XSPEC Model

```yaml
xspec:
  default_model: powerlaw_only  # For hard state
  
  # Or custom model
  models:
    my_model:
      expression: "tbabs*(diskbb + nthcomp)"
      params:
        nH: 5.5
        # ...
```

### Adjust PDS Settings

```yaml
# For low-frequency QPOs
pds:
  binning: 0.1       # Longer bins
  max_bins: 4096
  rebin: -1.05

# For high-frequency QPOs
pds:
  binning: -1
  max_bins: 16384
  rebin: -1.01
```

## Troubleshooting

### Config Not Loading

```python
# Check which config is being used
from autorxte.config import get_config

config = get_config()
print("Config loaded successfully")

# Try explicit load
load_config('/full/path/to/config.yaml')
```

### Wrong Energy Ranges

```
ERROR: No events extracted

# Check: Are you using channels (0-255) not keV?
# ❌ ranges: soft: "2-6"   (Too low - no channels!)
# ✅ ranges: soft: "0-13"  (Correct channels)
```

### Module Not Using Config

```python
# Make sure to use interactive=False
extract_all_events(interactive=False)  # ✅ Uses config

# Not this
extract_all_events(interactive=True)   # ❌ Prompts user
```

## Advanced: Creating Custom Variants

```yaml
# Define multiple PDS variants
powspec_variants:
  qpo_low:
    binning: 0.1
    max_bins: 4096
    rebin: -1.05
  
  qpo_mid:
    binning: 0.01
    max_bins: 8192
    rebin: -1.03
  
  qpo_high:
    binning: -1
    max_bins: 16384
    rebin: -1.01
```

```python
# Use variants in code
config = get_config()

# Run all three variants
for variant_name in ['qpo_low', 'qpo_mid', 'qpo_high']:
    variant = config.get_section(f'powspec_variants.{variant_name}')
    compute_pds(
        binning=variant['binning'],
        max_bins=variant['max_bins'],
        rebin=variant['rebin'],
        interactive=False
    )
```

## Summary

✅ **All parameters are configurable**
✅ **Energy ranges are CHANNEL IDs (0-255)**
✅ **Config overrides defaults**
✅ **Parameters override config**
✅ **One config per project recommended**

See `autorxte_config.yaml` for complete parameter list!
