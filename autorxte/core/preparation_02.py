"""02 - Observation Preparation with pcaprepobsid."""
import logging
import re
import multiprocessing
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from autorxte.utils import require_heasoft_tool, run_heasoft_pty, HEASoftToolError
from autorxte.utils.interactive import get_path, get_int, get_yes_no

logger = logging.getLogger(__name__)

# RXTE ObsID format: PPPPP-NN-NN-NN with optional trailing letter (revision tag).
# Examples: 60405-01-02-00, 80135-02-03-01, 20402-01-34-00A
OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

# pcaprepobsid writes appid.lis last; its presence is a reliable "complete" sentinel.
PREP_SENTINEL = 'appid.lis'


def is_obsid_dir(entry: Path) -> bool:
    """True if entry is a directory whose name matches the RXTE ObsID pattern.

    Excludes <obsid>-results dirs and other siblings (e.g. the downloaded_*.json
    record file is filtered out earlier by is_dir()).
    """
    return entry.is_dir() and bool(OBSID_RE.match(entry.name))


def prep_is_complete(results_dir: Path) -> bool:
    """True if a -results dir exists and contains the pcaprepobsid completion sentinel."""
    return results_dir.is_dir() and (results_dir / PREP_SENTINEL).exists()


def prepare_single_obsid(obsid_dir: Path, timeout: int = 1800) -> str:
    """Run pcaprepobsid on a single observation under a pty.

    pcaprepobsid opens /dev/tty for prompts and refuses to start under a
    non-TTY stdin (even with all parameters supplied), so we run it through
    run_heasoft_pty. We also pass mode=h to suppress prompt-on-blank
    behaviour and verify the appid.lis sentinel exists after the call.
    """
    obsid = obsid_dir.name
    outdir = obsid_dir.parent / f"{obsid}-results"
    sentinel = outdir / PREP_SENTINEL
    try:
        run_heasoft_pty(
            ['pcaprepobsid', f'indir={obsid_dir}', f'outdir={outdir}', 'mode=h'],
            timeout=timeout,
            must_exist=[sentinel],
        )
        logger.info(f"OK   {obsid}")
        return obsid
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid}: {e}")
        raise


def find_obsid_dirs(root_dir: Path, skip_existing: bool) -> List[Path]:
    """List ObsID directories under root_dir, optionally skipping completed preps."""
    obs_dirs = []
    for entry in sorted(root_dir.iterdir()):
        if not is_obsid_dir(entry):
            continue
        results_dir = root_dir / f"{entry.name}-results"
        if skip_existing and prep_is_complete(results_dir):
            logger.info(f"SKIP {entry.name} (results dir already complete)")
            continue
        obs_dirs.append(entry)
    return obs_dirs


def prepare_all_obsids(root_dir: Optional[Path] = None, workers: Optional[int] = None,
                       skip_existing: Optional[bool] = None, interactive: bool = True):
    """Prepare all observations under root_dir."""
    require_heasoft_tool('pcaprepobsid')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no("Skip existing results?", True, skip_existing)
    else:
        root_dir = root_dir or Path('.')
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    obs_dirs = find_obsid_dirs(root_dir, skip_existing)

    if not obs_dirs:
        logger.warning(
            f"No ObsID directories found under {root_dir} "
            f"(pattern {OBSID_RE.pattern!r}). "
            f"Either nothing needs preparing, or the root directory is wrong."
        )
        return

    logger.info(f"Preparing {len(obs_dirs)} observations with {workers} workers")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(prepare_single_obsid, d): d for d in obs_dirs}
        for future in as_completed(futures):
            try:
                future.result()
            except HEASoftToolError:
                # Already logged in prepare_single_obsid; just count.
                failures += 1
            except Exception as e:
                logger.error(f"Unexpected error: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(obs_dirs)} failures.")
    else:
        logger.info(f"Done. Prepared {len(obs_dirs)} observations.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-interactive', action='store_true')
    parser.add_argument('--no-skip-existing', action='store_true',
                        help='Re-run prep even when results dir is complete')
    args = parser.parse_args()
    prepare_all_obsids(
        args.directory,
        args.workers,
        skip_existing=not args.no_skip_existing,
        interactive=not args.no_interactive,
    )
