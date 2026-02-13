"""09 - Power Density Spectrum Generation."""
import logging
import subprocess
import multiprocessing
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_int

logger = logging.getLogger(__name__)

def process_powspec(analysis_dir: Path, lc_file: str, binning: str, 
                   rebin: str, output_png: str):
    """Run powspec to generate power spectrum."""
    script = analysis_dir / "scriptpowspec.txt"
    lines = [
        lc_file,
        "-",
        binning,
        "8192",
        "INDEF",
        rebin,
        "default",
        "yes",
        "/xw",
        f"hardcopy {output_png}",
        f"Wd {analysis_dir / lc_file.replace('.lc', '.qdp')}",
        "q"
    ]
    script.write_text("\n".join(lines) + "\n")
    
    out = analysis_dir / "pow.txt"
    with script.open('r') as inp, out.open('w') as fout:
        subprocess.run(
            ['powspec', 'norm=-2', 'window=none'],
            stdin=inp, stdout=fout, stderr=subprocess.STDOUT, check=True
        )
    script.unlink(missing_ok=True)

def process_fplot(analysis_dir: Path, lc_file: str):
    """Run fplot to extract frequency vs power."""
    fps_file = analysis_dir / lc_file.replace('.lc', '.fps')
    script = analysis_dir / "scriplot.txt"
    lines = [
        str(fps_file),
        "FREQUENCY[XAX_E]",
        "POWER[ERROR]",
        "-",
        "/xw",
        "log xy on",
        f"wd {analysis_dir / lc_file.replace('.lc', '_fps')}",
        "q"
    ]
    script.write_text("\n".join(lines) + "\n")
    
    subprocess.run(['fplot'], stdin=script.open('r'), check=True, capture_output=True)
    script.unlink(missing_ok=True)
    
    # Extract and transform .qdp
    qdp = analysis_dir / f"{lc_file.replace('.lc', '_fps')}.qdp"
    if qdp.exists():
        temp_qdp = analysis_dir / "temp.qdp"
        temp_dat = analysis_dir / "temp.dat"
        
        with qdp.open('r') as fin, temp_qdp.open('w') as fq:
            for i, line in enumerate(fin):
                if i >= 3:  # Skip first 3 header lines
                    fq.write(line)
        
        with temp_qdp.open('r') as fq, temp_dat.open('w') as fd:
            for line in fq:
                parts = line.split()
                if len(parts) >= 4:
                    f1, f2, f3, f4 = map(float, parts[:4])
                    fd.write(f"{f1-f2} {f1+f2} {f3} {f4}\n")

def process_flx2xsp(results_dir: Path, analysis_dir: Path):
    """Convert flux to spectrum format."""
    script = results_dir / "pds.txt"
    lines = [
        str(analysis_dir / "temp.dat"),
        str(analysis_dir / "pds-src.pha"),
        str(analysis_dir / "pds-rsp.pha"),
        "$"
    ]
    script.write_text("\n".join(lines) + "\n")
    
    out = analysis_dir / "pds.txt"
    with script.open('r') as inp, out.open('w') as fout:
        subprocess.run(
            ['flx2xsp'], stdin=inp, stdout=fout, stderr=subprocess.STDOUT, check=True
        )
    script.unlink(missing_ok=True)

def compute_pds_single(results_dir: Path, lc_file: str, binning: str, 
                       rebin: str, output_png: str) -> str:
    """Generate PDS for a single results directory."""
    analysis = results_dir / "Analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    
    # Check if lightcurve file exists
    if not (analysis / lc_file).exists():
        raise FileNotFoundError(f"No {lc_file} in {analysis}")
    
    process_powspec(analysis, lc_file, binning, rebin, output_png)
    process_fplot(analysis, lc_file)
    process_flx2xsp(results_dir, analysis)
    
    return results_dir.name

def compute_pds(root_dir: Optional[Path] = None, lc_file: Optional[str] = None,
                binning: Optional[str] = None, rebin: Optional[str] = None,
                output_png: Optional[str] = None, workers: Optional[int] = None,
                interactive: bool = True):
    """Generate Power Density Spectra using powspec, fplot, and flx2xsp."""
    require_heasoft_tool('powspec')
    require_heasoft_tool('fplot')
    require_heasoft_tool('flx2xsp')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        lc_file = get_input("Lightcurve filename", "event.lc", lc_file)
        binning = get_input("Binning (default -1 for auto)", "-1", binning)
        rebin = get_input("Rebin factor", "-1.03", rebin)
        output_png = get_input("Output PNG name", "pds.png/png", output_png)
        workers = get_int("Workers", multiprocessing.cpu_count(), workers)
    else:
        root_dir = root_dir or Path('.')
        lc_file = lc_file or "event.lc"
        binning = binning or "-1"
        rebin = rebin or "-1.03"
        output_png = output_png or "pds.png/png"
        workers = workers or multiprocessing.cpu_count()
    
    dirs = sorted(d for d in root_dir.glob("*-results") if d.is_dir())
    if not dirs:
        logger.warning("No *-results directories found")
        return
    
    logger.info(f"Processing {len(dirs)} directories with {workers} workers")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(compute_pds_single, d, lc_file, binning, 
                                   rebin, output_png): d for d in dirs}
        for future in as_completed(futures):
            d = futures[future]
            try:
                result = future.result()
                logger.info(f"✓ {result}")
            except Exception as e:
                logger.error(f"✗ {d.name}: {e}")
    
    logger.info("Complete")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--lc-file', default='event.lc')
    parser.add_argument('--binning', default='-1')
    parser.add_argument('--rebin', default='-1.03')
    parser.add_argument('--workers', type=int)
    args = parser.parse_args()
    compute_pds(args.directory, args.lc_file, args.binning, args.rebin,
                interactive=args.directory is None)
