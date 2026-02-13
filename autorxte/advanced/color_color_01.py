"""Color-Color Diagram Analysis.

Extract lightcurves in multiple energy ranges and create color-color diagrams
for tracking spectral state evolution.

Based on: ranged_seextrct_Etoken.txt, ranged_seextrct_xenon.txt, CD.txt
"""
import logging
import subprocess
import multiprocessing
from pathlib import Path
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int, get_yes_no

logger = logging.getLogger(__name__)

DEFAULT_RANGES = ['0-13', '14-35', '36-255']
DEFAULT_NAMES = ['soft', 'medium', 'hard']

def extract_color_range(results_dir: Path, infile: str, gti_file: Path, 
                       color_name: str, energy_range: str, bitmask: str) -> str:
    """Extract lightcurve for a single energy range."""
    analysis = results_dir / "Analysis"
    
    script = results_dir / f"script_color_{color_name}.txt"
    lines = [
        f"@{results_dir}/{infile}",
        "-",
        str(gti_file),
        f"{analysis}/{color_name}",
        f"{analysis}/{bitmask}",
        "TIME", "EVENT",
        "0.04",
        "LIGHTCURVE", "RATE", "SUM"
    ] + ["INDEF"] * 5 + [energy_range, "INDEF"]
    
    script.write_text("\n".join(lines) + "\n")
    
    try:
        subprocess.run(['seextrct', 'clobber=yes'], stdin=script.open('r'),
                      check=True, capture_output=True)
        return f"{results_dir.name}/{color_name}.lc"
    finally:
        script.unlink(missing_ok=True)

def extract_color_ranges(root_dir: Optional[Path] = None,
                        token: Optional[str] = None,
                        bitmask: Optional[str] = None,
                        ranges: Optional[List[str]] = None,
                        names: Optional[List[str]] = None,
                        workers: Optional[int] = None,
                        interactive: bool = True):
    """Extract lightcurves in multiple energy ranges."""
    require_heasoft_tool('seextrct')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        token = get_input("Token type (e/xenon)", "e", token).lower()
        bitmask = get_input("Bitmask filename", "bitmask", bitmask)
        
        n_ranges = get_int("Number of energy ranges", 3, len(ranges) if ranges else None)
        ranges = []
        names = []
        for i in range(n_ranges):
            default_range = DEFAULT_RANGES[i] if i < len(DEFAULT_RANGES) else f"{i*10}-{(i+1)*10}"
            default_name = DEFAULT_NAMES[i] if i < len(DEFAULT_NAMES) else f"color{i+1}"
            ranges.append(get_input(f"Range {i+1} (e.g., 0-13)", default_range))
            names.append(get_input(f"Name {i+1}", default_name))
        
        workers = get_int("Workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        token = (token or "e").lower()
        bitmask = bitmask or "bitmask"
        ranges = ranges or DEFAULT_RANGES
        names = names or DEFAULT_NAMES
        workers = workers or multiprocessing.cpu_count()
    
    if len(ranges) != len(names):
        raise ValueError("Number of ranges must match number of names")
    
    infile = 'Analysis/fits_files.god' if token == 'e' else 'Analysis/xenon_event_files.txt'
    
    tasks = []
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis = results_dir / "Analysis"
        gti_file = analysis / "good.gti"
        
        if not gti_file.exists():
            logger.warning(f"No good.gti in {results_dir.name}/Analysis")
            continue
        
        if not (analysis / bitmask).exists():
            logger.warning(f"No {bitmask} in {results_dir.name}/Analysis")
            continue
        
        for color_name, energy_range in zip(names, ranges):
            tasks.append((results_dir, infile, gti_file, color_name, energy_range, bitmask))
    
    logger.info(f"Extracting {len(tasks)} color lightcurves with {workers} workers")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(extract_color_range, *task): task for task in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
                logger.info(f"✓ {result}")
            except Exception as e:
                task = futures[future]
                logger.error(f"✗ {task[0].name}/{task[3]}: {e}")
    
    logger.info("Complete")

def plot_color_diagrams(root_dir: Optional[Path] = None,
                       color_names: Optional[List[str]] = None,
                       bin_size: Optional[str] = None,
                       workers: Optional[int] = None,
                       interactive: bool = True):
    """Plot color-color diagrams using lcurve."""
    require_heasoft_tool('lcurve')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        n_colors = get_int("Number of colors", 3, len(color_names) if color_names else None)
        color_names = []
        for i in range(n_colors):
            default = DEFAULT_NAMES[i] if i < len(DEFAULT_NAMES) else f"color{i+1}"
            color_names.append(get_input(f"Color {i+1} name", default))
        bin_size = get_input("Bin size (seconds, -1 for auto)", "-1", bin_size)
        workers = get_int("Workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        color_names = color_names or DEFAULT_NAMES
        bin_size = bin_size or "-1"
        workers = workers or multiprocessing.cpu_count()
    
    def plot_single_diagram(results_dir: Path) -> str:
        analysis = results_dir / "Analysis"
        
        # Check if all color files exist
        color_files = [f"{name}.lc" for name in color_names]
        for cf in color_files:
            if not (analysis / cf).exists():
                raise FileNotFoundError(f"No {cf} in {analysis}")
        
        script = analysis / "lcurve_ccd.txt"
        lines = [
            str(len(color_files))
        ] + color_files + [
            "-",
            bin_size,
            "2000000",
            "out",
            "yes",
            "/xw",
            "1",
            f"hardcopy ccd_plot.png/png",
            "q"
        ]
        
        script.write_text("\n".join(lines) + "\n")
        log_file = analysis / "ccd_lcurve.txt"
        
        try:
            with script.open('r') as inp, log_file.open('w') as out:
                subprocess.run(['lcurve'], stdin=inp, stdout=out, 
                             stderr=subprocess.STDOUT, check=True)
            return results_dir.name
        finally:
            script.unlink(missing_ok=True)
    
    dirs = sorted(d for d in root_dir.glob('*-results') if d.is_dir())
    logger.info(f"Plotting {len(dirs)} color-color diagrams with {workers} workers")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(plot_single_diagram, d): d for d in dirs}
        for future in as_completed(futures):
            d = futures[future]
            try:
                result = future.result()
                logger.info(f"✓ {result}")
            except Exception as e:
                logger.error(f"✗ {d.name}: {e}")
    
    logger.info("Complete")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='Color-color diagram analysis')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Extract subcommand
    extract_parser = subparsers.add_parser('extract', help='Extract color ranges')
    extract_parser.add_argument('--directory', type=Path)
    extract_parser.add_argument('--token', choices=['e', 'xenon'], default='e')
    extract_parser.add_argument('--bitmask', default='bitmask')
    extract_parser.add_argument('--ranges', nargs='+', default=DEFAULT_RANGES)
    extract_parser.add_argument('--names', nargs='+', default=DEFAULT_NAMES)
    extract_parser.add_argument('--workers', type=int)
    
    # Plot subcommand
    plot_parser = subparsers.add_parser('plot', help='Plot color-color diagrams')
    plot_parser.add_argument('--directory', type=Path)
    plot_parser.add_argument('--colors', nargs='+', default=DEFAULT_NAMES)
    plot_parser.add_argument('--bin-size', default='-1')
    plot_parser.add_argument('--workers', type=int)
    
    args = parser.parse_args()
    
    if args.command == 'extract':
        extract_color_ranges(args.directory, args.token, args.bitmask,
                           args.ranges, args.names, args.workers,
                           interactive=args.directory is None)
    elif args.command == 'plot':
        plot_color_diagrams(args.directory, args.colors, args.bin_size,
                          args.workers, interactive=args.directory is None)
    else:
        parser.print_help()
