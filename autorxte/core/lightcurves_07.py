"""07 - Light Curve Generation."""
import logging
import subprocess
from pathlib import Path
from typing import Optional, Literal
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_choice, get_input

logger = logging.getLogger(__name__)

def extract_std1_lightcurves(root_dir: Optional[Path] = None, bin_size: Optional[str] = None,
                             interactive: bool = True):
    """Generate STD1 light curves using pcaextlc1."""
    require_heasoft_tool('pcaextlc1')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        bin_size = get_input("Bin size (seconds)", "0.125", bin_size)
    else:
        root_dir = root_dir or Path('.')
        bin_size = bin_size or "0.125"
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis_dir = results_dir / 'Analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        script_lines = [
            f"@{results_dir}/FP_dtstd1.lis",
            f"@{results_dir}/FP_dtbkg2.lis",
            f"{analysis_dir}/std1.lc",
            f"{analysis_dir}/good.gti",
            "2",
            bin_size,
        ]
        
        script_file = results_dir / 'script_std1lc.txt'
        script_file.write_text("\n".join(script_lines) + "\n")
        
        try:
            with script_file.open('r') as sf:
                subprocess.run(['pcaextlc1'], stdin=sf, check=True, capture_output=True)
            logger.info(f"✓ {results_dir.name}")
            count += 1
            script_file.unlink()
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {results_dir.name}: {e.stderr.decode()}")
    
    logger.info(f"Complete: {count} lightcurves generated")

def extract_std2_lightcurves(root_dir: Optional[Path] = None, energy_channels: Optional[str] = None,
                             time_bins: Optional[str] = None, interactive: bool = True):
    """Generate STD2 light curves using pcaextlc2."""
    require_heasoft_tool('pcaextlc2')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        energy_channels = get_input("Energy channels", "ALL", energy_channels)
        time_bins = get_input("Number of time bins", "16", time_bins)
    else:
        root_dir = root_dir or Path('.')
        energy_channels = energy_channels or "ALL"
        time_bins = time_bins or "16"
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis_dir = results_dir / 'Analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        script_lines = [
            f"@{results_dir}/FP_dtstd2.lis",
            f"@{results_dir}/FP_dtbkg2.lis",
            f"{analysis_dir}/light.lc",
            f"{analysis_dir}/good.gti",
            "2",
            energy_channels,
            time_bins,
        ]
        
        script_file = results_dir / 'script_std2lc.txt'
        script_file.write_text("\n".join(script_lines) + "\n")
        
        try:
            with script_file.open('r') as sf:
                subprocess.run(['pcaextlc2'], stdin=sf, check=True, capture_output=True)
            logger.info(f"✓ {results_dir.name}")
            count += 1
            script_file.unlink()
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {results_dir.name}: {e.stderr.decode()}")
    
    logger.info(f"Complete: {count} lightcurves generated")

def generate_lightcurves(root_dir: Optional[Path] = None, lc_type: Optional[Literal['std1', 'std2']] = None,
                        interactive: bool = True):
    """Generate light curves (STD1 or STD2 mode)."""
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        lc_type = get_choice("Light curve type", ['std1', 'std2'], lc_type)
    else:
        root_dir = root_dir or Path('.')
        lc_type = lc_type or 'std2'
    
    if lc_type == 'std1':
        extract_std1_lightcurves(root_dir, interactive=interactive)
    else:
        extract_std2_lightcurves(root_dir, interactive=interactive)

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--type', choices=['std1', 'std2'], default='std2')
    args = parser.parse_args()
    generate_lightcurves(args.directory, args.type, interactive=args.directory is None)
