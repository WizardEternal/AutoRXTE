"""
Example: How to Integrate Config System into Modules

This shows how each module should use the config system.
"""

from pathlib import Path
from autorxte.config import get_config

# ============================================================================
# EXAMPLE 1: Module using config with fallback to parameters
# ============================================================================

def extract_all_events(root_dir=None, prefix=None, token=None, bitmask=None,
                      time_bin=None, split_gti_flag=None, workers=None,
                      interactive=True):
    """Extract events using config + parameter override."""
    config = get_config()
    
    if interactive:
        # Interactive mode - prompt user
        root_dir = get_path("Root directory", Path('.'), root_dir)
        prefix = get_input("Prefix", config.get('extraction.prefix', 'event'), prefix)
        token = get_input("Token", config.get('extraction.token', 'e'), token)
        # ... etc
    else:
        # Non-interactive - use params OR config
        root_dir = root_dir or Path('.')
        prefix = prefix or config.get('extraction.prefix', 'event')
        token = token or config.get('extraction.token', 'e')
        bitmask = bitmask or config.get('extraction.bitmask', 'bitmask_event')
        time_bin = time_bin or config.get('extraction.time_bin', 0.004)
        split_gti_flag = split_gti_flag if split_gti_flag is not None else config.get('extraction.split_gti', False)
        workers = workers or config.get('extraction.workers', 'auto')
    
    # Resolve 'auto' workers
    workers = config.resolve_workers(workers)
    
    # Use the values...
    print(f"Extracting with prefix={prefix}, token={token}, time_bin={time_bin}")


# ============================================================================
# EXAMPLE 2: Color-color module using config
# ============================================================================

def extract_color_ranges(root_dir=None, ranges=None, names=None, 
                        time_bin=None, workers=None, interactive=True):
    """Extract color ranges using config."""
    config = get_config()
    
    if not interactive:
        # Get from config if not provided
        if ranges is None or names is None:
            ranges, names = config.get_color_ranges()
        
        time_bin = time_bin or config.get('color_analysis.time_bin', 0.04)
        workers = config.resolve_workers(workers)
    
    print(f"Extracting ranges: {ranges}")
    print(f"Names: {names}")
    print(f"Time bin: {time_bin} sec")


# ============================================================================
# EXAMPLE 3: XSPEC module using model config
# ============================================================================

def fit_all_spectra(root_dir=None, model=None, energy_range=None, 
                   save_plots=None, interactive=True):
    """Fit spectra using XSPEC model from config."""
    config = get_config()
    
    if not interactive:
        # Get model from config
        if model is None:
            model_name = config.get('xspec.default_model', 'diskbb_pexrav')
            model_config = config.get_xspec_model(model_name)
            model = model_config.get('expression', 'tbabs(diskbb + pexrav)')
        
        # Get energy range from config
        if energy_range is None:
            emin = config.get('xspec.energy_range.min', 3.0)
            emax = config.get('xspec.energy_range.max', 30.0)
            energy_range = (emin, emax)
        
        save_plots = save_plots if save_plots is not None else config.get('xspec.save_plots', True)
    
    print(f"Fitting with model: {model}")
    print(f"Energy range: {energy_range} keV")


# ============================================================================
# EXAMPLE 4: PDS module using all config options
# ============================================================================

def compute_pds(root_dir=None, lc_file=None, binning=None, rebin=None,
               max_bins=None, window=None, norm=None, workers=None,
               interactive=True):
    """Compute PDS using config parameters."""
    config = get_config()
    
    if not interactive:
        lc_file = lc_file or config.get('pds.input_lightcurve', 'event.lc')
        binning = binning or config.get('pds.binning', '-1')
        rebin = rebin or config.get('pds.rebin', '-1.03')
        max_bins = max_bins or config.get('pds.max_bins', 8192)
        window = window or config.get('pds.window', 'none')
        norm = norm or config.get('pds.norm', -2)
        workers = config.resolve_workers(workers)
    
    print(f"PDS: binning={binning}, rebin={rebin}, norm={norm}")


# ============================================================================
# EXAMPLE 5: Using variant configs
# ============================================================================

def compute_pds_high_freq(root_dir=None):
    """Compute high-frequency PDS using variant config."""
    config = get_config()
    
    # Get high-freq variant parameters
    variant = config.get_section('powspec_variants.high_freq')
    
    compute_pds(
        root_dir=root_dir,
        binning=variant.get('binning', '-1'),
        max_bins=variant.get('max_bins', 8192),
        rebin=variant.get('rebin', '-1.03'),
        interactive=False
    )


# ============================================================================
# EXAMPLE 6: GTI filter expression
# ============================================================================

def create_gti_filters(root_dir=None, filter_expression=None, interactive=True):
    """Create GTI with filter from config."""
    config = get_config()
    
    if not interactive:
        filter_expression = filter_expression or config.get_filter_expression()
    
    print(f"Using filter: {filter_expression}")


# ============================================================================
# HOW TO USE IN YOUR WORKFLOW
# ============================================================================

if __name__ == '__main__':
    from autorxte.config import load_config
    
    # Method 1: Use default config
    extract_all_events(interactive=False)  # Uses config values
    
    # Method 2: Load custom config
    load_config('my_custom_config.yaml')
    extract_all_events(interactive=False)  # Uses custom config
    
    # Method 3: Override config with parameters
    extract_all_events(
        prefix='my_event',
        time_bin=0.01,
        workers=8,
        interactive=False
    )  # Parameters override config
    
    # Method 4: Use color ranges from config
    extract_color_ranges(interactive=False)  # Gets ranges from config
    
    # Method 5: Use XSPEC model from config
    fit_all_spectra(interactive=False)  # Gets model from config
