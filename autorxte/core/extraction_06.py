"""06 - Event Extraction with seextrct.

For each <obsid>-results/Analysis with the prerequisites in place, run
seextrct to produce <prefix>.lc and friends. Reads:
  - Analysis/fits_files.god      (event-mode file list, from organize)
  - Analysis/good.gti            (GTI from filter)
  - Analysis/<bitmask_file>      (from bitmask, default bitmask_event)

The .god file may contain absolute paths (post the rewritten organize_03)
or relative paths (the pre-repo script wrote paths relative to cwd). To
make both work, seextrct is run with cwd set to the parent of root_dir
(typically the dir from which the user invokes autorxte).
"""
import logging
import multiprocessing
import re
from pathlib import Path
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from astropy.io import fits

from autorxte.utils import run_heasoft_pty, HEASoftToolError, require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_yes_no, get_int

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')


def split_gti(gti_path: Path, sep_dir: Path) -> List[Path]:
    """Split a multi-row GTI FITS into one-row-per-file under sep_dir.

    Returns the list of split GTI paths (sorted). If sep_dir already has
    the right count, returns the existing files without rebuilding.

    Note: the pre-repo script used `cols = Column(...); cols += Column(...)`
    which does not work — fits.Column does not implement __iadd__. The
    correct pattern is to build a list of Columns and pass it to
    BinTableHDU.from_columns(); that's what we do here.
    """
    with fits.open(gti_path) as hdul:
        data = hdul[1].data
        nrows = len(data)
        sep_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(sep_dir.glob("good_*.gti"))
        if len(existing) == nrows:
            return existing

        out: List[Path] = []
        col0 = hdul[1].columns[0]
        col1 = hdul[1].columns[1]
        primary_hdu = hdul[0].copy()
        ext_header = hdul[1].header

        for idx, row in enumerate(data, start=1):
            cols = [
                fits.Column(name=col0.name, format=col0.format, array=[row[0]]),
                fits.Column(name=col1.name, format=col1.format, array=[row[1]]),
            ]
            tbl = fits.BinTableHDU.from_columns(cols, header=ext_header)
            hdu = fits.HDUList([primary_hdu, tbl])
            out_path = sep_dir / f"good_{idx}.gti"
            hdu.writeto(out_path, overwrite=True)
            out.append(out_path)
        return out


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def _build_seextrct_script(
    infile_at_path: str,
    gti_file: Path,
    evpath: Path,
    bitmask_file: Path,
    bin_size: str = "0.004",
) -> str:
    """Build the 14-line stdin script seextrct expects."""
    lines = [
        infile_at_path,        # @<path-to-list-file>
        "-",                    # clobber column (skip)
        str(gti_file),          # gti file
        str(evpath),            # output prefix
        str(bitmask_file),      # bitmask file
        "TIME",                 # time column
        "EVENT",                # event column
        bin_size,               # bin size in seconds
        "LIGHTCURVE",           # output type
        "RATE",                 # units
        "SUM",                  # combine mode
    ] + (["INDEF"] * 7)         # 7 INDEF defaults
    return "\n".join(lines) + "\n"


def run_seextrct_single(
    results_dir: Path,
    infile_rel: str,
    gti_file: Path,
    evt_prefix: str,
    bitmask_name: str,
    seext_cwd: Path,
    timeout: int = 600,
) -> str:
    """Run seextrct for a single GTI on one obsid. Returns 'obsid/prefix' on success."""
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / "Analysis"
    evpath = analysis / evt_prefix
    bitmask_file = analysis / bitmask_name

    # The lightcurve output that seextrct produces.
    lc_file = analysis / f"{evt_prefix}.lc"

    script = _build_seextrct_script(
        infile_at_path=f"@{results_dir}/{infile_rel}",
        gti_file=gti_file,
        evpath=evpath,
        bitmask_file=bitmask_file,
    )

    try:
        run_heasoft_pty(
            ['seextrct', 'clobber=yes'],
            input_text=script,
            cwd=seext_cwd,
            timeout=timeout,
            must_exist=[lc_file],
        )
        return f"{obsid}/{evt_prefix}"
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid}/{evt_prefix}: {e}")
        raise


def extract_all_events(
    root_dir: Optional[Path] = None,
    prefix: Optional[str] = None,
    token: Optional[str] = None,
    bitmask: Optional[str] = None,
    split_gti_flag: Optional[bool] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Run seextrct on every <obsid>-results/Analysis under root_dir."""
    require_heasoft_tool('seextrct')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        token = get_input("Use (e)-token or (xenon)-token?", "e", token).lower()
        prefix = get_input("Base event name", "event", prefix)
        bitmask = get_input("Bitmask filename", "bitmask_event", bitmask)
        split_gti_flag = get_yes_no("Use separated (per-row) GTIs?", False, split_gti_flag)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            "Skip obsids whose <prefix>.lc already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        token = (token or "e").lower()
        prefix = prefix or "event"
        bitmask = bitmask or "bitmask_event"
        split_gti_flag = split_gti_flag if split_gti_flag is not None else False
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    # Pick the correct file list for the chosen token.
    infile_rel = (
        'Analysis/fits_files.god' if token == 'e' else 'Analysis/xenon_event_files.txt'
    )

    # The .god file may have relative paths from the pre-repo workflow. Run
    # seextrct from the parent of root_dir so those paths resolve. Absolute
    # paths in newer .god files are unaffected.
    seext_cwd = root_dir.parent.resolve()

    # Build the task list.
    tasks: List[Tuple[Path, str, Path, str, str]] = []
    for results_dir in sorted(root_dir.iterdir()):
        if not _is_results_dir_for_obsid(results_dir):
            continue

        analysis = results_dir / "Analysis"
        if not analysis.is_dir():
            logger.warning(f"{results_dir.name}: no Analysis/; run 'organize' first")
            continue

        # Required inputs.
        infile_path = results_dir / infile_rel
        gti_main = analysis / "good.gti"
        bitmask_path = analysis / bitmask

        if not infile_path.exists():
            logger.warning(f"{results_dir.name}: missing {infile_rel}; run 'organize' first")
            continue
        if not gti_main.exists():
            logger.warning(f"{results_dir.name}: missing Analysis/good.gti; run 'filter' first")
            continue
        if not bitmask_path.exists():
            logger.warning(f"{results_dir.name}: missing Analysis/{bitmask}; run 'bitmask' first")
            continue

        gtis = (
            split_gti(gti_main, results_dir / "sep_gtis")
            if split_gti_flag else [gti_main]
        )

        for gti in gtis:
            row = gti.stem.split('_')[-1] if gti != gti_main else ''
            evt_prefix = prefix + (f"_{row}" if row else '')
            lc_file = analysis / f"{evt_prefix}.lc"
            if skip_existing and lc_file.exists() and lc_file.stat().st_size > 0:
                logger.info(f"SKIP {results_dir.name[:-len('-results')]}/{evt_prefix}")
                continue
            tasks.append((results_dir, infile_rel, gti, evt_prefix, bitmask))

    if not tasks:
        logger.warning("No work to do (everything skipped, or no valid obsids).")
        return

    logger.info(f"Extracting {len(tasks)} files with {workers} workers (cwd={seext_cwd})")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_seextrct_single, *task, seext_cwd): task
            for task in tasks
        }
        for fut in as_completed(futures):
            try:
                logger.info(f"OK   {fut.result()}")
            except (HEASoftToolError, FileNotFoundError, ValueError):
                # Already logged by run_seextrct_single.
                failures += 1
            except Exception as e:
                task = futures[fut]
                logger.error(f"FAIL {task[0].name}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(tasks)} failures.")
    else:
        logger.info(f"Done. Extracted {len(tasks)} event files.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--prefix', help='Base event filename (default: event)')
    parser.add_argument('--token', choices=['e', 'xenon'])
    parser.add_argument('--bitmask', help='Bitmask filename in Analysis/ (default: bitmask_event)')
    parser.add_argument('--split-gti', action='store_true')
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-skip-existing', action='store_true')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    skip_existing = False if args.no_skip_existing else None
    split_gti_flag = True if args.split_gti else None
    extract_all_events(
        args.directory,
        prefix=args.prefix,
        token=args.token,
        bitmask=args.bitmask,
        split_gti_flag=split_gti_flag,
        workers=args.workers,
        skip_existing=skip_existing,
        interactive=not args.no_interactive,
    )
