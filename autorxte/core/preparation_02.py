"""02 - Observation Preparation with pcaprepobsid."""
import logging
import subprocess
import multiprocessing
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_int, get_yes_no

logger = logging.getLogger(__name__)

def prepare_single_obsid(obsid_dir: Path) -> str:
    """Prepare single observation."""
    obsid = obsid_dir.name
    outdir = obsid_dir.parent / f"{obsid}-results"
    try:
        subprocess.run(['pcaprepobsid', f'indir={obsid_dir}', f'outdir={outdir}'],
                      check=True, capture_output=True)
        logger.info(f"✓ {obsid}")
        return obsid
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ {obsid}: {e.stderr}")
        raise

def prepare_all_obsids(root_dir: Optional[Path] = None, workers: Optional[int] = None,
                       skip_existing: Optional[bool] = None, interactive: bool = True):
    """Prepare all observations. Interactive or with arguments."""
    require_heasoft_tool('pcaprepobsid')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no("Skip existing results?", True, skip_existing)
    else:
        root_dir = root_dir or Path('.')
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True
    
    obs_dirs = []
    for entry in root_dir.iterdir():
        if entry.is_dir() and any(c.isdigit() for c in entry.name):
            results_dir = root_dir / f"{entry.name}-results"
            if skip_existing and results_dir.exists():
                logger.info(f"Skipping {entry.name}")
                continue
            obs_dirs.append(entry)
    
    logger.info(f"Preparing {len(obs_dirs)} observations")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(prepare_single_obsid, d): d for d in obs_dirs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error: {e}")
    
    logger.info("Complete")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    prepare_all_obsids(args.directory, args.workers, interactive=not args.no_interactive)
