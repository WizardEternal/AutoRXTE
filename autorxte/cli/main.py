"""Main CLI entry point for AutoRXTE."""
import argparse
import logging
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
  autorxte download --source "GRS 1915+105" --obsids 60405-01-02-00 --directory ./data
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
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable DEBUG logging')
    parser.add_argument('-q', '--quiet', action='store_true', help='Show warnings and errors only')

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Core modules
    download = subparsers.add_parser('download', help='Download RXTE data')
    download.add_argument('--source', help='Source name or "RA DEC" in degrees')
    download.add_argument('--catalog', help='HEASARC catalog (default: xtemaster)')
    download.add_argument('--radius', type=float, help='Search radius in arcmin (default: 5.0)')
    download.add_argument('--top-n', type=int, help='Download top N observations by exposure')
    download.add_argument('--bottom-n', type=int, help='Download bottom N observations by exposure')
    download.add_argument('--obsids', help='Comma-separated ObsIDs to download')
    download.add_argument('--min-exposure', type=float, help='Minimum exposure in seconds')
    download.add_argument('--start-date', help='Start date YYYY-MM-DD')
    download.add_argument('--end-date', help='End date YYYY-MM-DD')
    download.add_argument('--directory', type=Path, help='Output directory')
    download.add_argument('--bucket', help='S3 bucket (default: nasa-heasarc)')
    download.add_argument('--region', help='AWS region (us-east-1, ap-south-1, etc.)')
    download.add_argument('--auto-detect-region', action='store_true',
                         help='Auto-detect fastest region')
    download.add_argument('--overwrite', action='store_true', help='Re-download existing files')
    download.add_argument('--no-interactive', action='store_true',
                         help='Disable interactive prompts (requires --source)')
    
    prepare = subparsers.add_parser('prepare', help='Run pcaprepobsid')
    prepare.add_argument('--directory', type=Path, help='Data directory')
    prepare.add_argument('--workers', type=int, help='Parallel pcaprepobsid workers')
    prepare.add_argument('--no-interactive', action='store_true',
                         help='Disable interactive prompts')
    prepare.add_argument('--no-skip-existing', action='store_true',
                         help='Re-prepare even when results dir is already complete')

    organize = subparsers.add_parser('organize',
                                     help='Scan pca/ and write fits_files.god into Analysis/')
    organize.add_argument('--directory', type=Path, help='Data directory')
    organize.add_argument('--workers', type=int, help='Parallel obsid workers')
    organize.add_argument('--copy', action='store_true',
                          help='Copy .god files instead of moving them')
    organize.add_argument('--no-skip-existing', action='store_true',
                          help='Re-organize even when Analysis/ already has the .god')
    organize.add_argument('--no-interactive', action='store_true')

    filter_p = subparsers.add_parser('filter',
                                     help='Run maketime to build Analysis/good.gti')
    filter_p.add_argument('--directory', type=Path, help='Data directory')
    filter_p.add_argument('--filter', dest='filter_expr',
                          help='maketime selection expression (default: standard ELV/OFFSET/PCU cuts)')
    filter_p.add_argument('--workers', type=int, help='Parallel maketime workers')
    filter_p.add_argument('--no-skip-existing', action='store_true',
                          help='Re-run maketime even when good.gti already exists')
    filter_p.add_argument('--no-interactive', action='store_true')

    bitmask = subparsers.add_parser('bitmask',
                                    help='Copy a bitmask file into every Analysis/')
    bitmask.add_argument('--directory', type=Path, help='Data directory')
    bitmask.add_argument('--bitmask',
                         help='Bitmask name (e.g. bitfile_gx_d012) or path. '
                              'Default: bitmask_event (= bitfile_M).')
    bitmask.add_argument('--list', action='store_true',
                         help='List shipped bitmasks and exit')
    bitmask.add_argument('--overwrite', action='store_true',
                         help='Overwrite an existing bitmask file in Analysis/')
    bitmask.add_argument('--no-interactive', action='store_true')
    
    extract = subparsers.add_parser('extract', help='Extract events with seextrct')
    extract.add_argument('--directory', type=Path, help='Data directory')
    extract.add_argument('--token', choices=['e', 'xenon'], help='Token type (default: e)')
    extract.add_argument('--prefix', help='Base event filename (default: event)')
    extract.add_argument('--bitmask', help='Bitmask filename in Analysis/ (default: bitmask_event)')
    extract.add_argument('--split-gti', action='store_true',
                         help='Split multi-row GTI into per-row files and extract each')
    extract.add_argument('--workers', type=int, help='Parallel seextrct workers')
    extract.add_argument('--no-skip-existing', action='store_true',
                         help='Re-extract even when <prefix>.lc already exists')
    extract.add_argument('--no-interactive', action='store_true')
    
    lightcurves = subparsers.add_parser('lightcurves',
                                         help='Generate STD1/STD2 lightcurves with pcaextlc1/2')
    lightcurves.add_argument('--directory', type=Path, help='Data directory')
    lightcurves.add_argument('--type', choices=['std1', 'std2'], help='LC type (default std2)')
    lightcurves.add_argument('--bin-size', help='STD1 bin size in seconds (default 0.125)')
    lightcurves.add_argument('--layerlist', help='STD2 layer selection 1/2/3/ALL (default ALL)')
    lightcurves.add_argument('--time-bins', help='STD2 bin size in seconds, multiple of 16 (default 16)')
    lightcurves.add_argument('--chmin', help='STD2 min channel 0-255 (default 0)')
    lightcurves.add_argument('--chmax', help='STD2 max channel 0-255 (default 255)')
    lightcurves.add_argument('--lc-name', help='Output LC filename (default std1.lc or light.lc)')
    lightcurves.add_argument('--pculist', help='PCU list comma-separated (default 2)')
    lightcurves.add_argument('--workers', type=int)
    lightcurves.add_argument('--no-skip-existing', action='store_true')
    lightcurves.add_argument('--no-interactive', action='store_true')
    
    spectra = subparsers.add_parser('spectra', help='Extract src/bkg/rsp spectra with pcaextspect2')
    spectra.add_argument('--directory', type=Path, help='Data directory')
    spectra.add_argument('--layerlist', help='Layer selection 1/2/3/ALL (default ALL)')
    spectra.add_argument('--pculist', help='PCU list comma-separated (default 2)')
    spectra.add_argument('--src-name', help='Source spectrum filename (default src.pha)')
    spectra.add_argument('--bkg-name', help='Background spectrum filename (default bkg.pha)')
    spectra.add_argument('--rsp-name', help='Response filename (default rsp.pha)')
    spectra.add_argument('--workers', type=int)
    spectra.add_argument('--no-skip-existing', action='store_true')
    spectra.add_argument('--no-interactive', action='store_true')
    
    pds = subparsers.add_parser('pds', help='Generate PDS via powspec+fplot+flx2xsp chain')
    pds.add_argument('--directory', type=Path, help='Data directory')
    pds.add_argument('--lc-file', help='Lightcurve in Analysis/ (default event.lc)')
    pds.add_argument('--binning', help='powspec binning (default -1)')
    pds.add_argument('--rebin', help='powspec rebin factor (default -1.03)')
    pds.add_argument('--plot-device', help='PGPLOT device (default /null for headless)')
    pds.add_argument('--workers', type=int)
    pds.add_argument('--no-skip-existing', action='store_true')
    pds.add_argument('--no-interactive', action='store_true')
    
    # Advanced modules
    color_extract = subparsers.add_parser('color-extract',
                                           help='Extract per-band lightcurves with seextrct')
    color_extract.add_argument('--directory', type=Path, help='Data directory')
    color_extract.add_argument('--token', choices=['e', 'xenon'])
    color_extract.add_argument('--bitmask', help='Bitmask filename in Analysis/ (default bitmask_event)')
    color_extract.add_argument('--ranges', nargs='+',
                                help='Channel ranges, e.g. 0-13 14-35 36-255')
    color_extract.add_argument('--names', nargs='+',
                                help='Output names per range, e.g. soft medium hard')
    color_extract.add_argument('--bin-size', help='Time bin in seconds (default 0.04)')
    color_extract.add_argument('--workers', type=int)
    color_extract.add_argument('--no-skip-existing', action='store_true')
    color_extract.add_argument('--no-interactive', action='store_true')

    color_plot = subparsers.add_parser('color-plot',
                                        help='Plot color-color diagrams via lcurve')
    color_plot.add_argument('--directory', type=Path, help='Data directory')
    color_plot.add_argument('--colors', nargs='+', help='Color names matching extract step')
    color_plot.add_argument('--bin-size', help='Bin size (-1 = auto)')
    color_plot.add_argument('--plot-device', help='PGPLOT device (default /null)')
    color_plot.add_argument('--workers', type=int)
    color_plot.add_argument('--no-interactive', action='store_true')
    
    xspec = subparsers.add_parser('xspec',
                                   help='Apply a template .xcm to every Analysis/ and aggregate')
    xspec.add_argument('--xcm', dest='template', type=Path,
                       help='Template .xcm produced by your interactive XSPEC fit')
    xspec.add_argument('--directory', type=Path,
                       help='Root directory containing <obsid>-results/')
    xspec.add_argument('--name', help='Output basename (default: template stem)')
    xspec.add_argument('--energy',
                       help='Ignore range, e.g. 3-30 (keV). Adds `ignore **-Emin Emax-**`.')
    xspec.add_argument('--fit-iter', type=int, default=100000,
                       help='Iterations for `fit` (default 100000)')
    xspec.add_argument('--error', dest='error_spec',
                       help='Param indices for `error N`, e.g. "1,3-5,7"')
    xspec.add_argument('--flux',
                       help='Flux band like "3-30" (keV). Adds `flux Emin Emax`.')
    xspec.add_argument('--gain', dest='gain_groups_spec',
                       help='Datagroup indices for `gain fit N`, e.g. "1,2"')
    xspec.add_argument('--freeze', dest='freeze_spec',
                       help='Param indices to `freeze` before fit')
    xspec.add_argument('--thaw', dest='thaw_spec',
                       help='Param indices to `thaw` before fit')
    xspec.add_argument('--no-rewrite', action='store_true',
                       help='Use the template verbatim (do not rewrite data/response/backgrnd paths)')
    xspec.add_argument('--workers', type=int, help='Parallel xspec workers (default 1)')
    xspec.add_argument('--no-skip-existing', action='store_true')
    xspec.add_argument('--timeout', type=int, default=1800)
    xspec.add_argument('--output', dest='output_csv', type=Path,
                       help='Output CSV (default xspec_batch.csv in cwd)')
    xspec.add_argument('--no-interactive', action='store_true')
    
    xenon = subparsers.add_parser('xenon', help='Xenon workflow')
    xenon.add_argument('--directory', type=Path, help='Data directory')
    
    plot = subparsers.add_parser('plot', help='Plot lightcurves with lcurve')
    plot.add_argument('--directory', type=Path, help='Data directory')
    plot.add_argument('--pattern', help='Glob pattern in Analysis/ (default *.lc)')
    plot.add_argument('--bin-size', help='Bin size in seconds (default 1)')
    plot.add_argument('--plot-device', help='PGPLOT device (default /null)')
    plot.add_argument('--workers', type=int)
    plot.add_argument('--no-interactive', action='store_true')
    
    args = parser.parse_args()

    # Configure logging early so module-level logger.info calls are visible.
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

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
        # Region: explicit --region wins; --auto-detect-region runs the speed test
        # and persists the result; otherwise leave None for the function to handle
        # (interactive prompt or saved preference).
        region = args.region
        if args.auto_detect_region:
            from autorxte.core import find_fastest_region, save_preferred_region
            region = find_fastest_region(args.bucket or 'nasa-heasarc')
            save_preferred_region(region)
            print(f"Using region: {region}")

        obsids = None
        if args.obsids:
            obsids = [o.strip() for o in args.obsids.split(',') if o.strip()]

        # --no-interactive forces non-interactive; otherwise default to interactive
        # only when no source was given (matches prior behavior).
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.source is None

        # Pass overwrite as None if --overwrite was not given, so the interactive
        # prompt fires; only force a value when the user explicitly set the flag.
        overwrite = True if args.overwrite else None
        search_and_download(
            source=args.source,
            catalog=args.catalog,
            radius=args.radius,
            output_dir=args.directory,
            min_exposure=args.min_exposure,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            bottom_n=args.bottom_n,
            obsids=obsids,
            overwrite=overwrite,
            bucket=args.bucket,
            region=region,
            interactive=interactive,
        )
    elif args.command == 'prepare':
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        # Only force skip_existing=False when the user explicitly passed
        # --no-skip-existing; otherwise leave None so the interactive prompt fires.
        skip_existing = False if args.no_skip_existing else None
        prepare_all_obsids(
            args.directory,
            workers=args.workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )
    elif args.command == 'organize':
        from autorxte.core import organize_fits_files
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        # Same pattern: pass None unless the flag was explicitly given.
        move_mode = False if args.copy else None
        skip_existing = False if args.no_skip_existing else None
        organize_fits_files(
            args.directory,
            move_mode=move_mode,
            skip_existing=skip_existing,
            workers=args.workers,
            interactive=interactive,
        )
    elif args.command == 'filter':
        from autorxte.core import create_gti_filters
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        skip_existing = False if args.no_skip_existing else None
        create_gti_filters(
            args.directory,
            filter_expression=args.filter_expr,
            workers=args.workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )
    elif args.command == 'bitmask':
        from autorxte.core import copy_bitmask_to_results, print_bitmask_list
        if args.list:
            print_bitmask_list()
            return 0
        if args.no_interactive:
            interactive = False
        else:
            interactive = (args.directory is None) and (args.bitmask is None)
        overwrite = True if args.overwrite else None
        copy_bitmask_to_results(
            root_dir=args.directory,
            bitmask_path=args.bitmask,
            overwrite=overwrite,
            interactive=interactive,
        )
    elif args.command == 'extract':
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        skip_existing = False if args.no_skip_existing else None
        split_gti_flag = True if args.split_gti else None
        extract_all_events(
            args.directory,
            prefix=args.prefix,
            token=args.token,
            bitmask=args.bitmask,
            split_gti_flag=split_gti_flag,
            workers=args.workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )
    elif args.command == 'lightcurves':
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        skip_existing = False if args.no_skip_existing else None
        generate_lightcurves(
            args.directory,
            lc_type=args.type,
            workers=args.workers,
            skip_existing=skip_existing,
            interactive=interactive,
            bin_size=args.bin_size,
            layerlist=args.layerlist,
            time_bins=args.time_bins,
            chmin=args.chmin,
            chmax=args.chmax,
            lc_name=args.lc_name,
            pculist=args.pculist,
        )
    elif args.command == 'spectra':
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        skip_existing = False if args.no_skip_existing else None
        extract_spectra(
            args.directory,
            layerlist=args.layerlist,
            pculist=args.pculist,
            src_name=args.src_name,
            bkg_name=args.bkg_name,
            rsp_name=args.rsp_name,
            workers=args.workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )
    elif args.command == 'pds':
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        skip_existing = False if args.no_skip_existing else None
        compute_pds(
            args.directory,
            lc_file=args.lc_file,
            binning=args.binning,
            rebin=args.rebin,
            plot_device=args.plot_device,
            workers=args.workers,
            skip_existing=skip_existing,
            interactive=interactive,
        )
    elif args.command == 'color-extract':
        from autorxte.advanced import extract_color_ranges
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        skip_existing = False if args.no_skip_existing else None
        extract_color_ranges(
            args.directory,
            token=args.token, bitmask=args.bitmask,
            ranges=args.ranges, names=args.names,
            bin_size=args.bin_size, workers=args.workers,
            skip_existing=skip_existing, interactive=interactive,
        )
    elif args.command == 'color-plot':
        from autorxte.advanced import plot_color_diagrams
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        plot_color_diagrams(
            args.directory,
            color_names=args.colors, bin_size=args.bin_size,
            plot_device=args.plot_device, workers=args.workers,
            interactive=interactive,
        )
    elif args.command == 'xspec':
        from autorxte.advanced.xspec_fit_02 import apply_xcm_template

        def _parse_range(s):
            if not s:
                return None
            a, b = s.split('-', 1)
            return (float(a), float(b))

        if args.no_interactive:
            interactive = False
        else:
            interactive = args.template is None
        skip_existing = False if args.no_skip_existing else None
        # Only force a value when the user explicitly passed the flag; otherwise
        # leave None so the interactive prompts can fire.
        rewrite_paths = False if args.no_rewrite else None
        apply_xcm_template(
            template=args.template,
            root_dir=args.directory,
            name=args.name,
            energy_range=_parse_range(args.energy),
            fit_iter=args.fit_iter,
            error_spec=args.error_spec,
            flux_range=_parse_range(args.flux),
            gain_groups_spec=args.gain_groups_spec,
            freeze_spec=args.freeze_spec,
            thaw_spec=args.thaw_spec,
            rewrite_paths=rewrite_paths,
            workers=args.workers,
            skip_existing=skip_existing,
            timeout=args.timeout,
            output_csv=args.output_csv,
            interactive=interactive,
        )
    elif args.command == 'xenon':
        from autorxte.advanced import xenon_complete_workflow
        xenon_complete_workflow(args.directory, interactive=args.directory is None)
    elif args.command == 'plot':
        from autorxte.advanced import plot_all_lightcurves
        if args.no_interactive:
            interactive = False
        else:
            interactive = args.directory is None
        plot_all_lightcurves(
            args.directory,
            lc_pattern=args.pattern,
            bin_size=args.bin_size,
            plot_device=args.plot_device,
            workers=args.workers,
            interactive=interactive,
        )
    
    return 0

def _run():
    """Wrap main() with user-friendly error handling."""
    # Detect --verbose early so unexpected errors still get a traceback when
    # the user asked for one. Argparse hasn't run yet, so peek at sys.argv.
    verbose = ('-v' in sys.argv) or ('--verbose' in sys.argv)
    try:
        return main()
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        return 130
    except SystemExit:
        raise
    except Exception as e:
        # Print a clean one-line error. Full traceback only when -v/--verbose.
        if verbose:
            raise
        sys.stderr.write(f"error: {type(e).__name__}: {e}\n")
        return 2

if __name__ == '__main__':
    sys.exit(_run())
