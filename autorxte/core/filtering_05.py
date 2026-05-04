"""05 - Time Filtering and GTI Creation.

For each <obsid>-results/, run `maketime` against the prep-stage filter file
(FP_xtefilt.lis points at FP_*.xfl) to produce Analysis/good.gti, the Good
Time Interval table that downstream extraction uses.
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

DEFAULT_FILTER = (
    "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) "
    "&& .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)"
)


def _resolve_xfl_path(line: str, results_dir: Path) -> Path:
    """Take the first line of FP_xtefilt.lis and return an absolute path to the .xfl.

    pcaprepobsid writes whatever string was passed as `outdir=...` into the
    .lis file, so the path may be absolute or relative depending on how the
    caller invoked prep. If absolute and exists, use as-is. Otherwise look
    for the same basename inside results_dir.
    """
    p = Path(line)
    if p.is_absolute() and p.exists():
        return p
    # Fall back: same basename inside results_dir
    candidate = results_dir / p.name
    if candidate.exists():
        return candidate
    # Last try: as written, relative to cwd
    if Path(line).exists():
        return Path(line).resolve()
    raise FileNotFoundError(
        f"Filter file referenced in FP_xtefilt.lis not found: {line!r} "
        f"(also tried {results_dir / p.name})"
    )


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def filter_single_obsid(
    results_dir: Path,
    filter_expression: str,
    skip_existing: bool = True,
    timeout: int = 300,
) -> str:
    """Run maketime for a single -results dir. Returns the obsid name."""
    obsid = results_dir.name[:-len('-results')]
    analysis_dir = results_dir / 'Analysis'
    analysis_dir.mkdir(parents=True, exist_ok=True)

    gti_file = analysis_dir / 'good.gti'
    if skip_existing and gti_file.exists() and gti_file.stat().st_size > 0:
        logger.info(f"SKIP {obsid} (Analysis/good.gti already exists)")
        return obsid

    lis_file = results_dir / 'FP_xtefilt.lis'
    if not lis_file.exists():
        raise FileNotFoundError(
            f"{obsid}: no FP_xtefilt.lis in {results_dir}; run 'prepare' first"
        )

    first_line = lis_file.read_text().splitlines()[0].strip()
    if not first_line:
        raise ValueError(f"{obsid}: FP_xtefilt.lis is empty")

    xfl_path = _resolve_xfl_path(first_line, results_dir)

    # If we're re-running and a stale gti exists, remove it so maketime doesn't
    # ask about clobber. (HEASoft's clobber=yes is the default but the prompt
    # still appears in some configs.)
    if gti_file.exists():
        gti_file.unlink()

    # Stdin script for maketime: input filter file, output GTI, expression,
    # compact-HK flag (no), HK time column name (TIME).
    script = (
        f"{xfl_path}\n"
        f"{gti_file}\n"
        f"{filter_expression}\n"
        f"no\n"
        f"TIME\n"
    )

    try:
        run_heasoft_pty(
            ['maketime'],
            input_text=script,
            timeout=timeout,
            must_exist=[gti_file],
        )
        logger.info(f"OK   {obsid}")
        return obsid
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid}: {e}")
        raise


def create_gti_filters(
    root_dir: Optional[Path] = None,
    filter_expression: Optional[str] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Build Analysis/good.gti for every <obsid>-results/ under root_dir."""
    require_heasoft_tool('maketime')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        if filter_expression is None:
            print(f"Default filter: {DEFAULT_FILTER}")
        filter_expression = get_input(
            "Filter expression", DEFAULT_FILTER, filter_expression
        )
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            "Skip obsids whose Analysis/good.gti already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        filter_expression = filter_expression or DEFAULT_FILTER
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    results_dirs = [
        e for e in sorted(root_dir.iterdir()) if _is_results_dir_for_obsid(e)
    ]
    if not results_dirs:
        logger.warning(
            f"No <obsid>-results directories found under {root_dir}. "
            f"Run 'prepare' first."
        )
        return

    logger.info(f"Filtering {len(results_dirs)} obsids with {workers} workers")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(filter_single_obsid, d, filter_expression, skip_existing): d
            for d in results_dirs
        }
        for fut in as_completed(futures):
            try:
                fut.result()
            except (HEASoftToolError, FileNotFoundError, ValueError) as e:
                d = futures[fut]
                # FileNotFoundError already logged the message; HEASoft error
                # is logged in filter_single_obsid. ValueError isn't.
                if isinstance(e, ValueError) or isinstance(e, FileNotFoundError):
                    logger.error(f"FAIL {d.name}: {e}")
                failures += 1
            except Exception as e:
                d = futures[fut]
                logger.error(f"FAIL {d.name}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(results_dirs)} failures.")
    else:
        logger.info(f"Done. Built {len(results_dirs)} GTI files.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--filter', help='Filter expression')
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-skip-existing', action='store_true')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    skip_existing = False if args.no_skip_existing else None
    create_gti_filters(
        args.directory,
        args.filter,
        workers=args.workers,
        skip_existing=skip_existing,
        interactive=not args.no_interactive,
    )
