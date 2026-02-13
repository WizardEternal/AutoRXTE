"""Advanced RXTE analysis features."""

from autorxte.advanced.color_color_01 import extract_color_ranges, plot_color_diagrams
from autorxte.advanced.xspec_fit_02 import fit_all_spectra
from autorxte.advanced.xenon_mode_03 import (
    create_xenon_god_files,
    move_xenon_god_files,
    run_make_se,
    create_xenon_event_lists,
    xenon_complete_workflow
)
from autorxte.advanced.plotting_04 import (
    plot_single_lightcurve,
    plot_all_lightcurves,
    plot_multiple_lightcurves,
    quick_plot
)

__all__ = [
    'extract_color_ranges',
    'plot_color_diagrams',
    'fit_all_spectra',
    'create_xenon_god_files',
    'move_xenon_god_files',
    'run_make_se',
    'create_xenon_event_lists',
    'xenon_complete_workflow',
    'plot_single_lightcurve',
    'plot_all_lightcurves',
    'plot_multiple_lightcurves',
    'quick_plot',
]
