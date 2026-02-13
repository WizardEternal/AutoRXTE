"""04 - Bitmask Distribution."""
import logging
import shutil
from pathlib import Path
from typing import Optional
from autorxte.utils.interactive import get_path, get_yes_no

logger = logging.getLogger(__name__)

def copy_bitmask_to_results(root_dir: Optional[Path] = None, bitmask_path: Optional[Path] = None,
                            overwrite: Optional[bool] = None, interactive: bool = True):
    """Copy bitmask file to all Analysis directories."""
    if interactive:
        bitmask_path = get_path("Bitmask file", arg_value=bitmask_path)
        root_dir = get_path("Root directory", Path('.'), root_dir)
        overwrite = get_yes_no("Overwrite existing?", False, overwrite)
    
    if not bitmask_path.exists():
        raise FileNotFoundError(f"{bitmask_path}")
    
    for entry in root_dir.iterdir():
        if entry.is_dir() and entry.name.endswith("results"):
            analysis = entry / "Analysis"
            if analysis.is_dir():
                dest = analysis / bitmask_path.name
                if not dest.exists() or overwrite:
                    shutil.copy2(bitmask_path, dest)
                    logger.info(f"✓ {entry.name}")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--bitmask', type=Path)
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    copy_bitmask_to_results(args.directory, args.bitmask, interactive=args.bitmask is None)
