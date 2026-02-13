"""03 - FITS File Organization."""
import logging
import shutil
from pathlib import Path
from typing import Optional
from autorxte.utils.interactive import get_path, get_yes_no

logger = logging.getLogger(__name__)

def organize_fits_files(root_dir: Optional[Path] = None, move_mode: Optional[bool] = None,
                       interactive: bool = True):
    """Move fits_files.god from parent directories to Analysis directories."""
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        move_mode = get_yes_no("Move files (vs copy)?", True, move_mode)
    else:
        root_dir = root_dir or Path('.')
        move_mode = move_mode if move_mode is not None else True
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        # Extract parent directory name
        parent_name = results_dir.name[:-len('-results')]
        parent_dir = root_dir / parent_name
        
        analysis_dir = results_dir / 'Analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        if parent_dir.is_dir():
            src = parent_dir / 'fits_files.god'
            if src.exists():
                dst = analysis_dir / src.name
                
                if move_mode:
                    shutil.move(str(src), str(dst))
                    logger.info(f"✓ Moved {src.name} to {results_dir.name}/Analysis")
                else:
                    shutil.copy2(str(src), str(dst))
                    logger.info(f"✓ Copied {src.name} to {results_dir.name}/Analysis")
                count += 1
            else:
                logger.warning(f"No fits_files.god in {parent_dir}")
        else:
            logger.warning(f"Parent directory {parent_dir} not found")
    
    logger.info(f"Complete: {count} files organized")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--copy', action='store_true', help='Copy instead of move')
    args = parser.parse_args()
    organize_fits_files(args.directory, move_mode=not args.copy, 
                       interactive=args.directory is None)
