"""08 - Spectral Extraction.

This module uses pcaextspect2 to extract spectra and generate:
- src.pha: source spectrum
- bkg.pha: background spectrum
- rsp.pha: response matrix

Note: Background and response are generated automatically by pcaextspect2,
not as separate processing steps.
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input

logger = logging.getLogger(__name__)

def extract_spectra(root_dir: Optional[Path] = None, energy_channels: Optional[str] = None,
                   interactive: bool = True):
    """
    Extract spectra using pcaextspect2.
    
    Generates three output files per observation:
    - src.pha: source spectrum
    - bkg.pha: background spectrum  
    - rsp.pha: response matrix
    """
    require_heasoft_tool('pcaextspect2')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        energy_channels = get_input("Energy channels", "ALL", energy_channels)
    else:
        root_dir = root_dir or Path('.')
        energy_channels = energy_channels or "ALL"
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis_dir = results_dir / 'Analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        script_lines = [
            f"@{results_dir}/FP_dtstd2.lis",
            f"@{results_dir}/FP_dtbkg2.lis",
            f"{analysis_dir}/src.pha",
            f"{analysis_dir}/bkg.pha",
            f"{analysis_dir}/good.gti",
            "2",
            energy_channels,
            f"{analysis_dir}/rsp.pha",
            f"@{results_dir}/FP_xtefilt.lis",
        ]
        
        script_file = results_dir / 'script_spec.txt'
        script_file.write_text("\n".join(script_lines) + "\n")
        
        try:
            with script_file.open('r') as sf:
                subprocess.run(['pcaextspect2'], stdin=sf, check=True, capture_output=True)
            logger.info(f"✓ {results_dir.name}")
            count += 1
            script_file.unlink()
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {results_dir.name}: {e.stderr.decode()}")
    
    logger.info(f"Complete: {count} spectra extracted")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--channels', default='ALL')
    args = parser.parse_args()
    extract_spectra(args.directory, args.channels, interactive=args.directory is None)
