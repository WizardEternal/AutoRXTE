"""XSPEC Automated Spectral Fitting.

Automate XSPEC spectral model fitting for all observations.
Supports various models and flux calculations.

Based on: newmodel_xspec_spectral.txt, flux_calculation.txt
"""
import logging
import subprocess
import csv
from pathlib import Path
from typing import Optional, Dict, List
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_float, get_yes_no

logger = logging.getLogger(__name__)

# Common black hole spectral models
MODELS = {
    'diskbb_pexrav': 'tbabs(diskbb + pexrav)',
    'diskbb_powerlaw': 'tbabs(diskbb + powerlaw)',
    'diskbb_only': 'tbabs*diskbb',
    'powerlaw_only': 'tbabs*powerlaw',
    'comptt': 'tbabs*comptt',
}

def fit_single_spectrum(results_dir: Path, model_expr: str, 
                       energy_range: tuple, save_plots: bool = True) -> Dict:
    """Fit spectrum for a single observation."""
    analysis = results_dir / "Analysis"
    
    # Check required files
    for f in ['src.pha', 'bkg.pha', 'rsp.pha']:
        if not (analysis / f).exists():
            raise FileNotFoundError(f"No {f} in {analysis}")
    
    # Create XSPEC script
    script = analysis / "xspec_fit.txt"
    lines = [
        f"da {analysis}/src.pha",
        f"{analysis}/rsp.pha",
        f"{analysis}/bkg.pha",
        f"ig **-{energy_range[0]}",
        f"ig {energy_range[1]}-**",
        "setp e",
        f"model {model_expr}",
    ]
    
    # Model-specific parameter initialization
    if 'diskbb' in model_expr and 'pexrav' in model_expr:
        # tbabs(diskbb + pexrav) - typical for BH binaries
        lines += [
            "5.5 0.05 2.0 2.00 9.0 10.0",  # nH
            "1.2 0.01 1.0 1 3.0 4.0",      # diskbb kT
            "400",                          # diskbb norm
            "2.0 0.01 1.3 1.4 3.0 4.0",   # pexrav PhoIndex
            "30",                           # pexrav foldE
            "1",                            # pexrav rel_refl
            "0 -1",                         # pexrav redshift (frozen)
            "1 -1",                         # pexrav abund (frozen)
            "1 -1",                         # pexrav Fe_abund (frozen)
            "0.25 -1",                      # pexrav cosIncl (frozen)
            "15",                           # pexrav norm
        ]
    elif 'diskbb' in model_expr and 'powerlaw' in model_expr:
        # tbabs(diskbb + powerlaw)
        lines += [
            "5.5",      # nH
            "1.2",      # diskbb kT
            "400",      # diskbb norm
            "2.0",      # powerlaw PhoIndex
            "15",       # powerlaw norm
        ]
    elif 'diskbb' in model_expr:
        # tbabs*diskbb
        lines += [
            "5.5",      # nH
            "1.2",      # diskbb kT
            "400",      # diskbb norm
        ]
    elif 'powerlaw' in model_expr:
        # tbabs*powerlaw
        lines += [
            "5.5",      # nH
            "2.0",      # powerlaw PhoIndex
            "15",       # powerlaw norm
        ]
    
    lines += [
        "fit 1000",
        f"save all {analysis}/bestfit.xcm",
    ]
    
    if save_plots:
        lines += [
            "cpd /xw",
            "pl ld chi uf euf residual",
            f"hardcopy {analysis}/spectralfit.png/png",
        ]
    
    lines.append("exit")
    
    script.write_text("\n".join(lines) + "\n")
    log_file = analysis / "xspec_fit.log"
    
    try:
        with script.open('r') as inp, log_file.open('w') as out:
            subprocess.run(['xspec'], stdin=inp, stdout=out, 
                         stderr=subprocess.STDOUT, check=True)
        
        # Parse results from log
        return parse_xspec_results(log_file, results_dir.name)
    finally:
        script.unlink(missing_ok=True)

def parse_xspec_results(log_file: Path, obsid: str) -> Dict:
    """Parse fit results from XSPEC log file."""
    results = {'obsid': obsid}
    
    with open(log_file) as f:
        content = f.read()
        
        # Extract chi-squared
        if 'Chi-Squared' in content:
            for line in content.split('\n'):
                if 'Chi-Squared' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        results['chi2'] = parts[2]
                        results['dof'] = parts[-1] if 'dof' in line else 'N/A'
                    break
    
    return results

def calculate_fluxes(results_dir: Path, energy_bands: List[tuple]) -> Dict:
    """Calculate fluxes in specified energy bands."""
    analysis = results_dir / "Analysis"
    bestfit = analysis / "bestfit.xcm"
    
    if not bestfit.exists():
        raise FileNotFoundError(f"No bestfit.xcm in {analysis}")
    
    script = analysis / "flux_calc.txt"
    lines = [
        f"@{bestfit}",
        "fit",
    ]
    
    # Calculate flux for each band
    for emin, emax in energy_bands:
        lines.append(f"flux {emin} {emax}")
    
    lines.append("exit")
    
    script.write_text("\n".join(lines) + "\n")
    log_file = analysis / "flux_calc.log"
    
    try:
        with script.open('r') as inp, log_file.open('w') as out:
            subprocess.run(['xspec'], stdin=inp, stdout=out,
                         stderr=subprocess.STDOUT, check=True)
        
        return parse_flux_results(log_file, energy_bands)
    finally:
        script.unlink(missing_ok=True)

def parse_flux_results(log_file: Path, energy_bands: List[tuple]) -> Dict:
    """Parse flux values from XSPEC log."""
    fluxes = {}
    
    with open(log_file) as f:
        content = f.read()
        
        for i, (emin, emax) in enumerate(energy_bands):
            band_name = f"flux_{emin}_{emax}"
            # Look for flux output in log
            # This is simplified - actual parsing depends on XSPEC output format
            fluxes[band_name] = "N/A"
    
    return fluxes

def fit_all_spectra(root_dir: Optional[Path] = None,
                   model: Optional[str] = None,
                   energy_range: Optional[tuple] = None,
                   save_plots: Optional[bool] = None,
                   output_csv: Optional[Path] = None,
                   interactive: bool = True):
    """Fit spectra for all observations."""
    require_heasoft_tool('xspec')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        
        print("\nAvailable models:")
        for i, (key, expr) in enumerate(MODELS.items(), 1):
            print(f"  {i}) {key}: {expr}")
        
        model_choice = get_input("Model name or number", "diskbb_pexrav", model)
        if model_choice.isdigit():
            model_key = list(MODELS.keys())[int(model_choice) - 1]
            model = MODELS[model_key]
        elif model_choice in MODELS:
            model = MODELS[model_choice]
        else:
            model = model_choice
        
        emin = get_float("Minimum energy (keV)", 3.0)
        emax = get_float("Maximum energy (keV)", 30.0)
        energy_range = (emin, emax)
        
        save_plots = get_yes_no("Save plots?", True, save_plots)
        
        output_csv = get_path("Output CSV file", Path("xspec_results.csv"), output_csv)
    else:
        root_dir = root_dir or Path('.')
        model = model or MODELS['diskbb_pexrav']
        energy_range = energy_range or (3.0, 30.0)
        save_plots = save_plots if save_plots is not None else True
        output_csv = output_csv or Path("xspec_results.csv")
    
    dirs = sorted(d for d in root_dir.glob('*-results') if d.is_dir())
    logger.info(f"Fitting {len(dirs)} spectra with model: {model}")
    
    results = []
    for results_dir in dirs:
        try:
            result = fit_single_spectrum(results_dir, model, energy_range, save_plots)
            results.append(result)
            logger.info(f"✓ {results_dir.name}")
        except Exception as e:
            logger.error(f"✗ {results_dir.name}: {e}")
            results.append({'obsid': results_dir.name, 'error': str(e)})
    
    # Save results to CSV
    if results:
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"Results saved to {output_csv}")
    
    logger.info("Complete")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='XSPEC automated fitting')
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--model', choices=list(MODELS.keys()) + ['custom'])
    parser.add_argument('--custom-model', help='Custom model expression')
    parser.add_argument('--emin', type=float, default=3.0)
    parser.add_argument('--emax', type=float, default=30.0)
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--output', type=Path, default='xspec_results.csv')
    
    args = parser.parse_args()
    
    model_expr = MODELS.get(args.model, args.custom_model) if args.model else None
    
    fit_all_spectra(args.directory, model_expr, (args.emin, args.emax),
                   not args.no_plots, args.output,
                   interactive=args.directory is None)
