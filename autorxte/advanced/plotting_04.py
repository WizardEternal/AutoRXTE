"""Lightcurve Plotting Utilities.

Simple wrappers around lcurve for quick plotting and visualization.

Based on: lcurve.txt, seplcurve.txt
"""
import logging
import subprocess
import multiprocessing
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int, get_yes_no

logger = logging.getLogger(__name__)

def plot_single_lightcurve(lc_file: Path, bin_size: str = "1",
                          max_bins: str = "10000", output_format: str = "png") -> str:
    """Plot a single lightcurve file."""
    if not lc_file.exists():
        raise FileNotFoundError(f"Lightcurve file not found: {lc_file}")
    
    analysis_dir = lc_file.parent
    output_name = lc_file.stem
    
    script = analysis_dir / f"lcurve_{output_name}.txt"
    lines = [
        "1",
        lc_file.name,
        "-",
        bin_size,
        max_bins,
        "out",
        "yes",
        "/xw",
        "line on",
        "pl",
        f"hardcopy {output_name}.{output_format}/{output_format}",
        "q"
    ]
    
    script.write_text("\n".join(lines) + "\n")
    log_file = analysis_dir / f"{output_name}_lcurve.log"
    
    try:
        with script.open('r') as inp, log_file.open('w') as out:
            subprocess.run(['lcurve'], stdin=inp, stdout=out,
                         stderr=subprocess.STDOUT, check=True)
        return str(analysis_dir / f"{output_name}.{output_format}")
    finally:
        script.unlink(missing_ok=True)

def plot_all_lightcurves(root_dir: Optional[Path] = None,
                        lc_pattern: Optional[str] = None,
                        bin_size: Optional[str] = None,
                        output_format: Optional[str] = None,
                        workers: Optional[int] = None,
                        interactive: bool = True):
    """Plot all lightcurves matching pattern."""
    require_heasoft_tool('lcurve')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        lc_pattern = get_input("Lightcurve pattern", "*.lc", lc_pattern)
        bin_size = get_input("Bin size (seconds)", "1", bin_size)
        output_format = get_input("Output format (png/eps)", "png", output_format)
        workers = get_int("Workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        lc_pattern = lc_pattern or "*.lc"
        bin_size = bin_size or "1"
        output_format = output_format or "png"
        workers = workers or multiprocessing.cpu_count()
    
    # Find all matching lightcurve files
    lc_files = []
    for results_dir in root_dir.glob('*-results'):
        analysis = results_dir / "Analysis"
        if analysis.is_dir():
            lc_files.extend(analysis.glob(lc_pattern))
    
    if not lc_files:
        logger.warning(f"No lightcurve files matching '{lc_pattern}' found")
        return
    
    logger.info(f"Plotting {len(lc_files)} lightcurves with {workers} workers")
    
    def plot_task(lc_file: Path) -> str:
        output = plot_single_lightcurve(lc_file, bin_size, "10000", output_format)
        return f"{lc_file.parent.parent.name}/{lc_file.name}"
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(plot_task, lc): lc for lc in lc_files}
        for future in as_completed(futures):
            lc = futures[future]
            try:
                result = future.result()
                logger.info(f"✓ {result}")
            except Exception as e:
                logger.error(f"✗ {lc.name}: {e}")
    
    logger.info("Complete")

def plot_multiple_lightcurves(lc_files: List[Path], output_name: str,
                             bin_size: str = "-1", output_format: str = "png"):
    """Plot multiple lightcurves on the same plot (for comparison)."""
    if not lc_files:
        raise ValueError("No lightcurve files provided")
    
    # All files should be in same directory
    analysis_dir = lc_files[0].parent
    
    script = analysis_dir / f"lcurve_multi_{output_name}.txt"
    lines = [
        str(len(lc_files))
    ] + [lc.name for lc in lc_files] + [
        "-",
        bin_size,
        "2000000",
        "out",
        "yes",
        "/xw",
        "1",
        f"hardcopy {output_name}.{output_format}/{output_format}",
        "q"
    ]
    
    script.write_text("\n".join(lines) + "\n")
    log_file = analysis_dir / f"{output_name}_lcurve.log"
    
    try:
        with script.open('r') as inp, log_file.open('w') as out:
            subprocess.run(['lcurve'], stdin=inp, stdout=out,
                         stderr=subprocess.STDOUT, check=True)
        logger.info(f"✓ Created {output_name}.{output_format}")
        return str(analysis_dir / f"{output_name}.{output_format}")
    finally:
        script.unlink(missing_ok=True)

def quick_plot(lc_file_path: str, bin_size: str = "1"):
    """Quick plot a single lightcurve (convenience function)."""
    lc_file = Path(lc_file_path)
    output = plot_single_lightcurve(lc_file, bin_size)
    logger.info(f"Plot saved to: {output}")
    return output

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='Lightcurve plotting utilities')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Plot single
    single_parser = subparsers.add_parser('single', help='Plot single lightcurve')
    single_parser.add_argument('file', type=Path, help='Lightcurve file')
    single_parser.add_argument('--bin-size', default='1')
    single_parser.add_argument('--format', choices=['png', 'eps'], default='png')
    
    # Plot all
    all_parser = subparsers.add_parser('all', help='Plot all lightcurves')
    all_parser.add_argument('--directory', type=Path)
    all_parser.add_argument('--pattern', default='*.lc')
    all_parser.add_argument('--bin-size', default='1')
    all_parser.add_argument('--format', choices=['png', 'eps'], default='png')
    all_parser.add_argument('--workers', type=int)
    
    # Plot multiple (comparison)
    multi_parser = subparsers.add_parser('multi', help='Plot multiple lightcurves together')
    multi_parser.add_argument('files', nargs='+', type=Path, help='Lightcurve files')
    multi_parser.add_argument('--output', default='comparison')
    multi_parser.add_argument('--bin-size', default='-1')
    multi_parser.add_argument('--format', choices=['png', 'eps'], default='png')
    
    args = parser.parse_args()
    
    if args.command == 'single':
        plot_single_lightcurve(args.file, args.bin_size, "10000", args.format)
    elif args.command == 'all':
        plot_all_lightcurves(args.directory, args.pattern, args.bin_size,
                           args.format, args.workers, 
                           interactive=args.directory is None)
    elif args.command == 'multi':
        plot_multiple_lightcurves(args.files, args.output, args.bin_size, args.format)
    else:
        parser.print_help()
