# AutoRXTE

Automated pipeline for RXTE X-ray data analysis from download to advanced spectral-timing products.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

AutoRXTE is a comprehensive Python toolkit designed to automate the complete RXTE (Rossi X-ray Timing Explorer) data analysis workflow. The package provides both programmatic and interactive interfaces for researchers to efficiently process RXTE observations, from raw data acquisition through advanced spectral-timing analysis.

### Key Features

**Complete Analysis Pipeline**
- Automated data acquisition from NASA HEASARC archives
- Parallel processing with configurable worker pools
- Comprehensive error handling and progress tracking
- Resume capability for interrupted downloads

**Core Analysis Modules**
- Data preparation and organization
- GTI (Good Time Interval) filtering
- Event extraction for E-token and Xenon modes
- Standard and custom lightcurve generation
- Spectral extraction with automatic background and response
- Power density spectrum (PDS) analysis

**Advanced Capabilities**
- Multi-energy color-color diagram generation
- Automated XSPEC spectral model fitting
- Complete Xenon mode preprocessing workflow
- Batch lightcurve visualization

**Flexible Configuration**
- YAML-based parameter customization
- Region-specific download optimization
- Pre-configured templates for common analyses (QPO detection, hard/soft states)

## Installation

### Requirements

- Python ≥ 3.8
- HEASoft (with FTOOLS, XSPEC, and XRONOS)
- Required Python packages: astropy, astroquery, boto3, numpy, pyyaml

### From Source

```bash
git clone https://github.com/WizardEternal/AutoRXTE.git
cd AutoRXTE
pip install -r requirements.txt
```

**Note:** Package is not yet available on PyPI. Installation from pip will be supported in a future release.

### HEASoft Installation

AutoRXTE requires HEASoft to be installed and initialized:

```bash
# Initialize HEASoft (required before using AutoRXTE)
source $HEADAS/headas-init.sh

# Add to ~/.bashrc for automatic initialization
echo "source $HEADAS/headas-init.sh" >> ~/.bashrc
```

Download HEASoft from: https://heasarc.gsfc.nasa.gov/lheasoft/

## Quick Start

### Basic Workflow

```python
from autorxte.core import (
    search_and_download, prepare_all_obsids, extract_all_events,
    generate_lightcurves, extract_spectra, compute_pds
)
from pathlib import Path

# Download observations
search_and_download(
    source="Cygnus X-1",
    top_n=10,
    output_dir=Path("./data"),
    interactive=False
)

# Process observations
prepare_all_obsids(root_dir=Path("./data"))
extract_all_events(root_dir=Path("./data"))
generate_lightcurves(root_dir=Path("./data"))
extract_spectra(root_dir=Path("./data"))
compute_pds(root_dir=Path("./data"))
```

### Advanced Analysis

```python
from autorxte.advanced import (
    extract_color_ranges, plot_color_diagrams,
    fit_all_spectra, xenon_complete_workflow
)

# Color-color diagram analysis
extract_color_ranges(
    ranges=['0-13', '14-35', '36-255'],  # Channel IDs, not keV
    names=['soft', 'medium', 'hard']
)
plot_color_diagrams()

# Automated XSPEC fitting
fit_all_spectra(model='tbabs(diskbb + pexrav)')
```

### Configuration-Based Workflow

```python
from autorxte.config import load_config

# Load custom configuration
load_config('qpo_analysis.yaml')

# All parameters now use config values
extract_all_events()  # Uses time_bin from config
compute_pds()         # Uses max_bins from config
```

## Command Line Interface

```bash
# Download with automatic region optimization
autorxte download --source "Cyg X-1" --top-n 10 --auto-detect-region

# Process pipeline
autorxte prepare --directory ./data
autorxte extract --directory ./data
autorxte lightcurves --directory ./data --type std2
autorxte spectra --directory ./data
autorxte pds --directory ./data

# Advanced features
autorxte color-extract --directory ./data
autorxte xspec --directory ./data --model diskbb_pexrav
```

## Interactive Menu

For interactive analysis with a terminal menu interface:

```bash
python autorxte_interactive.py
```

## Global Download Optimization

AutoRXTE implements intelligent region selection for optimal download speeds worldwide:

**Automatic Region Detection**
```python
# First run: Auto-detects fastest AWS region
search_and_download("GX 339-4", top_n=5)

# Preference saved to ~/.autorxte/download_region.json
# Subsequent runs use saved preference automatically
```

**Expected Performance by Region**
| Region | Optimal AWS Endpoint |
|--------|---------------------|
| North America | us-east-1, us-west-2 |
| Europe | eu-west-1 |
| India | ap-south-1 (Mumbai) |
| Southeast Asia | ap-southeast-1 (Singapore) |
| East Asia | ap-northeast-1 (Tokyo) |

**Manual Configuration**
```yaml
# autorxte_config.yaml
download:
  s3:
    region: ap-south-1  # Override for your location
```

## Configuration System

AutoRXTE uses YAML-based configuration for all analysis parameters.

**Critical Note on Energy Ranges:** All energy ranges in configuration files use **PCA channel IDs (0-255)**, not keV values.

```yaml
# Correct: Channel IDs
color_analysis:
  ranges:
    soft: "0-13"      # Channels 0-13 ≈ 2-6 keV
    medium: "14-35"   # Channels 14-35 ≈ 6-13 keV
    hard: "36-255"    # Channels 36-255 ≈ 13-60 keV

# Incorrect: Do not use keV values
# ranges:
#   soft: "2-6"  # This means channels 2-6, NOT 2-6 keV!
```

**Channel to Energy Conversion** (approximate, varies by gain epoch):
- Channels 0-13: ~2-6 keV (soft X-rays)
- Channels 14-35: ~6-13 keV (medium)
- Channels 36-255: ~13-60 keV (hard X-rays)

See `CONFIG_GUIDE.md` for complete parameter reference.

## Example Configurations

Template configurations for common analyses:

```bash
examples/
├── config_qpo_analysis.yaml      # QPO detection (125 μs time resolution)
├── config_high_energy.yaml       # Hard X-ray analysis
└── config_soft_thermal.yaml      # Soft/thermal state analysis
```

## Module Architecture

**Core Modules** (01-09)
1. Download - S3 data acquisition with region optimization
2. Preparation - pcaprepobsid execution
3. Organization - FITS file cataloging
4. Bitmasks - Automated distribution
5. Filtering - GTI creation with maketime
6. Extraction - Event extraction via seextrct
7. Lightcurves - STD1/STD2 generation
8. Spectra - Source, background, and response extraction
9. PDS - Power density spectrum computation

**Advanced Modules** (01-04)
1. Color-Color Analysis - Multi-energy lightcurve extraction and visualization
2. XSPEC Fitting - Automated spectral model fitting with predefined models
3. Xenon Mode - Complete Good Xenon preprocessing pipeline
4. Plotting - Batch lightcurve visualization utilities

## Documentation

- **README.md** - This file
- **CONFIG_GUIDE.md** - Comprehensive parameter reference
- **CONFIG_QUICK_REF.md** - Quick reference card
- **DUAL_MODE_GUIDE.md** - Interactive vs programmatic usage
- **examples/** - Complete workflow examples

## Citation

If you use AutoRXTE in your research, please cite:

```bibtex
@software{autorxte2025,
  author = {{AutoRXTE Development Team}},
  title = {AutoRXTE: Automated RXTE Data Analysis Pipeline},
  year = {2025},
  url = {https://github.com/WizardEternal/AutoRXTE}
}
```

## Contributing

Contributions are welcome. Please open an issue or submit a pull request on GitHub.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- NASA HEASARC for RXTE data archival and access
- HEASoft development team
- RXTE mission team and data providers

## Version

**v1.1.0** - Complete workflow with advanced features and global optimization

---

**Repository:** https://github.com/WizardEternal/AutoRXTE

**Issues & Support:** https://github.com/WizardEternal/AutoRXTE/issues
