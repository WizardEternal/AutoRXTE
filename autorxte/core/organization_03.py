"""03 - FITS File Organization.

For each ObsID under root_dir:
  1. Scan <obsid>/pca/ for FITS files (compressed or not), read DATAMODE/DDESC
     headers from the XTE_SE (event-mode) and XTE_SP (Good Xenon) extensions.
  2. Write per-extension summary CSVs and path lists ("god" files):
       <obsid>/fits_data_summary.csv     and  <obsid>/fits_files.god      (XTE_SE)
       <obsid>/xenon_data_summary.csv    and  <obsid>/xenon_files.god     (XTE_SP)
  3. Move (or copy) the .god files into <obsid>-results/Analysis/.

The .god files are the input to seextrct in extraction_06; without them the
rest of the pipeline has nothing to chew on. The pre-repo
fits_files_xenon_normal_mover.py did this; the repo migration dropped step
1 by accident, so this module restores it.
"""
import csv
import gzip
import logging
import multiprocessing
import re
import shutil
from pathlib import Path
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import astropy.io.fits as fits

from autorxte.utils.interactive import get_path, get_int, get_yes_no

logger = logging.getLogger(__name__)

# Same RXTE ObsID pattern as preparation_02.
OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

# Extensions of interest in PCA single-event FITS files.
SE_EXT = 'XTE_SE'   # event-mode
SP_EXT = 'XTE_SP'   # Good Xenon

# Output filenames.
SE_CSV = 'fits_data_summary.csv'
SE_GOD = 'fits_files.god'
SP_CSV = 'xenon_data_summary.csv'
SP_GOD = 'xenon_files.god'


def _read_ext_header(path: Path, ext: str) -> Tuple[str, str]:
    """Return (DATAMODE, DDESC) from extension `ext` of a FITS file, or ('','') if absent.

    astropy.io.fits handles .gz transparently, so we don't need to gunzip ourselves.
    """
    try:
        with fits.open(path, memmap=False) as hdul:
            if ext in hdul:
                hdr = hdul[ext].header
                return hdr.get('DATAMODE', ''), hdr.get('DDESC', '')
    except Exception as e:
        logger.debug(f"FITS read error in {path.name}: {e}")
    return '', ''


def _strip_gz(path_str: str) -> str:
    """Strip a trailing '.gz' from a path string. Match the pre-repo behaviour
    (the old `p.rstrip('.gz')` was buggy; this is the intended semantics)."""
    return path_str[:-3] if path_str.endswith('.gz') else path_str


def _scan_pca_dir(pca_dir: Path) -> Tuple[List[Tuple[Path, str, str]], List[Tuple[Path, str, str]]]:
    """Scan pca/ and return (se_entries, sp_entries) where each entry is (path, datamode, ddesc).

    Files considered: those starting with 'F' (RXTE PCA convention), regardless
    of compression. astropy reads .gz natively.
    """
    se: List[Tuple[Path, str, str]] = []
    sp: List[Tuple[Path, str, str]] = []
    for f in sorted(pca_dir.iterdir()):
        if not f.is_file():
            continue
        if not f.name.startswith('F'):
            continue
        # Try XTE_SE
        dm, dd = _read_ext_header(f, SE_EXT)
        if dm:
            se.append((f, dm, dd))
            continue
        # Otherwise try XTE_SP
        dm, dd = _read_ext_header(f, SP_EXT)
        if dm:
            sp.append((f, dm, dd))
    return se, sp


def _write_csv(out_path: Path, entries: List[Tuple[Path, str, str]]):
    """Write a 3-column CSV: Filename, DATAMODE, DDESC."""
    with open(out_path, 'w', newline='') as cf:
        w = csv.writer(cf)
        w.writerow(['Filename', 'DATAMODE', 'DDESC'])
        for path, dm, dd in entries:
            w.writerow([path.name, dm, dd])


def _write_god(out_path: Path, entries: List[Tuple[Path, str, str]]):
    """Write a path-per-line list, with .gz stripped from each path string."""
    with open(out_path, 'w') as gf:
        for path, _dm, _dd in entries:
            gf.write(_strip_gz(str(path)) + '\n')


def organize_single_obsid(
    obsid_dir: Path,
    move_mode: bool = True,
    skip_existing: bool = True,
) -> str:
    """Process one obsid: scan pca/, write csv+god in obsid dir, move god into Analysis/.

    Returns the obsid name on success.
    """
    obsid = obsid_dir.name
    results_dir = obsid_dir.parent / f"{obsid}-results"
    analysis_dir = results_dir / 'Analysis'

    if not results_dir.is_dir():
        raise FileNotFoundError(
            f"{obsid}: results dir missing ({results_dir}). Run 'prepare' first."
        )

    pca_dir = obsid_dir / 'pca'
    if not pca_dir.is_dir():
        raise FileNotFoundError(f"{obsid}: no pca/ subdir under {obsid_dir}")

    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Resume: if both god files are already in Analysis (or just SE if no SP data),
    # skip. We only know if SP exists after scanning, so we conservatively skip
    # only when the SE god file exists.
    se_target = analysis_dir / SE_GOD
    if skip_existing and se_target.exists():
        logger.info(f"SKIP {obsid} (Analysis/{SE_GOD} already exists)")
        return obsid

    # Scan pca/ once and bin by extension type.
    se_entries, sp_entries = _scan_pca_dir(pca_dir)

    if not se_entries and not sp_entries:
        logger.warning(f"{obsid}: no XTE_SE or XTE_SP files found in pca/")
        return obsid

    # Write per-extension CSV + .god into the obsid dir.
    if se_entries:
        _write_csv(obsid_dir / SE_CSV, se_entries)
        _write_god(obsid_dir / SE_GOD, se_entries)
    if sp_entries:
        _write_csv(obsid_dir / SP_CSV, sp_entries)
        _write_god(obsid_dir / SP_GOD, sp_entries)

    # Move (or copy) the god files into Analysis/.
    transfer = shutil.move if move_mode else shutil.copy2
    for god_name, made in [(SE_GOD, bool(se_entries)), (SP_GOD, bool(sp_entries))]:
        if not made:
            continue
        src = obsid_dir / god_name
        dst = analysis_dir / god_name
        if dst.exists():
            dst.unlink()
        transfer(str(src), str(dst))

    n_se, n_sp = len(se_entries), len(sp_entries)
    logger.info(f"OK   {obsid}  (SE={n_se} SP={n_sp})")
    return obsid


def organize_fits_files(
    root_dir: Optional[Path] = None,
    move_mode: Optional[bool] = None,
    skip_existing: Optional[bool] = None,
    workers: Optional[int] = None,
    interactive: bool = True,
):
    """Run organization across every ObsID under root_dir."""
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        move_mode = get_yes_no("Move files (vs copy)?", True, move_mode)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no("Skip obsids whose Analysis/ already has the .god?",
                                   True, skip_existing)
    else:
        root_dir = root_dir or Path('.')
        move_mode = move_mode if move_mode is not None else True
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    obs_dirs = [
        e for e in sorted(root_dir.iterdir())
        if e.is_dir() and OBSID_RE.match(e.name)
    ]

    if not obs_dirs:
        logger.warning(
            f"No ObsID directories found under {root_dir} "
            f"(pattern {OBSID_RE.pattern!r}). Either nothing needs organizing, "
            f"or the root directory is wrong."
        )
        return

    logger.info(f"Organizing {len(obs_dirs)} observations with {workers} workers")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(organize_single_obsid, d, move_mode, skip_existing): d
            for d in obs_dirs
        }
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                d = futures[fut]
                logger.error(f"FAIL {d.name}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(obs_dirs)} failures.")
    else:
        logger.info(f"Done. Organized {len(obs_dirs)} observations.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--workers', type=int)
    parser.add_argument('--copy', action='store_true', help='Copy instead of move')
    parser.add_argument('--no-skip-existing', action='store_true',
                        help='Re-organize even when Analysis/ already has the .god')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    organize_fits_files(
        args.directory,
        move_mode=not args.copy,
        skip_existing=not args.no_skip_existing,
        workers=args.workers,
        interactive=not args.no_interactive,
    )
