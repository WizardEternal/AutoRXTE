"""08 - Spectral Extraction with pcaextspect2.

Three outputs per ObsID land in <obsid>-results/Analysis/:
  - src.pha  source spectrum (dead-time corrected)
  - bkg.pha  background spectrum
  - rsp.pha  response matrix

Like pcaextlc1/2, pcaextspect2 has a fixed-size internal buffer for the
output filename plus an internal `_tmp` suffix. Long paths overflow it
and the tool aborts with the misleading "COLUMNS parameter may be too
long" error. We work around this by writing into a short tempdir and
moving the three output files into Analysis/ afterwards.
"""
import logging
import multiprocessing
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from autorxte.utils import run_heasoft_pty, HEASoftToolError, require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int, get_yes_no

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

DEFAULT_SRC = "src.pha"
DEFAULT_BKG = "bkg.pha"
DEFAULT_RSP = "rsp.pha"


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def _check_inputs(results_dir: Path) -> bool:
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / 'Analysis'
    if not analysis.is_dir():
        logger.warning(f"{obsid}: missing Analysis/; run 'organize' first")
        return False
    if not (analysis / 'good.gti').exists():
        logger.warning(f"{obsid}: missing Analysis/good.gti; run 'filter' first")
        return False
    for lf in ('FP_dtstd2.lis', 'FP_dtbkg2.lis', 'FP_xtefilt.lis'):
        if not (results_dir / lf).exists():
            logger.warning(f"{obsid}: missing {lf}; run 'prepare' first")
            return False
    return True


def _build_pcaextspect2_args(
    results_dir: Path, src_out: Path, bkg_out: Path, rsp_out: Path,
    pculist: str, layerlist: str,
) -> List[str]:
    return [
        'pcaextspect2',
        f'src_infile=@{results_dir}/FP_dtstd2.lis',
        f'bkg_infile=@{results_dir}/FP_dtbkg2.lis',
        f'src_phafile={src_out}',
        f'bkg_phafile={bkg_out}',
        f'gtiandfile={results_dir / "Analysis" / "good.gti"}',
        f'pculist={pculist}',
        f'layerlist={layerlist}',
        f'respfile={rsp_out}',
        f'filtfile=@{results_dir}/FP_xtefilt.lis',
        'clobber=yes',
        'mode=h',
    ]


def extract_spectrum_single(
    results_dir: Path,
    src_name: str,
    bkg_name: str,
    rsp_name: str,
    pculist: str,
    layerlist: str,
    seext_cwd: Path,
    timeout: int = 900,
) -> str:
    """Run pcaextspect2 on a single obsid. Outputs go via a short tempdir."""
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / 'Analysis'
    analysis.mkdir(parents=True, exist_ok=True)

    src_final = analysis / src_name
    bkg_final = analysis / bkg_name
    rsp_final = analysis / rsp_name

    short_dir = Path(tempfile.mkdtemp(prefix='pcaextspec_'))
    src_tmp = short_dir / src_name
    bkg_tmp = short_dir / bkg_name
    rsp_tmp = short_dir / rsp_name

    cmd = _build_pcaextspect2_args(
        results_dir, src_tmp, bkg_tmp, rsp_tmp, pculist, layerlist,
    )

    try:
        run_heasoft_pty(
            cmd,
            cwd=seext_cwd,
            timeout=timeout,
            must_exist=[src_tmp, bkg_tmp, rsp_tmp],
        )
        # Move all three outputs into Analysis/.
        for tmp, final in (
            (src_tmp, src_final),
            (bkg_tmp, bkg_final),
            (rsp_tmp, rsp_final),
        ):
            if final.exists():
                final.unlink()
            shutil.move(str(tmp), str(final))
        return obsid
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid} (pcaextspect2): {e}")
        raise
    finally:
        shutil.rmtree(short_dir, ignore_errors=True)


def extract_spectra(
    root_dir: Optional[Path] = None,
    layerlist: Optional[str] = None,
    pculist: Optional[str] = None,
    src_name: Optional[str] = None,
    bkg_name: Optional[str] = None,
    rsp_name: Optional[str] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Run pcaextspect2 on every <obsid>-results/Analysis under root_dir."""
    require_heasoft_tool('pcaextspect2')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        layerlist = get_input("Layer list (1, 2, 3, or ALL)", "ALL", layerlist)
        pculist = get_input("PCU list (comma-sep)", "2", pculist)
        src_name = get_input("Source spectrum filename", DEFAULT_SRC, src_name)
        bkg_name = get_input("Background spectrum filename", DEFAULT_BKG, bkg_name)
        rsp_name = get_input("Response filename", DEFAULT_RSP, rsp_name)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            f"Skip obsids whose Analysis/{src_name} already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        layerlist = layerlist or "ALL"
        pculist = pculist or "2"
        src_name = src_name or DEFAULT_SRC
        bkg_name = bkg_name or DEFAULT_BKG
        rsp_name = rsp_name or DEFAULT_RSP
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    seext_cwd = root_dir.parent.resolve()

    tasks: List[Path] = []
    for results_dir in sorted(root_dir.iterdir()):
        if not _is_results_dir_for_obsid(results_dir):
            continue
        if not _check_inputs(results_dir):
            continue
        analysis = results_dir / 'Analysis'
        src_path = analysis / src_name
        if skip_existing and src_path.exists() and src_path.stat().st_size > 0:
            logger.info(f"SKIP {results_dir.name[:-len('-results')]} ({src_name})")
            continue
        tasks.append(results_dir)

    if not tasks:
        logger.warning("No work to do.")
        return

    logger.info(f"Extracting {len(tasks)} spectra with {workers} workers")
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                extract_spectrum_single, d, src_name, bkg_name, rsp_name,
                pculist, layerlist, seext_cwd,
            ): d
            for d in tasks
        }
        for fut in as_completed(futures):
            try:
                logger.info(f"OK   {fut.result()}")
            except HEASoftToolError:
                failures += 1
            except Exception as e:
                d = futures[fut]
                logger.error(f"FAIL {d.name}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        logger.warning(f"Done with {failures}/{len(tasks)} failures.")
    else:
        logger.info(f"Done. Extracted {len(tasks)} spectra.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--layerlist', help='Layer selection 1/2/3/ALL (default ALL)')
    parser.add_argument('--pculist', help='PCU list comma-separated (default 2)')
    parser.add_argument('--src-name')
    parser.add_argument('--bkg-name')
    parser.add_argument('--rsp-name')
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-skip-existing', action='store_true')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    skip_existing = False if args.no_skip_existing else None
    extract_spectra(
        args.directory,
        layerlist=args.layerlist,
        pculist=args.pculist,
        src_name=args.src_name,
        bkg_name=args.bkg_name,
        rsp_name=args.rsp_name,
        workers=args.workers,
        skip_existing=skip_existing,
        interactive=not args.no_interactive,
    )
