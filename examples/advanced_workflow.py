#!/usr/bin/env python3
"""
Advanced RXTE Analysis Example

This example demonstrates the advanced features:
- Color-color diagram analysis
- XSPEC automated spectral fitting
- Lightcurve plotting
"""

from pathlib import Path
from autorxte.core import *
from autorxte.advanced import *

# Configuration
data_dir = Path("./rxte_data")

print("=" * 60)
print("Advanced RXTE Analysis Workflow")
print("=" * 60)

# Assume core workflow already completed:
# 1-8: download, prepare, organize, bitmask, filter, extract, lightcurves, spectra
# (See basic_workflow.py for the complete core workflow)

# ============================================================================
# ADVANCED FEATURE 1: Color-Color Diagram Analysis
# ============================================================================
print("\n1. Color-Color Diagram Analysis")
print("-" * 60)

# Extract lightcurves in 3 energy ranges
print("Extracting color lightcurves in energy ranges...")
extract_color_ranges(
    root_dir=data_dir,
    token='e',                           # E-token mode
    bitmask='bitmask_event',
    ranges=['0-13', '14-35', '36-255'],  # Soft, medium, hard
    names=['soft', 'medium', 'hard'],
    workers=4,
    interactive=False
)

# Create color-color diagrams
print("\nPlotting color-color diagrams...")
plot_color_diagrams(
    root_dir=data_dir,
    color_names=['soft', 'medium', 'hard'],
    bin_size='-1',  # Auto binning
    workers=4,
    interactive=False
)

print("✅ Color-color diagrams created in Analysis/ccd_plot.png")

# ============================================================================
# ADVANCED FEATURE 2: XSPEC Automated Spectral Fitting
# ============================================================================
print("\n2. XSPEC Automated Spectral Fitting")
print("-" * 60)

print("Fitting all spectra with disk + power-law reflection model...")
fit_all_spectra(
    root_dir=data_dir,
    model='tbabs(diskbb + pexrav)',  # Black hole disk + reflection
    energy_range=(3.0, 30.0),        # 3-30 keV
    save_plots=True,
    output_csv=data_dir / 'xspec_results.csv',
    interactive=False
)

print("✅ Spectral fits complete!")
print(f"   - Best-fit models saved in Analysis/bestfit.xcm")
print(f"   - Plots saved in Analysis/spectralfit.png")
print(f"   - Results table: {data_dir / 'xspec_results.csv'}")

# ============================================================================
# ADVANCED FEATURE 3: Lightcurve Plotting
# ============================================================================
print("\n3. Lightcurve Plotting")
print("-" * 60)

# Plot all event lightcurves
print("Creating plots for all event lightcurves...")
plot_all_lightcurves(
    root_dir=data_dir,
    lc_pattern='event.lc',
    bin_size='1',      # 1 second bins
    output_format='png',
    workers=4,
    interactive=False
)

print("✅ Lightcurve plots created in Analysis/event.png")

# ============================================================================
# BONUS: Quick Single Plot
# ============================================================================
print("\n4. Quick Plot Example")
print("-" * 60)

# Find first event.lc file and plot it
for results_dir in data_dir.glob('*-results'):
    event_lc = results_dir / 'Analysis' / 'event.lc'
    if event_lc.exists():
        print(f"Quick plotting: {event_lc}")
        plot_file = quick_plot(str(event_lc), bin_size='0.1')
        print(f"✅ Plot saved: {plot_file}")
        break

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
print("Advanced Analysis Complete!")
print("=" * 60)
print("\nGenerated outputs:")
print("  📊 Color-color diagrams: */Analysis/ccd_plot.png")
print("  📈 Spectral fits: */Analysis/spectralfit.png")
print("  📉 Lightcurve plots: */Analysis/event.png")
print("  📁 XSPEC results: xspec_results.csv")
print("\nNext steps:")
print("  - Examine color-color diagrams for spectral state evolution")
print("  - Review XSPEC fit parameters in bestfit.xcm files")
print("  - Analyze timing properties using the PDS from core workflow")
print("  - Correlate spectral and timing behavior")

print("\n🎉 Full RXTE analysis pipeline complete!")
