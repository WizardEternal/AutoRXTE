"""05 - Time Filtering and GTI Creation."""
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input

logger = logging.getLogger(__name__)

DEFAULT_FILTER = "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) && .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)"

def create_gti_filters(root_dir: Optional[Path] = None, filter_expression: Optional[str] = None,
                      interactive: bool = True):
    """Create GTI files using maketime."""
    require_heasoft_tool('maketime')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        if filter_expression is None:
            print(f"Default: {DEFAULT_FILTER}")
            filter_expression = get_input("Filter expression", DEFAULT_FILTER, filter_expression)
    else:
        root_dir = root_dir or Path('.')
        filter_expression = filter_expression or DEFAULT_FILTER
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis_dir = results_dir / 'Analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for FP_xtefilt.lis
        lis_file = results_dir / 'FP_xtefilt.lis'
        if not lis_file.exists():
            logger.warning(f"No FP_xtefilt.lis in {results_dir.name}")
            continue
        
        # Copy to temporary .txt file and read first line
        txt_file = results_dir / 'FP_xtefilt.txt'
        shutil.copy2(lis_file, txt_file)
        first_line = txt_file.open('r').readline().rstrip('\n')
        
        # Build maketime script
        gti_file = analysis_dir / 'good.gti'
        script_content = f"""{first_line}
{gti_file}
{filter_expression}
no
TIME
"""
        
        script_file = results_dir / 'maketime_script.txt'
        script_file.write_text(script_content)
        
        try:
            with script_file.open('r') as sf:
                subprocess.run(['maketime'], stdin=sf, check=True, capture_output=True)
            logger.info(f"✓ {results_dir.name}")
            count += 1
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {results_dir.name}: {e.stderr.decode()}")
        finally:
            # Cleanup temporary files
            for temp in [script_file, txt_file]:
                try:
                    temp.unlink()
                except Exception:
                    pass
    
    logger.info(f"Complete: {count} GTI files created")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--filter', help='Filter expression')
    args = parser.parse_args()
    create_gti_filters(args.directory, args.filter, interactive=args.directory is None)
