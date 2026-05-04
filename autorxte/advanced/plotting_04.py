"""Lightcurve Plotting Utilities.

Wrappers around the FTOOLS `lcurve` for quick plotting / hardcopy export.
Plot device defaults to /null so the module runs without DISPLAY.

Note: PGPLOT's hardcopy-to-PNG behaviour through lcurve's stdin scripts is
finicky and version-dependent; getting an actual PNG out reliably may
require manual lcurve sessions on some systems. The .lc data itself is
the primary downstream artefact and is unaffected.
"""
import logging
import multiprocessing
import re
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from autorxte.utils import run_heasoft_pty, HEASoftToolError, require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def plot_single_lightcurve(
    lc_file: Path, bin_size: str = "1", max_bins: str = "10000",
    plot_device: str = "/null",
) -> None:
    """Plot a single lightcurve via lcurve. Saves to plot_device."""
    if not lc_file.exists():
        raise FileNotFoundError(f"Lightcurve file not found: {lc_file}")

    analysis_dir = lc_file.parent

    # lcurve prompts (running with cwd=analysis_dir keeps paths short):
    #   nfiles, fname1, window, bin, nbins, outroot, plot, plotdev,
    #   then PGPLOT subcommands.
    lines = [
        "1",
        lc_file.name,
        "-",
        bin_size,
        max_bins,
        "out",
        "yes",
        plot_device,
    ]
    if plot_device != "/null":
        lines += ["line on", "pl", "q"]
    else:
        lines += ["q"]
    script = "\n".join(lines) + "\n"

    run_heasoft_pty(
        ['lcurve'],
        input_text=script,
        cwd=analysis_dir,
        timeout=120,
    )


def plot_all_lightcurves(
    root_dir: Optional[Path] = None,
    lc_pattern: Optional[str] = None,
    bin_size: Optional[str] = None,
    plot_device: Optional[str] = None,
    workers: Optional[int] = None,
    interactive: bool = True,
):
    """Run lcurve on every <obsid>-results/Analysis/<lc_pattern> match."""
    require_heasoft_tool('lcurve')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        lc_pattern = get_input("Lightcurve glob pattern (in Analysis/)", "*.lc", lc_pattern)
        bin_size = get_input("Bin size (seconds)", "1", bin_size)
        plot_device = get_input(
            "PGPLOT device (/null = headless, file.png/png to save)",
            "/null", plot_device,
        )
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        lc_pattern = lc_pattern or "*.lc"
        bin_size = bin_size or "1"
        plot_device = plot_device or "/null"
        workers = workers or multiprocessing.cpu_count()

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    lc_files: List[Path] = []
    for results_dir in sorted(root_dir.iterdir()):
        if not _is_results_dir_for_obsid(results_dir):
            continue
        analysis = results_dir / "Analysis"
        if analysis.is_dir():
            lc_files.extend(sorted(analysis.glob(lc_pattern)))

    if not lc_files:
        logger.warning(f"No lightcurve files matching {lc_pattern!r} found")
        return

    logger.info(f"Plotting {len(lc_files)} lightcurves with {workers} workers")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(plot_single_lightcurve, lc, bin_size, "10000", plot_device): lc
            for lc in lc_files
        }
        for fut in as_completed(futures):
            lc = futures[fut]
            try:
                fut.result()
                logger.info(f"OK   {lc.parent.parent.name}/{lc.name}")
            except (HEASoftToolError, FileNotFoundError):
                failures += 1
            except Exception as e:
                logger.error(f"FAIL {lc.name}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(lc_files)} failures.")
    else:
        logger.info(f"Done. Plotted {len(lc_files)} lightcurves.")


def plot_multiple_lightcurves(
    lc_files: List[Path], output_name: str = "comparison",
    bin_size: str = "-1", plot_device: str = "/null",
):
    """Plot multiple lightcurves on one figure (for comparison)."""
    if not lc_files:
        raise ValueError("No lightcurve files provided")

    analysis_dir = lc_files[0].parent
    lines = [str(len(lc_files))] + [lc.name for lc in lc_files] + [
        "-", bin_size, "2000000", "out", "yes", plot_device,
    ]
    if plot_device != "/null":
        lines += ["1", "q"]
    else:
        lines += ["q"]
    script = "\n".join(lines) + "\n"

    run_heasoft_pty(
        ['lcurve'],
        input_text=script,
        cwd=analysis_dir,
        timeout=300,
    )


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description='Lightcurve plotting utilities')
    sub = parser.add_subparsers(dest='command', help='Command to run')

    single_p = sub.add_parser('single', help='Plot single lightcurve')
    single_p.add_argument('file', type=Path)
    single_p.add_argument('--bin-size', default='1')
    single_p.add_argument('--plot-device', default='/null')

    all_p = sub.add_parser('all', help='Plot every matching lightcurve')
    all_p.add_argument('--directory', type=Path)
    all_p.add_argument('--pattern', default='*.lc')
    all_p.add_argument('--bin-size', default='1')
    all_p.add_argument('--plot-device', default='/null')
    all_p.add_argument('--workers', type=int)
    all_p.add_argument('--no-interactive', action='store_true')

    multi_p = sub.add_parser('multi', help='Plot multiple lightcurves together')
    multi_p.add_argument('files', nargs='+', type=Path)
    multi_p.add_argument('--output', default='comparison')
    multi_p.add_argument('--bin-size', default='-1')
    multi_p.add_argument('--plot-device', default='/null')

    args = parser.parse_args()

    if args.command == 'single':
        plot_single_lightcurve(args.file, args.bin_size, "10000", args.plot_device)
    elif args.command == 'all':
        plot_all_lightcurves(
            args.directory, args.pattern, args.bin_size, args.plot_device,
            args.workers, interactive=not args.no_interactive,
        )
    elif args.command == 'multi':
        plot_multiple_lightcurves(args.files, args.output, args.bin_size, args.plot_device)
    else:
        parser.print_help()
