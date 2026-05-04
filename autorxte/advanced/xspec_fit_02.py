"""XSPEC template runner.

Given a single .xcm file you produced by hand in XSPEC (`save all best.xcm`),
this distributes it across every <obsid>-results/Analysis/ in a dataset,
rewrites the data/response/background filenames so each instance loads its
own spectra, and mass-runs xspec with the operations you ask for: fit,
per-parameter error, flux integration, gain fit, freeze/thaw. Per-target
log files are parsed into a single CSV.

The pre-repo workflow this matches lives in refit_revision/xrt/flux_cal.txt
and refit_revision/astrosat/same_folder_xcm_runner.txt.
"""
import csv
import logging
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from autorxte.utils import require_heasoft_tool, run_heasoft_pty, HEASoftToolError
from autorxte.utils.interactive import (
    get_path, get_input, get_float, get_yes_no, get_int,
)

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

# XSPEC commands we may rewrite the path argument of. Format:
#   data [grp:][num] <path>
#   response [grp:][num] <path>
#   backgrnd [num] <path>
#   arf [grp:][num] <path>
#   corfile [grp:][num] <path>
PATH_CMDS = ('data', 'response', 'arf', 'backgrnd', 'back', 'corfile')


def _is_results_dir_for_obsid(entry: Path) -> bool:
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def rewrite_xcm_paths(template_text: str, target_dir: Path) -> str:
    """Rewrite data/response/backgrnd/arf/corfile paths in an XSPEC .xcm so
    each path keeps its basename but points into target_dir.

    Lines that start with one of the PATH_CMDS are split into
    ``<cmd> [<group spec>] <path>`` and the path is replaced by
    ``target_dir/<basename(original_path)>``.

    Other lines (model, ignore, fit settings, parameter values) are left
    untouched.
    """
    out_lines = []
    for line in template_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            out_lines.append(line)
            continue

        tokens = stripped.split()
        cmd = tokens[0].lower()
        if cmd not in PATH_CMDS:
            out_lines.append(line)
            continue

        # Last token is the path. (Earlier tokens are the command and
        # optional group/index specifiers like "1:1" or "1".)
        old_path = tokens[-1]
        new_path = str(target_dir / Path(old_path).name)
        new_tokens = tokens[:-1] + [new_path]
        # Preserve leading whitespace if any.
        leading = line[: len(line) - len(line.lstrip())]
        out_lines.append(leading + ' '.join(new_tokens))
    return '\n'.join(out_lines) + ('\n' if template_text.endswith('\n') else '')


def _parse_int_list(spec: Optional[str]) -> List[int]:
    """Parse a comma-separated int spec ('1,2,3') or range ('1-6') or mix
    ('1,3-5,7') into a list of ints. None returns []."""
    if not spec:
        return []
    out: List[int] = []
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part and not part.startswith('-'):
            a, b = part.split('-', 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _build_xspec_script(
    xcm_filename: str,
    energy_range: Optional[Tuple[float, float]],
    freeze: List[int],
    thaw: List[int],
    fit_iter: int,
    error_params: List[int],
    flux_range: Optional[Tuple[float, float]],
    gain_groups: List[int],
    save_basename: str,
) -> str:
    """Build the XSPEC stdin script.

    Order matters: load model, apply ignore/freeze/thaw, optionally gain
    fit, then fit, then errors and flux, then save.
    """
    lines: List[str] = [f"@{xcm_filename}"]
    if energy_range is not None:
        emin, emax = energy_range
        lines += [f"ignore **-{emin}", f"ignore {emax}-**"]
    for p in freeze:
        lines.append(f"freeze {p}")
    for p in thaw:
        lines.append(f"thaw {p}")
    for g in gain_groups:
        # Plain `gain fit N` (without `:1`) avoids a re-prompt under non-tty.
        lines.append(f"gain fit {g}")
    lines.append(f"fit {fit_iter}")
    for p in error_params:
        lines.append(f"error {p}")
    if flux_range is not None:
        emin, emax = flux_range
        lines.append(f"flux {emin} {emax}")
    lines += [
        f"save all {save_basename}_bestfit.xcm",
        "exit",
    ]
    return "\n".join(lines) + "\n"


# ----- Log parsing ----------------------------------------------------------

# "Test statistic : Chi-Squared                 5945.33     using 52 bins."
_RE_CHI2 = re.compile(r'Chi-Squared\s+([0-9.eE+-]+)\s+using')
_RE_DOF = re.compile(r'with\s+(\d+)\s+degrees of freedom')

# Post-fit parameter table row:
#   "   1    1   TBabs      nH         10^22    2.46373E-16  +/-  -1.00000"
# The value is the non-whitespace token immediately before "+/-".
_RE_PARAM = re.compile(
    r'^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+).*?(\S+)\s+\+/-\s*(\S+)',
    re.MULTILINE,
)

# `error N` output:
#   "     2      1.50343    1.70125   (-0.151904,0.0451)"
# (parameter index, lower bound, upper bound, then the +/- range in parens)
_RE_ERROR = re.compile(
    r'^\s*(\d+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+\(\s*'
    r'([0-9.eE+-]+)\s*,\s*([0-9.eE+-]+)\s*\)',
    re.MULTILINE,
)

# `flux Emin Emax` output:
#   " Model Flux  0.02343 photons (1.234e-10 ergs/cm^2/s) range (3.0 - 30.0 keV)"
_RE_FLUX = re.compile(
    r'Model\s+Flux\s+([0-9.eE+-]+)\s+photons\s+\(([0-9.eE+-]+)\s+ergs',
)


def parse_xspec_log(log_text: str, obsid: str, error_params: List[int],
                    flux_range: Optional[Tuple[float, float]]) -> Dict:
    """Pull chi^2/dof, per-parameter values, error confidence bounds, and
    flux out of an XSPEC log."""
    results: Dict[str, str] = {'obsid': obsid, 'chi2': 'N/A',
                                'dof': 'N/A', 'reduced_chi2': 'N/A'}

    chi2_hits = list(_RE_CHI2.finditer(log_text))
    dof_hits = list(_RE_DOF.finditer(log_text))
    if chi2_hits:
        results['chi2'] = chi2_hits[-1].group(1)
    if dof_hits:
        results['dof'] = dof_hits[-1].group(1)
    try:
        if results['chi2'] != 'N/A' and results['dof'] != 'N/A':
            results['reduced_chi2'] = (
                f"{float(results['chi2']) / float(results['dof']):.4f}"
            )
    except (ValueError, ZeroDivisionError):
        pass

    # Per-parameter best-fit values from the post-fit summary table.
    for m in _RE_PARAM.finditer(log_text):
        par_num, _grp, comp, parm, value, _err = m.groups()
        key = f"p{par_num}_{comp}_{parm}"
        results[key] = value
        results[f"{key}_quoted_err"] = _err

    # `error` results: keep low/high bounds for each param we asked about.
    if error_params:
        wanted = set(error_params)
        for m in _RE_ERROR.finditer(log_text):
            p, lo, hi, dlo, dhi = m.groups()
            if int(p) in wanted:
                results[f"p{p}_err_lo"] = lo
                results[f"p{p}_err_hi"] = hi
                results[f"p{p}_err_minus"] = dlo
                results[f"p{p}_err_plus"] = dhi

    # `flux` result: the integrated photon flux + erg flux for the band.
    if flux_range is not None:
        flux_hits = list(_RE_FLUX.finditer(log_text))
        if flux_hits:
            ph, erg = flux_hits[-1].groups()
            emin, emax = flux_range
            tag = f"flux_{emin}_{emax}"
            results[f"{tag}_photons"] = ph
            results[f"{tag}_ergs_cm2_s"] = erg

    return results


# ----- The runner -----------------------------------------------------------

def apply_xcm_to_one(
    results_dir: Path,
    template_text: str,
    energy_range: Optional[Tuple[float, float]],
    freeze: List[int],
    thaw: List[int],
    fit_iter: int,
    error_params: List[int],
    flux_range: Optional[Tuple[float, float]],
    gain_groups: List[int],
    name: str,
    rewrite_paths: bool,
    timeout: int,
) -> Dict:
    """Apply the template xcm to one obsid and return parsed results."""
    obsid = results_dir.name[:-len('-results')]
    analysis = results_dir / "Analysis"
    if not analysis.is_dir():
        raise FileNotFoundError(f"{obsid}: no Analysis/ dir")

    target_xcm = analysis / f"{name}.xcm"
    save_xcm = analysis / f"{name}_bestfit.xcm"
    log_path = analysis / f"{name}.log"

    # Write the per-target xcm.
    if rewrite_paths:
        target_xcm.write_text(rewrite_xcm_paths(template_text, analysis))
    else:
        target_xcm.write_text(template_text)

    script = _build_xspec_script(
        xcm_filename=target_xcm.name,
        energy_range=energy_range,
        freeze=freeze, thaw=thaw,
        fit_iter=fit_iter,
        error_params=error_params,
        flux_range=flux_range,
        gain_groups=gain_groups,
        save_basename=name,
    )

    try:
        rc, output = run_heasoft_pty(
            ['xspec'], input_text=script, cwd=analysis, timeout=timeout,
            must_exist=[save_xcm],
        )
    except HEASoftToolError as e:
        # Capture whatever output we got for diagnosis.
        log_path.write_text(str(e))
        logger.error(f"FAIL {obsid}: {e}")
        raise

    log_path.write_text(output)
    return parse_xspec_log(output, obsid, error_params, flux_range)


def apply_xcm_template(
    template: Optional[Path] = None,
    root_dir: Optional[Path] = None,
    name: Optional[str] = None,
    energy_range: Optional[Tuple[float, float]] = None,
    fit_iter: int = 100000,
    error_spec: Optional[str] = None,
    flux_range: Optional[Tuple[float, float]] = None,
    gain_groups_spec: Optional[str] = None,
    freeze_spec: Optional[str] = None,
    thaw_spec: Optional[str] = None,
    rewrite_paths: Optional[bool] = None,
    workers: Optional[int] = None,
    skip_existing: Optional[bool] = None,
    timeout: int = 1800,
    output_csv: Optional[Path] = None,
    interactive: bool = True,
):
    """Distribute `template` across every <obsid>-results/Analysis/ under
    root_dir, run xspec on each, and write a CSV with the parsed results.

    Args:
        template: path to the master .xcm
        root_dir: directory containing <obsid>-results/ subdirs
        name: output basename (default: template's stem). Per-target
            outputs are <analysis>/<name>.xcm, <name>_bestfit.xcm, <name>.log
        energy_range: (Emin, Emax) keV. Adds `ignore **-Emin Emax-**`.
        fit_iter: iterations passed to `fit`
        error_spec: "1,3-5,7" form. Each listed param gets `error N`.
        flux_range: (Emin, Emax) keV. Adds `flux Emin Emax`.
        gain_groups_spec: "1,2" form. Adds `gain fit N` for each group.
        freeze_spec, thaw_spec: same form, for `freeze N`/`thaw N`.
        rewrite_paths: if True (default), rewrite `data`/`response`/
            `backgrnd`/`arf`/`corfile` paths so each instance points at
            its own Analysis/ files (basename preserved). If False, copy
            the template verbatim (assumes it works in cwd=Analysis/).
        workers: parallel xspec workers
        skip_existing: skip when <name>_bestfit.xcm already present
        output_csv: where to write the aggregated results
        interactive: prompt for missing args
    """
    require_heasoft_tool('xspec')

    if interactive:
        template = get_path("Template .xcm path", arg_value=template)
        root_dir = get_path("Root directory", Path('.'), root_dir)
        name = get_input("Output basename",
                         template.stem if template else "fit", name)
        emin = get_float("Energy min keV (blank to skip ignore)",
                          arg_value=energy_range[0] if energy_range else None,
                          default=3.0)
        emax = get_float("Energy max keV (blank to skip ignore)",
                          arg_value=energy_range[1] if energy_range else None,
                          default=30.0)
        energy_range = (emin, emax) if (emin and emax) else None
        error_spec = get_input(
            "error params (e.g. 1,3-5 or blank)", arg_value=error_spec,
        )
        do_flux = get_yes_no("Compute flux?", False)
        if do_flux:
            fmin = get_float("flux Emin keV", 3.0)
            fmax = get_float("flux Emax keV", 30.0)
            flux_range = (fmin, fmax)
        gain_groups_spec = get_input(
            "gain-fit datagroups (e.g. 1,2 or blank)",
            arg_value=gain_groups_spec,
        )
        freeze_spec = get_input("freeze params (or blank)",
                                 arg_value=freeze_spec)
        thaw_spec = get_input("thaw params (or blank)", arg_value=thaw_spec)
        rewrite_paths = get_yes_no(
            "Rewrite data/response/backgrnd paths to each Analysis/?",
            True, rewrite_paths,
        )
        workers = get_int("Parallel xspec workers", 1, workers)
        skip_existing = get_yes_no(
            "Skip targets where <name>_bestfit.xcm already exists?",
            True, skip_existing,
        )
        output_csv = get_path(
            "Output CSV path", Path("xspec_batch.csv"), output_csv,
        )
    else:
        if template is None:
            raise ValueError("apply_xcm_template needs `template` "
                              "(--xcm path/to/template.xcm)")
        root_dir = root_dir or Path('.')
        name = name or template.stem
        skip_existing = skip_existing if skip_existing is not None else True
        rewrite_paths = rewrite_paths if rewrite_paths is not None else True
        workers = workers if workers is not None else 1
        output_csv = output_csv or Path("xspec_batch.csv")

    template = Path(template)
    if not template.is_file():
        raise ValueError(f"Template .xcm not found: {template}")
    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    template_text = template.read_text()

    error_params = _parse_int_list(error_spec)
    gain_groups = _parse_int_list(gain_groups_spec)
    freeze = _parse_int_list(freeze_spec)
    thaw = _parse_int_list(thaw_spec)

    # Plan tasks.
    tasks: List[Path] = []
    for results_dir in sorted(root_dir.iterdir()):
        if not _is_results_dir_for_obsid(results_dir):
            continue
        analysis = results_dir / "Analysis"
        if not analysis.is_dir():
            logger.warning(f"{results_dir.name}: no Analysis/; skip")
            continue
        save_xcm = analysis / f"{name}_bestfit.xcm"
        if skip_existing and save_xcm.exists() and save_xcm.stat().st_size > 0:
            logger.info(f"SKIP {results_dir.name[:-len('-results')]} "
                         f"({name}_bestfit.xcm already exists)")
            continue
        tasks.append(results_dir)

    if not tasks:
        logger.warning("No work to do.")
        return

    logger.info(
        f"Running xspec on {len(tasks)} obsids using template={template.name}"
        f" (workers={workers})"
    )
    if error_params:
        logger.info(f"  error params: {error_params}")
    if flux_range:
        logger.info(f"  flux: {flux_range[0]}-{flux_range[1]} keV")
    if gain_groups:
        logger.info(f"  gain fit groups: {gain_groups}")
    if freeze:
        logger.info(f"  freeze: {freeze}")
    if thaw:
        logger.info(f"  thaw: {thaw}")

    rows: List[Dict] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                apply_xcm_to_one,
                d, template_text, energy_range, freeze, thaw,
                fit_iter, error_params, flux_range, gain_groups,
                name, rewrite_paths, timeout,
            ): d for d in tasks
        }
        for fut in as_completed(futures):
            d = futures[fut]
            try:
                row = fut.result()
                rows.append(row)
                logger.info(
                    f"OK   {row['obsid']}  chi2={row['chi2']}/{row['dof']}"
                    f" = {row['reduced_chi2']}"
                )
            except (HEASoftToolError, FileNotFoundError) as e:
                failures += 1
                rows.append({'obsid': d.name, 'error': str(e)[:200]})
            except Exception as e:
                failures += 1
                logger.error(
                    f"FAIL {d.name}: {type(e).__name__}: {e}"
                )
                rows.append({'obsid': d.name,
                              'error': f"{type(e).__name__}: {e}"})

    # Union of all keys across rows so the CSV header has every column we saw.
    all_keys: List[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                all_keys.append(k)
    with open(output_csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=all_keys)
        w.writeheader()
        w.writerows(rows)
    logger.info(f"Results -> {output_csv}")

    if failures:
        logger.warning(f"Done with {failures}/{len(tasks)} failures.")
    else:
        logger.info(f"Done. {len(tasks)} obsids fit.")


# Backwards-compatible alias for the old API name. Prefer apply_xcm_template.
fit_all_spectra = apply_xcm_template


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(
        description='Apply a template .xcm to a batch of spectra and aggregate results.'
    )
    parser.add_argument('--xcm', dest='template', type=Path,
                        help='Template .xcm produced by your interactive XSPEC fit')
    parser.add_argument('--directory', type=Path,
                        help='Root directory containing <obsid>-results/')
    parser.add_argument('--name',
                        help='Output basename (default: template stem)')
    parser.add_argument('--energy', help='Energy range for ignore, e.g. 3-30 (keV)')
    parser.add_argument('--fit-iter', type=int, default=100000,
                        help='Iterations passed to xspec `fit` (default 100000)')
    parser.add_argument('--error',
                        help='Param indices for `error N`. Spec like "1,3-5".')
    parser.add_argument('--flux', help='Flux band like "3-30" (keV)')
    parser.add_argument('--gain', dest='gain_groups',
                        help='Datagroup indices for `gain fit`. Spec like "1,2".')
    parser.add_argument('--freeze', help='Param indices to `freeze` before fit')
    parser.add_argument('--thaw', help='Param indices to `thaw` before fit')
    parser.add_argument('--no-rewrite', action='store_true',
                        help='Use the template verbatim instead of rewriting paths.')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--no-skip-existing', action='store_true')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--output', dest='output_csv', type=Path,
                        default=Path('xspec_batch.csv'))
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()

    def _parse_range(s: Optional[str]) -> Optional[Tuple[float, float]]:
        if not s:
            return None
        a, b = s.split('-', 1)
        return (float(a), float(b))

    apply_xcm_template(
        template=args.template,
        root_dir=args.directory,
        name=args.name,
        energy_range=_parse_range(args.energy),
        fit_iter=args.fit_iter,
        error_spec=args.error,
        flux_range=_parse_range(args.flux),
        gain_groups_spec=args.gain_groups,
        freeze_spec=args.freeze,
        thaw_spec=args.thaw,
        rewrite_paths=not args.no_rewrite,
        workers=args.workers,
        skip_existing=False if args.no_skip_existing else None,
        timeout=args.timeout,
        output_csv=args.output_csv,
        interactive=not args.no_interactive,
    )
