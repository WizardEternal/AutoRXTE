"""09 - Power Density Spectrum Generation.

Three-tool chain per ObsID, all run with cwd=<obsid>-results/Analysis/ so
the outputs land in Analysis/ with short basenames:

  powspec   <event.lc>       -> pds.fps                     (FFT power spectrum)
  fplot     pds.fps          -> pds_fps.qdp                 (frequency vs power text)
            (then transformed to pds.dat via simple parsing of the QDP)
  flx2xsp   pds.dat          -> pds-src.pha + pds-rsp.pha   (XSPEC-readable)

Plot device defaults to /null so this works on headless machines with no
DISPLAY. The .fps and .pha outputs are what downstream analysis cares
about; pass --plot-device <dev>/png to also save a PNG of the spectrum.
"""
import logging
import multiprocessing
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List

from autorxte.utils import run_heasoft_pty, HEASoftToolError, require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int, get_yes_no
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

# Default output names (in Analysis/).
DEFAULT_LC = "event.lc"
PDS_FPS = "pds.fps"
PDS_QDP = "pds_fps.qdp"
PDS_DAT = "pds.dat"
PDS_SRC = "pds-src.pha"
PDS_RSP = "pds-rsp.pha"


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def _run_powspec(
    analysis: Path, lc_file: str, binning: str, rebin: str, plot_device: str,
):
    """powspec: read lc, write pds.fps. Stdin script handles its prompt sequence."""
    fps_path = analysis / PDS_FPS
    if fps_path.exists():
        fps_path.unlink()

    # powspec prompts (when window/outfile/norm/clobber are on the cmdline):
    #   cfile1, dtnb, nbint, nintfm, rebin, plot, [plotdev]
    # Then if plotdev != /null, PGPLOT may take subcommands; we send "q".
    # We pass plot=no when plot_device=/null so PGPLOT is never invoked.
    plot_yes = "no" if plot_device == "/null" else "yes"
    lines = [
        lc_file,    # cfile1
        binning,    # dtnb
        "8192",     # nbint
        "INDEF",    # nintfm
        rebin,      # rebin
        plot_yes,   # plot
    ]
    if plot_yes == "yes":
        lines.append(plot_device)
        lines.append("q")
    script = "\n".join(lines) + "\n"

    cmd = ['powspec', 'norm=-2', 'window=-', 'outfile=pds', 'clobber=yes']
    run_heasoft_pty(
        cmd,
        input_text=script,
        cwd=analysis,
        timeout=600,
        must_exist=[fps_path],
    )


def _run_fplot(analysis: Path):
    """fplot: read pds.fps, write pds_fps.qdp text dump."""
    qdp_path = analysis / PDS_QDP
    if qdp_path.exists():
        qdp_path.unlink()

    # fplot prompts: infile, xparm, yparm, plotdev, then PGPLOT subcommands.
    script = "\n".join([
        PDS_FPS,
        "FREQUENCY[XAX_E]",
        "POWER[ERROR]",
        "-",
        "/null",
        f"wd pds_fps",
        "q",
    ]) + "\n"
    run_heasoft_pty(
        ['fplot'],
        input_text=script,
        cwd=analysis,
        timeout=120,
        must_exist=[qdp_path],
    )


def _qdp_to_dat(analysis: Path):
    """Transform QDP (FREQ ERR_F POWER ERR_P) into the 4-column format flx2xsp wants:
       lo  hi  rate  err
    where lo = freq - half-bin, hi = freq + half-bin.
    """
    qdp_path = analysis / PDS_QDP
    dat_path = analysis / PDS_DAT
    with qdp_path.open() as fin, dat_path.open('w') as fout:
        for i, line in enumerate(fin):
            if i < 3:
                continue  # QDP header
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                f, df, p, dp = (float(x) for x in parts[:4])
            except ValueError:
                continue
            fout.write(f"{f - df} {f + df} {p} {dp}\n")


def _run_flx2xsp(analysis: Path):
    """flx2xsp: read pds.dat, write pds-src.pha + pds-rsp.pha."""
    src_path = analysis / PDS_SRC
    rsp_path = analysis / PDS_RSP
    for p in (src_path, rsp_path):
        if p.exists():
            p.unlink()

    # flx2xsp expects: infile, phafile, rspfile, "$" or other terminator.
    script = "\n".join([
        PDS_DAT,
        PDS_SRC,
        PDS_RSP,
        "$",
    ]) + "\n"
    run_heasoft_pty(
        ['flx2xsp'],
        input_text=script,
        cwd=analysis,
        timeout=60,
        must_exist=[src_path, rsp_path],
    )


def compute_pds_single(
    results_dir: Path,
    lc_file: str,
    binning: str,
    rebin: str,
    plot_device: str,
) -> str:
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / "Analysis"
    if not analysis.is_dir():
        raise FileNotFoundError(f"{obsid}: no Analysis/; run earlier stages first")
    if not (analysis / lc_file).exists():
        raise FileNotFoundError(f"{obsid}: no {lc_file} in Analysis/; run 'extract' or 'lightcurves'")

    try:
        _run_powspec(analysis, lc_file, binning, rebin, plot_device)
        _run_fplot(analysis)
        _qdp_to_dat(analysis)
        _run_flx2xsp(analysis)
    except HEASoftToolError as e:
        logger.error(f"FAIL {obsid}: {e}")
        raise

    return obsid


def compute_pds(
    root_dir: Optional[Path] = None,
    lc_file: Optional[str] = None,
    binning: Optional[str] = None,
    rebin: Optional[str] = None,
    plot_device: Optional[str] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    interactive: bool = True,
):
    """Build PDS for every <obsid>-results/Analysis under root_dir."""
    require_heasoft_tool('powspec')
    require_heasoft_tool('fplot')
    require_heasoft_tool('flx2xsp')

    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        lc_file = get_input("Lightcurve filename in Analysis/", DEFAULT_LC, lc_file)
        binning = get_input("Binning (negative = auto rebin)", "-1", binning)
        rebin = get_input("Rebin factor", "-1.03", rebin)
        plot_device = get_input(
            "PGPLOT plot device (/null = headless, e.g. pds.png/png to save)",
            "/null", plot_device,
        )
        workers = get_int("Parallel workers", multiprocessing.cpu_count(), workers)
        skip_existing = get_yes_no(
            f"Skip obsids whose Analysis/{PDS_SRC} already exists?", True, skip_existing
        )
    else:
        root_dir = root_dir or Path('.')
        lc_file = lc_file or DEFAULT_LC
        binning = binning or "-1"
        rebin = rebin or "-1.03"
        plot_device = plot_device or "/null"
        workers = workers or multiprocessing.cpu_count()
        skip_existing = skip_existing if skip_existing is not None else True

    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    tasks: List[Path] = []
    for results_dir in sorted(root_dir.iterdir()):
        if not _is_results_dir_for_obsid(results_dir):
            continue
        analysis = results_dir / "Analysis"
        if not analysis.is_dir():
            logger.warning(f"{results_dir.name[:-len('-results')]}: no Analysis/; skip")
            continue
        if not (analysis / lc_file).exists():
            logger.warning(
                f"{results_dir.name[:-len('-results')]}: no {lc_file} in Analysis/; skip"
            )
            continue
        if skip_existing and (analysis / PDS_SRC).exists() \
                and (analysis / PDS_SRC).stat().st_size > 0:
            logger.info(f"SKIP {results_dir.name[:-len('-results')]} ({PDS_SRC})")
            continue
        tasks.append(results_dir)

    if not tasks:
        logger.warning("No work to do.")
        return

    logger.info(f"Building {len(tasks)} PDS with {workers} workers")

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                compute_pds_single, d, lc_file, binning, rebin, plot_device,
            ): d
            for d in tasks
        }
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
        logger.warning(f"Done with {failures}/{len(tasks)} failures.")
    else:
        logger.info(f"Done. Built {len(tasks)} PDS.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--lc-file')
    parser.add_argument('--binning')
    parser.add_argument('--rebin')
    parser.add_argument('--plot-device', help='PGPLOT device (default /null)')
    parser.add_argument('--workers', type=int)
    parser.add_argument('--no-skip-existing', action='store_true')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()
    skip_existing = False if args.no_skip_existing else None
    compute_pds(
        args.directory,
        lc_file=args.lc_file,
        binning=args.binning,
        rebin=args.rebin,
        plot_device=args.plot_device,
        workers=args.workers,
        skip_existing=skip_existing,
        interactive=not args.no_interactive,
    )
