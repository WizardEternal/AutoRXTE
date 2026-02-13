"""Core processing modules."""

from autorxte.core.download_01 import (
    search_and_download, 
    find_fastest_region, 
    save_preferred_region,
    load_preferred_region
)
from autorxte.core.preparation_02 import prepare_all_obsids
from autorxte.core.organization_03 import organize_fits_files
from autorxte.core.bitmasks_04 import copy_bitmask_to_results
from autorxte.core.filtering_05 import create_gti_filters
from autorxte.core.extraction_06 import extract_all_events
from autorxte.core.lightcurves_07 import generate_lightcurves
from autorxte.core.spectra_08 import extract_spectra
from autorxte.core.pds_09 import compute_pds

__all__ = [
    'search_and_download',
    'find_fastest_region',
    'save_preferred_region',
    'load_preferred_region',
    'prepare_all_obsids',
    'organize_fits_files',
    'copy_bitmask_to_results',
    'create_gti_filters',
    'extract_all_events',
    'generate_lightcurves',
    'extract_spectra',
    'compute_pds',
]
