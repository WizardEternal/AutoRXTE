"""04 - Bitmask Distribution.

Copies an RXTE PCA bitmask file into every <obsid>-results/Analysis/.
seextrct in extraction_06 reads this file by name from Analysis/ to filter
events by the EVENT bit pattern.

The bitmask collection lives at bitmasks/ in the repo root (see
bitmasks/README.md for the catalog and when to use which). The default
choice is `bitfile_M` (alias `bitmask_event`), which keeps every event
except the time marker. Power users pick a more specific selection
(detectors, layers, AND vs OR mode) by name with --bitmask.
"""
import logging
import re
import shutil
from pathlib import Path
from typing import Optional, List, Dict

from autorxte.utils.interactive import get_path, get_yes_no, get_input

logger = logging.getLogger(__name__)

OBSID_RE = re.compile(r'^\d{5}-\d{2}-\d{2}-\d{2}[A-Z]?$')

# Filename downstream code (extraction_06) reads from Analysis/.
CANONICAL_NAME = 'bitmask_event'


def _bitmask_search_roots() -> List[Path]:
    """Directories searched for bitmask files (in priority order)."""
    pkg_root = Path(__file__).resolve().parent.parent  # autorxte/
    repo_root = pkg_root.parent  # AutoRXTE-main/
    return [
        Path.cwd() / 'bitmasks',
        repo_root / 'bitmasks',
        pkg_root / 'bitmasks',
        Path.home() / '.autorxte' / 'bitmasks',
    ]


def list_available_bitmasks() -> Dict[str, Path]:
    """Find every shipped bitmask file. Returns {short_name: full_path}.

    `short_name` is the basename. If two roots ship the same name, the first
    root in _bitmask_search_roots() wins.
    """
    found: Dict[str, Path] = {}
    for root in _bitmask_search_roots():
        if not root.is_dir():
            continue
        for f in root.rglob('bitfile_*'):
            if f.is_file() and f.name not in found:
                found[f.name] = f
        # Also pick up the canonical alias if present.
        alias = root / CANONICAL_NAME
        if alias.is_file() and CANONICAL_NAME not in found:
            found[CANONICAL_NAME] = alias
    return found


def resolve_bitmask(name_or_path: Optional[str]) -> Path:
    """Resolve a bitmask reference to a real file path.

    Accepts: a short name like `bitfile_gx_d012`, the alias `bitmask_event`,
    or a full path to a bitmask file. Raises ValueError if not found.
    """
    if name_or_path is None:
        # Default: bitmask_event (= bitfiles_d/bitfile_M).
        name_or_path = CANONICAL_NAME

    p = Path(name_or_path)
    if p.is_file():
        return p

    # Treat as a short name to look up in the shipped collection.
    available = list_available_bitmasks()
    if name_or_path in available:
        return available[name_or_path]

    raise ValueError(
        f"Bitmask {name_or_path!r} not found. "
        f"Pass a path or one of the named bitmasks "
        f"(see `autorxte bitmask --list`)."
    )


def _is_results_dir_for_obsid(entry: Path) -> bool:
    """True if entry is <obsid>-results where obsid matches the RXTE pattern."""
    if not entry.is_dir() or not entry.name.endswith('-results'):
        return False
    return bool(OBSID_RE.match(entry.name[:-len('-results')]))


def copy_bitmask_to_results(
    root_dir: Optional[Path] = None,
    bitmask_path: Optional[str] = None,
    overwrite: Optional[bool] = None,
    interactive: bool = True,
):
    """Copy `bitmask_path` into every <obsid>-results/Analysis/ under root_dir,
    renamed to `bitmask_event` (the name extraction_06 expects)."""
    if interactive:
        bitmask_path = get_input(
            f"Bitmask name or path", CANONICAL_NAME,
            arg_value=bitmask_path,
        )
        root_dir = get_path("Root directory", Path('.'), root_dir)
        overwrite = get_yes_no("Overwrite existing bitmask in Analysis/?", False, overwrite)
    else:
        if bitmask_path is None:
            bitmask_path = CANONICAL_NAME
        root_dir = root_dir or Path('.')
        overwrite = overwrite if overwrite is not None else False

    src = resolve_bitmask(bitmask_path)
    if not root_dir.is_dir():
        raise ValueError(f"Root directory does not exist: {root_dir}")

    results_dirs = [e for e in sorted(root_dir.iterdir()) if _is_results_dir_for_obsid(e)]
    if not results_dirs:
        logger.warning(
            f"No <obsid>-results directories found under {root_dir}. "
            f"Run 'prepare' first."
        )
        return

    logger.info(f"Distributing {src.name} (as {CANONICAL_NAME}) across "
                f"{len(results_dirs)} results dirs")

    copied = skipped = missing = 0
    for results_dir in results_dirs:
        analysis = results_dir / 'Analysis'
        if not analysis.is_dir():
            logger.warning(f"{results_dir.name}: no Analysis/ subdir; run 'organize' first")
            missing += 1
            continue
        dest = analysis / CANONICAL_NAME
        if dest.exists() and not overwrite:
            skipped += 1
            logger.info(f"SKIP {results_dir.name} (already has {CANONICAL_NAME})")
            continue
        shutil.copy2(str(src), str(dest))
        copied += 1
        logger.info(f"OK   {results_dir.name}")

    logger.info(
        f"Done. Copied={copied}  skipped={skipped}  missing-Analysis={missing}  "
        f"(of {len(results_dirs)} results dirs)"
    )


def print_bitmask_list():
    """Print the shipped bitmask collection grouped by HEASARC category."""
    available = list_available_bitmasks()
    if not available:
        print("No bitmask files found in any search root:")
        for r in _bitmask_search_roots():
            print(f"  - {r}")
        return

    # Group by parent dir relative to its shipping root (e.g. bitfiles_gx/and).
    groups: Dict[str, List[str]] = {}
    for name, path in sorted(available.items()):
        # Find which search root this file lives under.
        rel_parent = '(top level)'
        for root in _bitmask_search_roots():
            try:
                rel = path.relative_to(root)
                rel_parent = str(rel.parent) if rel.parent != Path('.') else '(top level)'
                break
            except ValueError:
                continue
        groups.setdefault(rel_parent, []).append(name)

    print(f"Available bitmasks ({len(available)} total):")
    for group in sorted(groups):
        print(f"\n  {group}/")
        for name in groups[group]:
            print(f"    {name}")
    print("\nSee bitmasks/README.md for when to use which.")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--bitmask', help='Name (e.g. bitfile_gx_d012) or path to bitmask file')
    parser.add_argument('--directory', type=Path, help='Root directory')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing bitmask file in each Analysis/')
    parser.add_argument('--list', action='store_true', help='List shipped bitmasks and exit')
    parser.add_argument('--no-interactive', action='store_true')
    args = parser.parse_args()

    if args.list:
        print_bitmask_list()
        raise SystemExit(0)

    overwrite = True if args.overwrite else None
    copy_bitmask_to_results(
        args.directory,
        args.bitmask,
        overwrite=overwrite,
        interactive=not args.no_interactive,
    )
