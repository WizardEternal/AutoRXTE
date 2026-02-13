"""Main CLI entry point for AutoRXTE."""
import argparse
import sys
from pathlib import Path

def main():
    """Main entry point for autorxte command."""
    parser = argparse.ArgumentParser(
        description='AutoRXTE - Fast RXTE data analysis automation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Core workflow
  autorxte download --source "Cyg X-1" --top-n 5 --directory ./data
  autorxte prepare --directory ./data
  autorxte extract --directory ./data --token e
  autorxte lightcurves --directory ./data --type std2
  autorxte spectra --directory ./data
  autorxte pds --directory ./data
  
  # Advanced features
  autorxte color-extract --directory ./data
  autorxte color-plot --directory ./data
  autorxte xspec --directory ./data --model diskbb_pexrav
  autorxte xenon --directory ./data
  autorxte plot --directory ./data
  
  # Use custom config
  autorxte --config my_config.yaml extract --directory ./data

For detailed help: autorxte <command> --help
"""
    )
    
    parser.add_argument('--version', action='version', version='AutoRXTE v1.1.0')
    parser.add_argument('--config', type=Path, help='Custom config file')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Core modules
    download = subparsers.add_parser('download', help='Download RXTE data')
    download.add_argument('--source', help='Source name')
    download.add_argument('--top-n', type=int, help='Number of observations')
    download.add_argument('--directory', type=Path, help='Output directory')
    download.add_argument('--region', help='AWS region (us-east-1, ap-south-1, etc.)')
    download.add_argument('--auto-detect-region', action='store_true', 
                         help='Auto-detect fastest region')
    
    prepare = subparsers.add_parser('prepare', help='Run pcaprepobsid')
    prepare.add_argument('--directory', type=Path, help='Data directory')
    
    extract = subparsers.add_parser('extract', help='Extract events')
    extract.add_argument('--directory', type=Path, help='Data directory')
    extract.add_argument('--token', choices=['e', 'xenon'], help='Token type')
    
    lightcurves = subparsers.add_parser('lightcurves', help='Generate lightcurves')
    lightcurves.add_argument('--directory', type=Path, help='Data directory')
    lightcurves.add_argument('--type', choices=['std1', 'std2'], help='LC type')
    
    spectra = subparsers.add_parser('spectra', help='Extract spectra')
    spectra.add_argument('--directory', type=Path, help='Data directory')
    
    pds = subparsers.add_parser('pds', help='Generate PDS')
    pds.add_argument('--directory', type=Path, help='Data directory')
    
    # Advanced modules
    color_extract = subparsers.add_parser('color-extract', help='Extract color ranges')
    color_extract.add_argument('--directory', type=Path, help='Data directory')
    
    color_plot = subparsers.add_parser('color-plot', help='Plot CCDs')
    color_plot.add_argument('--directory', type=Path, help='Data directory')
    
    xspec = subparsers.add_parser('xspec', help='XSPEC fitting')
    xspec.add_argument('--directory', type=Path, help='Data directory')
    xspec.add_argument('--model', help='Model name')
    
    xenon = subparsers.add_parser('xenon', help='Xenon workflow')
    xenon.add_argument('--directory', type=Path, help='Data directory')
    
    plot = subparsers.add_parser('plot', help='Plot lightcurves')
    plot.add_argument('--directory', type=Path, help='Data directory')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    # Load config if specified
    if args.config:
        from autorxte.config import load_config
        load_config(args.config)
    
    # Execute commands
    from autorxte.core import (
        search_and_download, prepare_all_obsids, extract_all_events,
        generate_lightcurves, extract_spectra, compute_pds
    )
    
    if args.command == 'download':
        # Handle auto-detect region
        region = None
        if args.auto_detect_region:
            from autorxte.core import find_fastest_region, save_preferred_region
            region = find_fastest_region('nasa-heasarc')
            save_preferred_region(region)
            print(f"Using region: {region}")
        elif hasattr(args, 'region') and args.region:
            region = args.region
        
        search_and_download(
            source=args.source,
            top_n=args.top_n,
            output_dir=args.directory,
            region=region,
            interactive=args.source is None
        )
    elif args.command == 'prepare':
        prepare_all_obsids(args.directory, interactive=args.directory is None)
    elif args.command == 'extract':
        extract_all_events(args.directory, token=args.token, 
                          interactive=args.directory is None)
    elif args.command == 'lightcurves':
        generate_lightcurves(args.directory, args.type, 
                            interactive=args.directory is None)
    elif args.command == 'spectra':
        extract_spectra(args.directory, interactive=args.directory is None)
    elif args.command == 'pds':
        compute_pds(args.directory, interactive=args.directory is None)
    elif args.command == 'color-extract':
        from autorxte.advanced import extract_color_ranges
        extract_color_ranges(args.directory, interactive=args.directory is None)
    elif args.command == 'color-plot':
        from autorxte.advanced import plot_color_diagrams
        plot_color_diagrams(args.directory, interactive=args.directory is None)
    elif args.command == 'xspec':
        from autorxte.advanced import fit_all_spectra
        fit_all_spectra(args.directory, args.model, 
                       interactive=args.directory is None)
    elif args.command == 'xenon':
        from autorxte.advanced import xenon_complete_workflow
        xenon_complete_workflow(args.directory, interactive=args.directory is None)
    elif args.command == 'plot':
        from autorxte.advanced import plot_all_lightcurves
        plot_all_lightcurves(args.directory, interactive=args.directory is None)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
