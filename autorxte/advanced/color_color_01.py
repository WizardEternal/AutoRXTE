"""Color-Color Diagram Analysis.

Two operations:
  extract_color_ranges  - run seextrct once per energy range (PCA channel band)
                          to produce per-band lightcurves in Analysis/<name>.lc
  plot_color_diagrams   - run lcurve over the per-band lightcurves to make a
                          combined plot (e.g. ccd_plot.png)

Energy bands here are PCA *channel IDs* (0-255), not keV. See CONFIG_GUIDE.md
for the channel-to-keV translation.
"""
import logging
import multiprocessing
import re
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from autorxte.utils import run_heasoft_pty, HEASoftToolError, require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int, get_yes_no

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

DEFAULT_RANGES = ['0-13', '14-35', '36-255']
DEFAULT_NAMES = ['soft', 'medium', 'hard']
DEFAULT_BITMASK = 'bitmask_event'  # written by `bitmask` step


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def extract_color_range(
    results_dir: Path, infile_rel: str, gti_file: Path,
    color_name: str, energy_range: str, bitmask_name: str,
    seext_cwd: Path, bin_size: str = "0.04",
) -> str:
    """Run seextrct for one energy band on one obsid. Returns 'obsid/color_name'."""
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / "Analysis"
    evpath = analysis / color_name
    lc_file = analysis / f"{color_name}.lc"
    bitmask_path = analysis / bitmask_name

    # seextrct script: same shape as extraction_06 except one of the trailing
    # INDEFs is replaced by the channel range. Total 18 stdin lines.
    script_lines = [
        f"@{results_dir}/{infile_rel}",
        "-",
        str(gti_file),
        str(evpath),
        str(bitmask_path),
        "TIME", "EVENT",
        bin_size,
        "LIGHTCURVE", "RATE", "SUM",
    ] + (["INDEF"] * 5) + [energy_range, "INDEF"]
    script = "\n".join(script_lines) + "\n"

    try:
        run_heasoft_pty(
            ['seextrct', 'clobber=yes'],
            input_text=script,
            cwd=seext_cwd,
            timeout=600,
            must_exist=[lc_file],
        )
        return f"{obsid}/{color_name}"
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid}/{color_name}: {e}")
        raise


def extract_color_ranges(
    root_dir: Optional[Path] = None,
    token: Optional[str] = None,
    bitmask: Optional[str] = None,
    ranges: Optional[List[str]] = None,
    names: Optional[List[str]] = None,
    bin_size: Optional[str] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Extract per-band lightcurves for every <obsid>-results/Analysis under root_dir."""
    require_heasoft_tool('seextrct')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        token = get_input("Token type (e/xenon)", "e", token).lower()
        bitmask = get_input("Bitmask filename", DEFAULT_BITMASK, bitmask)
        bin_size = get_input("Time bin size (seconds)", "0.04", bin_size)

        n_ranges = get_int("Number of energy bands", 3, len(ranges) if ranges else None)
        ranges_l = []
        names_l = []
        for i in range(n_ranges):
            default_range = DEFAULT_RANGES[i] if i < len(DEFAULT_RANGES) else f"{i*10}-{(i+1)*10}"
            default_name = DEFAULT_NAMES[i] if i < len(DEFAULT_NAMES) else f"color{i+1}"
            ranges_l.append(get_input(f"Range {i+1} (channel IDs, e.g. 0-13)", default_range))
            names_l.append(get_input(f"Name {i+1}", default_name))
        ranges, names = ranges_l, names_l

        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            "Skip when Analysis/<name>.lc already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        token = (token or "e").lower()
        bitmask = bitmask or DEFAULT_BITMASK
        bin_size = bin_size or "0.04"
        ranges = ranges or DEFAULT_RANGES
        names = names or DEFAULT_NAMES
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")
    if len(ranges) != len(names):
        raise ValueError(
            f"--ranges and --names must have the same count "
            f"(got {len(ranges)} ranges, {len(names)} names)"
        )

    seext_cwd = root_dir.parent.resolve()

    infile_rel = (
        'Analysis/fits_files.god' if token == 'e'
        else 'Analysis/xenon_event_files.txt'
    )

    tasks = []
    for results_dir in sorted(root_dir.iterdir()):
        if not _is_results_dir_for_obsid(results_dir):
            continue
        analysis = results_dir / "Analysis"
        if not analysis.is_dir():
            logger.warning(f"{results_dir.name}: no Analysis/; skip")
            continue
        gti_file = analysis / "good.gti"
        if not gti_file.exists():
            logger.warning(f"{results_dir.name}: missing good.gti; run 'filter' first")
            continue
        if not (analysis / bitmask).exists():
            logger.warning(f"{results_dir.name}: missing {bitmask}; run 'bitmask' first")
            continue
        if not (results_dir / infile_rel).exists():
            logger.warning(f"{results_dir.name}: missing {infile_rel}; run 'organize' first")
            continue

        for color_name, energy_range in zip(names, ranges):
            lc_file = analysis / f"{color_name}.lc"
            if skip_existing and lc_file.exists() and lc_file.stat().st_size > 0:
                logger.info(f"SKIP {results_dir.name[:-len('-results')]}/{color_name}")
                continue
            tasks.append((
                results_dir, infile_rel, gti_file, color_name, energy_range,
                bitmask, seext_cwd, bin_size,
            ))

    if not tasks:
        logger.warning("No work to do.")
        return

    logger.info(f"Extracting {len(tasks)} color lightcurves with {workers} workers")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(extract_color_range, *task): task for task in tasks
        }
        for fut in as_completed(futures):
            try:
                logger.info(f"OK   {fut.result()}")
            except HEASoftToolError:
                failures += 1
            except Exception as e:
                task = futures[fut]
                logger.error(f"FAIL {task[0].name}/{task[3]}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(tasks)} failures.")
    else:
        logger.info(f"Done. Extracted {len(tasks)} color lightcurves.")


def plot_color_diagrams(
    root_dir: Optional[Path] = None,
    color_names: Optional[List[str]] = None,
    bin_size: Optional[str] = None,
    plot_device: Optional[str] = None,
    workers: Optional[int] = None,
    interactive: bool = True,
):
    """Plot per-obsid color-color diagrams using lcurve."""
    require_heasoft_tool('lcurve')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        n_colors = get_int("Number of colors", 3, len(color_names) if color_names else None)
        names_l = []
        for i in range(n_colors):
            default = DEFAULT_NAMES[i] if i < len(DEFAULT_NAMES) else f"color{i+1}"
            names_l.append(get_input(f"Color {i+1} name", default))
        color_names = names_l
        bin_size = get_input("Bin size (seconds, -1 for auto)", "-1", bin_size)
        plot_device = get_input(
            "PGPLOT device (/null = headless, ccd_plot.png/png to save PNG)",
            "/null", plot_device,
        )
        workers = get_int("Workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        color_names = color_names or DEFAULT_NAMES
        bin_size = bin_size or "-1"
        plot_device = plot_device or "/null"
        workers = workers or multiprocessing.cpu_count()

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    def plot_single_diagram(results_dir: Path) -> str:
        obsid = results_dir.name[:-len('-results')]
        analysis = results_dir / "Analysis"
        color_files = [f"{name}.lc" for name in color_names]
        for cf in color_files:
            if not (analysis / cf).exists():
                raise FileNotFoundError(f"{obsid}: missing Analysis/{cf}")

        lines = [str(len(color_files))] + color_files + [
            "-", bin_size, "2000000", "out", "yes",
            plot_device, "1",
        ]
        if plot_device != "/null":
            lines.append("q")
        else:
            lines.append("q")
        script = "\n".join(lines) + "\n"

        try:
            run_heasoft_pty(
                ['lcurve'],
                input_text=script,
                cwd=analysis,
                timeout=300,
            )
            return obsid
        except HEASoftToolError as e:
            logger.error(f"FAIL {obsid}: {e}")
            raise

    dirs = [d for d in sorted(root_dir.iterdir()) if _is_results_dir_for_obsid(d)]
    if not dirs:
        logger.warning("No <obsid>-results directories found.")
        return

    logger.info(f"Plotting {len(dirs)} color-color diagrams with {workers} workers")
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(plot_single_diagram, d): d for d in dirs}
        for fut in as_completed(futures):
            try:
                logger.info(f"OK   {fut.result()}")
            except (HEASoftToolError, FileNotFoundError):
                failures += 1
            except Exception as e:
                d = futures[fut]
                logger.error(f"FAIL {d.name}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(dirs)} failures.")
    else:
        logger.info(f"Done. Plotted {len(dirs)} diagrams.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description='Color-color diagram analysis')
    sub = parser.add_subparsers(dest='command', help='Command to run')

    ext = sub.add_parser('extract', help='Extract per-band lightcurves')
    ext.add_argument('--directory', type=Path)
    ext.add_argument('--token', choices=['e', 'xenon'])
    ext.add_argument('--bitmask')
    ext.add_argument('--ranges', nargs='+')
    ext.add_argument('--names', nargs='+')
    ext.add_argument('--bin-size')
    ext.add_argument('--workers', type=int)
    ext.add_argument('--no-skip-existing', action='store_true')
    ext.add_argument('--no-interactive', action='store_true')

    plt = sub.add_parser('plot', help='Plot color-color diagrams')
    plt.add_argument('--directory', type=Path)
    plt.add_argument('--colors', nargs='+')
    plt.add_argument('--bin-size')
    plt.add_argument('--plot-device')
    plt.add_argument('--workers', type=int)
    plt.add_argument('--no-interactive', action='store_true')

    args = parser.parse_args()

    if args.command == 'extract':
        skip_existing = False if args.no_skip_existing else None
        extract_color_ranges(
            args.directory,
            token=args.token, bitmask=args.bitmask,
            ranges=args.ranges, names=args.names, bin_size=args.bin_size,
            workers=args.workers, skip_existing=skip_existing,
            interactive=not args.no_interactive,
        )
    elif args.command == 'plot':
        plot_color_diagrams(
            args.directory,
            color_names=args.colors, bin_size=args.bin_size,
            plot_device=args.plot_device, workers=args.workers,
            interactive=not args.no_interactive,
        )
    else:
        parser.print_help()
