"""07 - Light Curve Generation with pcaextlc1 / pcaextlc2.

Two distinct tools, one entry point:

  std1 -> pcaextlc1   (Standard1, 1/8-second resolution, single channel)
  std2 -> pcaextlc2   (Standard2, configurable energy channels and time bins)

Both read FP_dtstd*.lis + FP_dtbkg2.lis (written by pcaprepobsid) and the
GTI file built by `filter`. Outputs land in <obsid>-results/Analysis/.

pcaextlc1/2 has a fixed-size internal buffer for the temp filename
("<outfile>_tmp.lc"); a long outfile path overflows it and the tool aborts
with the misleading "COLUMNS parameter may be too long" error. We work
around this by running with a short tempdir outfile and moving the result
into Analysis/ afterwards.
"""
import logging
import multiprocessing
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Literal, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from autorxte.utils import run_heasoft_pty, HEASoftToolError, require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int, get_yes_no, get_choice

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

DEFAULT_STD1_LC_NAME = "std1.lc"
DEFAULT_STD2_LC_NAME = "light.lc"


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def _build_pcaextlc1_args(
    results_dir: Path, analysis_dir: Path, lc_name: str, bin_size: str, pculist: str,
) -> List[str]:
    return [
        'pcaextlc1',
        f'src_infile=@{results_dir}/FP_dtstd1.lis',
        f'bkg_infile=@{results_dir}/FP_dtbkg2.lis',
        f'outfile={analysis_dir / lc_name}',
        f'gtiandfile={analysis_dir / "good.gti"}',
        f'pculist={pculist}',
        f'binsz={bin_size}',
        'clobber=yes',
        'mode=h',
    ]


def _build_pcaextlc2_args(
    results_dir: Path, analysis_dir: Path, lc_name: str,
    layerlist: str, time_bins: str, pculist: str,
    chmin: str, chmax: str,
) -> List[str]:
    # chmin/chmax are required when layerlist=ALL: without them pcaextlc2's
    # auto-generated COLUMNS list overflows ("COLUMNS parameter may be too long").
    return [
        'pcaextlc2',
        f'src_infile=@{results_dir}/FP_dtstd2.lis',
        f'bkg_infile=@{results_dir}/FP_dtbkg2.lis',
        f'outfile={analysis_dir / lc_name}',
        f'gtiandfile={analysis_dir / "good.gti"}',
        f'pculist={pculist}',
        f'layerlist={layerlist}',
        f'binsz={time_bins}',
        f'chmin={chmin}',
        f'chmax={chmax}',
        'clobber=yes',
        'mode=h',
    ]


def _run_pcaextlc(
    cmd: List[str],
    results_dir: Path,
    lc_path: Path,
    seext_cwd: Path,
    timeout: int = 600,
) -> str:
    """Generic runner for pcaextlc1/pcaextlc2 returning the obsid name on success.

    Runs with a short outfile path inside a tempdir, then moves the produced
    light curve to lc_path. Cleans up auxiliary tempbkg files that
    pcaextlc1 leaves behind.
    """
    obsid = results_dir.name[:-len('-results')]
    lc_path.parent.mkdir(parents=True, exist_ok=True)

    # Build a new cmd with outfile pointing at a short temp path. lc_path's
    # name is reused so the produced file can be moved unambiguously.
    short_dir = Path(tempfile.mkdtemp(prefix='pcaextlc_'))
    short_outfile = short_dir / lc_path.name
    cmd2 = []
    replaced = False
    for arg in cmd:
        if arg.startswith('outfile='):
            cmd2.append(f'outfile={short_outfile}')
            replaced = True
        else:
            cmd2.append(arg)
    if not replaced:
        cmd2 = cmd  # nothing to do

    try:
        run_heasoft_pty(
            cmd2,
            cwd=seext_cwd,
            timeout=timeout,
            must_exist=[short_outfile],
        )
        # Move the .lc into Analysis/. Replace any stale prior version.
        if lc_path.exists():
            lc_path.unlink()
        shutil.move(str(short_outfile), str(lc_path))
        return obsid
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid} ({cmd[0]}): {e}")
        raise
    finally:
        # Clean up any leftover files in the temp dir (pcaextlc1 leaves
        # <name>_tmpbkg.lc; pcaextlc2 doesn't).
        try:
            shutil.rmtree(short_dir, ignore_errors=True)
        except Exception:
            pass


def _enumerate_results(root_dir: Path) -> List[Path]:
    return [e for e in sorted(root_dir.iterdir()) if _is_results_dir_for_obsid(e)]


def _check_inputs(results_dir: Path, list_files: List[str]) -> bool:
    """Verify per-obsid input files exist; return True if all present, else log + False."""
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / 'Analysis'
    if not analysis.is_dir():
        logger.warning(f"{obsid}: missing Analysis/; run 'organize' first")
        return False
    if not (analysis / 'good.gti').exists():
        logger.warning(f"{obsid}: missing Analysis/good.gti; run 'filter' first")
        return False
    for lf in list_files:
        if not (results_dir / lf).exists():
            logger.warning(f"{obsid}: missing {lf}; run 'prepare' first")
            return False
    return True


def extract_std1_lightcurves(
    root_dir: Optional[Path] = None,
    bin_size: Optional[str] = None,
    lc_name: Optional[str] = None,
    pculist: Optional[str] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Generate STD1 light curves with pcaextlc1."""
    require_heasoft_tool('pcaextlc1')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        bin_size = get_input("Bin size (seconds)", "0.125", bin_size)
        lc_name = get_input("Output LC filename", DEFAULT_STD1_LC_NAME, lc_name)
        pculist = get_input("PCU list (comma-sep)", "2", pculist)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            f"Skip obsids whose Analysis/{lc_name} already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        bin_size = bin_size or "0.125"
        lc_name = lc_name or DEFAULT_STD1_LC_NAME
        pculist = pculist or "2"
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    seext_cwd = root_dir.parent.resolve()

    tasks: List[Tuple[Path, List[str], Path]] = []
    for results_dir in _enumerate_results(root_dir):
        if not _check_inputs(results_dir, ['FP_dtstd1.lis', 'FP_dtbkg2.lis']):
            continue
        analysis = results_dir / 'Analysis'
        lc_path = analysis / lc_name
        if skip_existing and lc_path.exists() and lc_path.stat().st_size > 0:
            logger.info(f"SKIP {results_dir.name[:-len('-results')]} ({lc_name})")
            continue
        cmd = _build_pcaextlc1_args(results_dir, analysis, lc_name, bin_size, pculist)
        tasks.append((results_dir, cmd, lc_path))

    if not tasks:
        logger.warning("No work to do.")
        return

    logger.info(f"Building {len(tasks)} STD1 lightcurves with {workers} workers")
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_pcaextlc, c, d, p, seext_cwd): d
            for d, c, p in tasks
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
        logger.info(f"Done. Built {len(tasks)} STD1 lightcurves.")


def extract_std2_lightcurves(
    root_dir: Optional[Path] = None,
    layerlist: Optional[str] = None,
    time_bins: Optional[str] = None,
    lc_name: Optional[str] = None,
    pculist: Optional[str] = None,
    chmin: Optional[str] = None,
    chmax: Optional[str] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Generate STD2 light curves with pcaextlc2."""
    require_heasoft_tool('pcaextlc2')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        layerlist = get_input("Layer list (1, 2, 3, or ALL)", "ALL", layerlist)
        time_bins = get_input("Bin size (seconds, multiple of 16)", "16", time_bins)
        lc_name = get_input("Output LC filename", DEFAULT_STD2_LC_NAME, lc_name)
        pculist = get_input("PCU list (comma-sep)", "2", pculist)
        chmin = get_input("Min channel (0-255)", "0", chmin)
        chmax = get_input("Max channel (0-255)", "255", chmax)
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            f"Skip obsids whose Analysis/{lc_name} already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        layerlist = layerlist or "ALL"
        time_bins = time_bins or "16"
        lc_name = lc_name or DEFAULT_STD2_LC_NAME
        pculist = pculist or "2"
        chmin = chmin or "0"
        chmax = chmax or "255"
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    seext_cwd = root_dir.parent.resolve()

    tasks: List[Tuple[Path, List[str], Path]] = []
    for results_dir in _enumerate_results(root_dir):
        if not _check_inputs(results_dir, ['FP_dtstd2.lis', 'FP_dtbkg2.lis']):
            continue
        analysis = results_dir / 'Analysis'
        lc_path = analysis / lc_name
        if skip_existing and lc_path.exists() and lc_path.stat().st_size > 0:
            logger.info(f"SKIP {results_dir.name[:-len('-results')]} ({lc_name})")
            continue
        cmd = _build_pcaextlc2_args(
            results_dir, analysis, lc_name, layerlist, time_bins, pculist, chmin, chmax,
        )
        tasks.append((results_dir, cmd, lc_path))

    if not tasks:
        logger.warning("No work to do.")
        return

    logger.info(f"Building {len(tasks)} STD2 lightcurves with {workers} workers")
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_pcaextlc, c, d, p, seext_cwd): d
            for d, c, p in tasks
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
        logger.info(f"Done. Built {len(tasks)} STD2 lightcurves.")


def generate_lightcurves(
    root_dir: Optional[Path] = None,
    lc_type: Optional[Literal['std1', 'std2']] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
    **kwargs,
):
    """Top-level dispatcher: pick std1 or std2 and call the right extractor."""
    if interactive and lc_type is None:
        lc_type = get_choice("Light curve type", ['std1', 'std2'], 'std2', lc_type)
    elif lc_type is None:
        lc_type = 'std2'

    if lc_type == 'std1':
        extract_std1_lightcurves(
            root_dir=root_dir,
            bin_size=kwargs.get('bin_size'),
            lc_name=kwargs.get('lc_name'),
            pculist=kwargs.get('pculist'),
            workers=workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )
    else:
        extract_std2_lightcurves(
            root_dir=root_dir,
            layerlist=kwargs.get('layerlist'),
            time_bins=kwargs.get('time_bins'),
            lc_name=kwargs.get('lc_name'),
            pculist=kwargs.get('pculist'),
            chmin=kwargs.get('chmin'),
            chmax=kwargs.get('chmax'),
            workers=workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--type', choices=['std1', 'std2'])
    parser.add_argument('--bin-size', help='STD1 only: bin size in seconds (default 0.125)')
    parser.add_argument('--layerlist', help='STD2 only: layer selection 1/2/3/ALL (default ALL)')
    parser.add_argument('--time-bins', help='STD2 only: bin size in seconds, multiple of 16 (default 16)')
    parser.add_argument('--chmin', help='STD2 only: min channel 0-255 (default 0)')
    parser.add_argument('--chmax', help='STD2 only: max channel 0-255 (default 255)')
    parser.add_argument('--lc-name', help='Output LC filename (default std1.lc or light.lc)')
    parser.add_argument('--pculist', help='PCU list comma-separated (default 2)')
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-skip-existing', action='store_true')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    skip_existing = False if args.no_skip_existing else None
    generate_lightcurves(
        args.directory,
        lc_type=args.type,
        bin_size=args.bin_size,
        layerlist=args.layerlist,
        time_bins=args.time_bins,
        chmin=args.chmin,
        chmax=args.chmax,
        lc_name=args.lc_name,
        pculist=args.pculist,
        workers=args.workers,
        skip_existing=skip_existing,
        interactive=not args.no_interactive,
    )
