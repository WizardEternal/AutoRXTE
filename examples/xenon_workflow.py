#!/usr/bin/env python3
"""
Xenon Mode Complete Workflow Example

This example shows how to process Good Xenon mode data end-to-end.
"""

from pathlib import Path
from autorxte.core import *
from autorxte.advanced import xenon_complete_workflow

# Configuration
data_dir = Path("./rxte_xenon_data")
bitmask_xenon = Path("./bitmasks/bitmask_xenon")

print("=" * 60)
print("RXTE Xenon Mode Complete Workflow")
print("=" * 60)

# ============================================================================
# STEP 1-2: Download and Prepare (Same as E-token mode)
# ============================================================================
print("\n1. Download RXTE data")
print("-" * 60)

search_and_download(
    source="GX 339-4",
    top_n=5,
    output_dir=data_dir,
    interactive=False
)

print("\n2. Prepare observations")
print("-" * 60)

prepare_all_obsids(
    root_dir=data_dir,
    workers=4,
    interactive=False
)

# ============================================================================
# STEP 3: Complete Xenon Mode Preprocessing
# ============================================================================
print("\n3. Xenon Mode Preprocessing")
print("-" * 60)

# This runs the complete Xenon workflow:
# - Creates xenon_files.god from FITS files
# - Moves to Analysis directories
# - Runs make_se to generate Xenon event files
# - Creates xenon_event_files.txt lists

xenon_complete_workflow(
    root_dir=data_dir,
    run_make_se_flag=True,  # Set False to skip make_se if already done
    interactive=False
)

# ============================================================================
# STEP 4-5: Bitmasks and GTI (Same as E-token mode)
# ============================================================================
print("\n4. Copy Xenon bitmasks")
print("-" * 60)

copy_bitmask_to_results(
    root_dir=data_dir,
    bitmask_path=bitmask_xenon,
    overwrite=True,
    interactive=False
)

print("\n5. Create GTI filters")
print("-" * 60)

create_gti_filters(
    root_dir=data_dir,
    interactive=False
)

# ============================================================================
# STEP 6: Extract Xenon Events
# ============================================================================
print("\n6. Extract Xenon mode events")
print("-" * 60)

# Use token='xenon' to use xenon_event_files.txt
extract_all_events(
    root_dir=data_dir,
    prefix="event",
    token="xenon",              # ← Important: Use Xenon token
    bitmask="bitmask_xenon",    # ← Xenon-specific bitmask
    split_gti_flag=False,
    workers=4,
    interactive=False
)

# ============================================================================
# STEP 7-9: Standard Products (Same as E-token mode)
# ============================================================================
print("\n7. Generate lightcurves")
print("-" * 60)

generate_lightcurves(
    root_dir=data_dir,
    lc_type='std2',
    interactive=False
)

print("\n8. Extract spectra")
print("-" * 60)

extract_spectra(
    root_dir=data_dir,
    energy_channels='ALL',
    interactive=False
)

print("\n9. Generate PDS")
print("-" * 60)

compute_pds(
    root_dir=data_dir,
    lc_file="event.lc",
    binning="-1",
    rebin="-1.03",
    workers=4,
    interactive=False
)

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
print("Xenon Mode Workflow Complete!")
print("=" * 60)
print("\nGenerated outputs (per observation):")
print("  📁 xenon_files.god - List of Xenon FITS files")
print("  📁 xenon_event_files.txt - List of generated event files")
print("  📊 event.lc - Xenon mode lightcurve")
print("  📊 std1.lc, light.lc - Standard mode lightcurves")
print("  📈 src.pha, bkg.pha, rsp.pha - Spectral products")
print("  📉 pds.png, pds-src.pha - Power spectrum")
print("\n🎉 Xenon mode analysis complete!")

# ============================================================================
# Alternative: Run Xenon Steps Individually
# ============================================================================
print("\n" + "=" * 60)
print("Alternative: Running Xenon Steps Individually")
print("=" * 60)
print("\nYou can also run each step separately:")
print("""
from autorxte.advanced import (
    create_xenon_god_files,
    move_xenon_god_files,
    run_make_se,
    create_xenon_event_lists
)

# Step by step:
create_xenon_god_files(data_dir, interactive=False)
move_xenon_god_files(data_dir, interactive=False)
run_make_se(data_dir, output_root='event', interactive=False)
create_xenon_event_lists(data_dir, pattern='xenon_event_gx*', interactive=False)
""")
