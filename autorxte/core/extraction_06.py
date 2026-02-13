"""06 - Event Extraction."""
import logging
import multiprocessing
import subprocess
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from astropy.io import fits
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_yes_no, get_int

logger = logging.getLogger(__name__)

def split_gti(gti_path: Path, sep_dir: Path) -> List[Path]:
    """Split a multi-row GTI FITS into separate files."""
    hdul = fits.open(gti_path)
    data = hdul[1].data
    nrows = len(data)
    sep_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if already split
    existing = list(sep_dir.glob("good_*.gti"))
    if len(existing) == nrows:
        return sorted(existing)
    
    out = []
    for idx, row in enumerate(data, start=1):
        cols = fits.Column(name=hdul[1].columns[0].name,
                          format=hdul[1].columns[0].format,
                          array=[row[0]])
        cols += fits.Column(name=hdul[1].columns[1].name,
                           format=hdul[1].columns[1].format,
                           array=[row[1]])
        tbl = fits.BinTableHDU.from_columns([cols], header=hdul[1].header)
        hdu = fits.HDUList([hdul[0], tbl])
        out_path = sep_dir / f"good_{idx}.gti"
        hdu.writeto(out_path, overwrite=True)
        out.append(out_path)
    hdul.close()
    return out

def run_seextrct_single(results_dir: Path, infile: str, gti_file: Path,
                       prefix: str, bitmask: str, use_ranges: bool = False, 
                       rng_field: str = "0.004") -> str:
    """Run seextrct for a single GTI file."""
    analysis = results_dir / "Analysis"
    evpath = analysis / prefix
    
    script = results_dir / f"script_{prefix}.txt"
    lines = [
        f"@{results_dir}/{infile}",
        "-",
        str(gti_file),
        str(evpath),
        f"{analysis}/{bitmask}",
        "TIME", "EVENT",
        (rng_field if use_ranges else "0.004"),
        "LIGHTCURVE", "RATE", "SUM"
    ] + (["INDEF"] * 7)
    
    script.write_text("\n".join(lines) + "\n")
    
    try:
        subprocess.run(['seextrct', 'clobber=yes'], stdin=script.open('r'), 
                      check=True, capture_output=True)
        return f"{results_dir.name}/{prefix}"
    finally:
        script.unlink(missing_ok=True)

def extract_all_events(root_dir: Optional[Path] = None, prefix: Optional[str] = None,
                      token: Optional[str] = None, bitmask: Optional[str] = None,
                      split_gti_flag: Optional[bool] = None, workers: Optional[int] = None,
                      interactive: bool = True):
    """Extract events using seextrct."""
    require_heasoft_tool('seextrct')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        token = get_input("Use (e)-token or (xenon)-token?", "e", token).lower()
        prefix = get_input("Base event name", "event", prefix)
        bitmask = get_input("Bitmask filename", "bitmask_event", bitmask)
        split_gti_flag = get_yes_no("Use separated GTI?", False, split_gti_flag)
        workers = get_int("Workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        token = (token or "e").lower()
        prefix = prefix or "event"
        bitmask = bitmask or "bitmask_event"
        split_gti_flag = split_gti_flag if split_gti_flag is not None else False
        workers = workers or multiprocessing.cpu_count()
    
    infile = 'Analysis/fits_files.god' if token == 'e' else 'Analysis/xenon_event_files.txt'
    
    tasks = []
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
            
        analysis = results_dir / "Analysis"
        gti_main = analysis / "good.gti"
        if not gti_main.exists():
            logger.warning(f"No good.gti in {results_dir.name}/Analysis")
            continue
        
        # Check bitmask exists
        if not (analysis / bitmask).exists():
            logger.warning(f"No {bitmask} in {results_dir.name}/Analysis")
            continue
        
        if split_gti_flag:
            gtis = split_gti(gti_main, results_dir / "sep_gtis")
        else:
            gtis = [gti_main]
        
        for gti in gtis:
            row = gti.stem.split('_')[-1] if split_gti_flag and gti != gti_main else ''
            evt_prefix = prefix + (f"_{row}" if row else '')
            tasks.append((results_dir, infile, gti, evt_prefix, bitmask))
    
    logger.info(f"Extracting {len(tasks)} event files with {workers} workers")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_seextrct_single, *task): task for task in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
                logger.info(f"✓ {result}")
            except Exception as e:
                task = futures[future]
                logger.error(f"✗ {task[0].name}: {e}")
    
    logger.info("Complete")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--prefix', default='event')
    parser.add_argument('--token', choices=['e', 'xenon'], default='e')
    parser.add_argument('--bitmask', default='bitmask_event')
    parser.add_argument('--split-gti', action='store_true')
    parser.add_argument('--workers', type=int)
    args = parser.parse_args()
    extract_all_events(args.directory, args.prefix, args.token, args.bitmask,
                      args.split_gti, args.workers, interactive=args.directory is None)
