"""Example: Complete RXTE analysis workflow."""

from pathlib import Path
from autorxte.core import (
    search_and_download,
    prepare_all_obsids,
    copy_bitmask_to_results,
    extract_all_events,
    generate_lightcurves,
    extract_spectra,
    compute_pds
)

# Set parameters
source = "Cyg X-1"
output_dir = Path("./cyg_x1_data")
bitmask = Path("./bitmasks/bitmask_event")

# 1. Download top 5 observations
# First time: Will prompt for region selection (auto-detect recommended)
# Saves fastest region to ~/.autorxte/download_region.json
print("Step 1: Downloading data...")
search_and_download(
    source=source,
    top_n=5,
    output_dir=output_dir,
    interactive=False  # Set True to get region selection prompt
)

# 2. Prepare observations
print("\nStep 2: Preparing observations...")
data_dir = output_dir / "download_RXTE_CygX-1"
prepare_all_obsids(
    root_dir=data_dir,
    workers=4,
    interactive=False
)

# 3. Copy bitmasks
print("\nStep 3: Copying bitmasks...")
copy_bitmask_to_results(
    root_dir=data_dir,
    bitmask_path=bitmask,
    interactive=False
)

# 4. Extract events
print("\nStep 4: Extracting events...")
extract_all_events(
    root_dir=data_dir,
    workers=4,
    interactive=False
)

# 5. Generate lightcurves
print("\nStep 5: Generating lightcurves...")
generate_lightcurves(
    root_dir=data_dir,
    interactive=False
)

# 6. Extract spectra
print("\nStep 6: Extracting spectra...")
extract_spectra(
    root_dir=data_dir,
    interactive=False
)

# 7. Compute PDS
print("\nStep 7: Computing PDS...")
compute_pds(
    root_dir=data_dir,
    interactive=False
)

print("\n✓ Complete workflow finished!")
