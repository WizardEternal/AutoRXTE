"""Complete Xenon Mode Workflow.

Complete preprocessing for Good Xenon mode data, including:
- Creating xenon_files.god from FITS files
- Running make_se to generate Xenon event files
- Listing generated Xenon event files

Based on: xenongod.py, make_se.txt, xenon_move.txt, xenonlist.txt
"""
import logging
import subprocess
import shutil
import gzip
from pathlib import Path
from typing import Optional
import astropy.io.fits as fits
from autorxte.utils import require_heasoft_tool
from autorxte.utils.interactive import get_path, get_input, get_yes_no

logger = logging.getLogger(__name__)

def read_fits_header_xenon(file_path: Path, extension: str = 'XTE_SP'):
    """Read DATAMODE and DDESC from Xenon FITS file."""
    try:
        if file_path.suffix == '.gz':
            with gzip.open(file_path, 'rb') as gz:
                with fits.open(gz) as hdul:
                    if extension in hdul:
                        hdr = hdul[extension].header
                        return hdr.get('DATAMODE', 'N/A'), hdr.get('DDESC', 'N/A')
        else:
            with fits.open(file_path) as hdul:
                if extension in hdul:
                    hdr = hdul[extension].header
                    return hdr.get('DATAMODE', 'N/A'), hdr.get('DDESC', 'N/A')
    except Exception as e:
        logger.warning(f"Error reading {file_path.name}: {e}")
    return 'N/A', 'N/A'

def create_xenon_god_files(root_dir: Optional[Path] = None, 
                          extension: Optional[str] = None,
                          interactive: bool = True):
    """Create xenon_files.god for all numbered directories."""
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        extension = get_input("FITS extension", "XTE_SP", extension)
    else:
        root_dir = root_dir or Path('.')
        extension = extension or "XTE_SP"
    
    count = 0
    for entry in root_dir.iterdir():
        if not entry.is_dir() or not any(c.isdigit() for c in entry.name):
            continue
        
        pca = entry / 'pca'
        if not pca.is_dir():
            logger.warning(f"No pca/ in {entry.name}")
            continue
        
        # Find FITS files
        xenon_files = []
        for f in pca.rglob('*'):
            if f.is_file() and ('.' not in f.name or f.name.endswith('.gz')) and f.name.startswith('F'):
                dm, dd = read_fits_header_xenon(f, extension)
                if dm != 'N/A':
                    # Remove .gz extension for the list
                    file_path = str(f).rstrip('.gz')
                    xenon_files.append(file_path)
        
        if xenon_files:
            god_file = entry / 'xenon_files.god'
            with open(god_file, 'w') as gf:
                for fp in xenon_files:
                    gf.write(fp + "\n")
            logger.info(f"✓ Created {god_file} ({len(xenon_files)} files)")
            count += 1
        else:
            logger.warning(f"No Xenon FITS files in {entry.name}/pca")
    
    logger.info(f"Complete: {count} xenon_files.god created")

def move_xenon_god_files(root_dir: Optional[Path] = None,
                        interactive: bool = True):
    """Move xenon_files.god to Analysis directories."""
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
    else:
        root_dir = root_dir or Path('.')
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        parent_name = results_dir.name[:-len('-results')]
        parent_dir = root_dir / parent_name
        analysis_dir = results_dir / 'Analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        if parent_dir.is_dir():
            src = parent_dir / 'xenon_files.god'
            if src.exists():
                dst = analysis_dir / 'xenon_files.god'
                shutil.move(str(src), str(dst))
                logger.info(f"✓ Moved to {results_dir.name}/Analysis")
                count += 1
            else:
                logger.warning(f"No xenon_files.god in {parent_dir}")
    
    logger.info(f"Complete: {count} files moved")

def run_make_se(root_dir: Optional[Path] = None,
               output_root: Optional[str] = None,
               interactive: bool = True):
    """Run make_se to generate Xenon event files.
    
    Note: This creates separate processes for each observation.
    In interactive mode, this will open new terminals (Linux only).
    """
    require_heasoft_tool('make_se')
    
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        output_root = get_input("Output root name", "event", output_root)
        use_terminals = get_yes_no("Open new terminals? (Linux only)", False)
    else:
        root_dir = root_dir or Path('.')
        output_root = output_root or "event"
        use_terminals = False
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis_dir = results_dir / 'Analysis'
        god_file = analysis_dir / 'xenon_files.god'
        
        if not god_file.exists():
            logger.warning(f"No xenon_files.god in {results_dir.name}/Analysis")
            continue
        
        script = analysis_dir / 'make_se_script.txt'
        lines = [
            "xenon_files.god",
            output_root
        ]
        script.write_text("\n".join(lines) + "\n")
        
        try:
            if use_terminals:
                # Open in new terminal (Linux only)
                bash_cmd = f"cd '{analysis_dir}' && make_se < make_se_script.txt; exec bash"
                subprocess.Popen(['gnome-terminal', '--', 'bash', '-c', bash_cmd])
                logger.info(f"✓ Launched make_se in terminal for {results_dir.name}")
            else:
                # Run in current process
                with script.open('r') as sf:
                    result = subprocess.run(['make_se'], stdin=sf, cwd=analysis_dir,
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        logger.info(f"✓ {results_dir.name}")
                    else:
                        logger.error(f"✗ {results_dir.name}: {result.stderr}")
            count += 1
        finally:
            script.unlink(missing_ok=True)
    
    if use_terminals:
        logger.info(f"Launched {count} make_se processes in terminals")
    else:
        logger.info(f"Complete: {count} observations processed")

def create_xenon_event_lists(root_dir: Optional[Path] = None,
                            pattern: Optional[str] = None,
                            interactive: bool = True):
    """Create xenon_event_files.txt listing generated Xenon event files."""
    if interactive:
        root_dir = get_path("Root directory", Path('.'), root_dir)
        pattern = get_input("Event file pattern", "xenon_event_gx*", pattern)
    else:
        root_dir = root_dir or Path('.')
        pattern = pattern or "xenon_event_gx*"
    
    count = 0
    for results_dir in root_dir.glob('*-results'):
        if not results_dir.is_dir():
            continue
        
        analysis_dir = results_dir / 'Analysis'
        if not analysis_dir.is_dir():
            continue
        
        event_files = list(analysis_dir.glob(pattern))
        
        if event_files:
            list_file = analysis_dir / 'xenon_event_files.txt'
            with open(list_file, 'w') as f:
                for ef in event_files:
                    f.write(str(ef) + "\n")
            logger.info(f"✓ {results_dir.name}: {len(event_files)} files")
            count += 1
        else:
            logger.warning(f"No {pattern} files in {results_dir.name}/Analysis")
    
    logger.info(f"Complete: {count} lists created")

def xenon_complete_workflow(root_dir: Optional[Path] = None,
                           run_make_se_flag: Optional[bool] = None,
                           interactive: bool = True):
    """Run complete Xenon mode workflow."""
    logger.info("Starting complete Xenon mode workflow")
    
    # Step 1: Create xenon_files.god
    logger.info("Step 1: Creating xenon_files.god")
    create_xenon_god_files(root_dir, interactive=interactive)
    
    # Step 2: Move to Analysis directories
    logger.info("Step 2: Moving xenon_files.god to Analysis")
    move_xenon_god_files(root_dir, interactive=interactive)
    
    # Step 3: Run make_se (optional)
    if interactive:
        run_make_se_flag = get_yes_no("Run make_se now?", True, run_make_se_flag)
    
    if run_make_se_flag if run_make_se_flag is not None else True:
        logger.info("Step 3: Running make_se")
        run_make_se(root_dir, interactive=interactive)
        
        # Step 4: Create event file lists
        logger.info("Step 4: Creating xenon_event_files.txt")
        create_xenon_event_lists(root_dir, interactive=interactive)
    else:
        logger.info("Skipping make_se - run manually if needed")
    
    logger.info("Xenon workflow complete!")

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='Xenon mode workflow')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Create god files
    god_parser = subparsers.add_parser('create-god', help='Create xenon_files.god')
    god_parser.add_argument('--directory', type=Path)
    god_parser.add_argument('--extension', default='XTE_SP')
    
    # Move god files
    move_parser = subparsers.add_parser('move-god', help='Move xenon_files.god')
    move_parser.add_argument('--directory', type=Path)
    
    # Run make_se
    make_se_parser = subparsers.add_parser('make-se', help='Run make_se')
    make_se_parser.add_argument('--directory', type=Path)
    make_se_parser.add_argument('--output-root', default='event')
    
    # Create event lists
    list_parser = subparsers.add_parser('list-events', help='Create event file lists')
    list_parser.add_argument('--directory', type=Path)
    list_parser.add_argument('--pattern', default='xenon_event_gx*')
    
    # Complete workflow
    workflow_parser = subparsers.add_parser('workflow', help='Run complete workflow')
    workflow_parser.add_argument('--directory', type=Path)
    workflow_parser.add_argument('--skip-make-se', action='store_true')
    
    args = parser.parse_args()
    
    if args.command == 'create-god':
        create_xenon_god_files(args.directory, args.extension, 
                              interactive=args.directory is None)
    elif args.command == 'move-god':
        move_xenon_god_files(args.directory, interactive=args.directory is None)
    elif args.command == 'make-se':
        run_make_se(args.directory, args.output_root, 
                   interactive=args.directory is None)
    elif args.command == 'list-events':
        create_xenon_event_lists(args.directory, args.pattern,
                                interactive=args.directory is None)
    elif args.command == 'workflow':
        xenon_complete_workflow(args.directory, not args.skip_make_se,
                               interactive=args.directory is None)
    else:
        parser.print_help()
