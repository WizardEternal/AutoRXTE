"""
01 - Data Search and Download

Download RXTE data from NASA HEASARC S3 archive.
Supports both interactive mode and function arguments.
"""

import re
import json
import time
import logging
import threading
import multiprocessing
from pathlib import Path
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import numpy as np
from botocore import UNSIGNED
from botocore.client import Config
from astroquery.heasarc import Heasarc
from astropy.time import Time
from datetime import datetime
from astropy.coordinates import SkyCoord
from astropy import units as u

from autorxte.utils.interactive import get_input, get_yes_no, get_path, get_float, get_int, get_choice

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = 'nasa-heasarc'
DEFAULT_REGION = 'us-east-1'
DEFAULT_CATALOG = 'xtemaster'

# AWS regions to test (major global endpoints)
POSSIBLE_REGIONS = [
    # US
    'us-east-1',      # US East (N. Virginia) - Default
    'us-east-2',      # US East (Ohio)
    'us-west-1',      # US West (N. California)
    'us-west-2',      # US West (Oregon)
    # Europe
    'eu-west-1',      # Europe (Ireland)
    'eu-west-2',      # Europe (London)
    'eu-west-3',      # Europe (Paris)
    'eu-central-1',   # Europe (Frankfurt)
    'eu-north-1',     # Europe (Stockholm)
    'eu-south-1',     # Europe (Milan)
    # Asia Pacific
    'ap-south-1',     # Asia Pacific (Mumbai)
    'ap-southeast-1', # Asia Pacific (Singapore)
    'ap-southeast-2', # Asia Pacific (Sydney)
    'ap-northeast-1', # Asia Pacific (Tokyo)
    'ap-northeast-2', # Asia Pacific (Seoul)
    'ap-northeast-3', # Asia Pacific (Osaka)
    'ap-east-1',      # Asia Pacific (Hong Kong)
    # South America
    'sa-east-1',      # South America (São Paulo)
    # Middle East
    'me-south-1',     # Middle East (Bahrain)
    # Africa
    'af-south-1',     # Africa (Cape Town)
    # Canada
    'ca-central-1',   # Canada (Montreal)
]


def test_region_speed(bucket: str, region: str, test_key: str = 'rxte/') -> Optional[float]:
    """Test download speed from a specific region.
    
    Returns:
        Download speed in MB/s, or None if region doesn't work
    """
    try:
        s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED), region_name=region)
        
        # List objects to test connectivity
        start = time.time()
        response = s3.list_objects_v2(Bucket=bucket, Prefix=test_key, MaxKeys=10)
        elapsed = time.time() - start
        
        if elapsed > 0:
            # Simple metric: 1/latency (faster = better)
            return 1.0 / elapsed
        return None
    except Exception as e:
        logger.debug(f"Region {region} failed: {e}")
        return None


def find_fastest_region(bucket: str, regions: List[str] = POSSIBLE_REGIONS) -> str:
    """Auto-detect fastest region for downloads.
    
    Returns:
        Fastest region name
    """
    logger.info("Testing download speeds from different regions...")
    
    speeds = {}
    for region in regions:
        logger.info(f"  Testing {region}...")
        speed = test_region_speed(bucket, region)
        if speed:
            speeds[region] = speed
            logger.info(f"    {region}: {speed:.2f} score")
    
    if not speeds:
        logger.warning("No regions responded, using default us-east-1")
        return DEFAULT_REGION
    
    fastest = max(speeds.items(), key=lambda x: x[1])[0]
    logger.info(f"✓ Fastest region: {fastest}")
    return fastest


def save_preferred_region(region: str, config_path: Path = None):
    """Save preferred region to config file."""
    if config_path is None:
        config_path = Path.home() / '.autorxte' / 'download_region.json'
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump({'region': region, 'saved_at': datetime.now().isoformat()}, f)
    logger.info(f"Saved preferred region: {region}")


def load_preferred_region(config_path: Path = None) -> Optional[str]:
    """Load previously saved preferred region."""
    if config_path is None:
        config_path = Path.home() / '.autorxte' / 'download_region.json'
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return data.get('region')
        except:
            return None
    return None


def choose_max_workers(n_files: int, avg_size_kb: float) -> int:
    """Pick optimal thread count based on file count and size."""
    cpu = multiprocessing.cpu_count()
    if avg_size_kb < 500:
        return min(n_files, max(8, cpu * 10), 64)
    else:
        return min(n_files, max(4, cpu * 5), 32)


def human_readable_size(n_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    if n_bytes >= 1 << 30:
        return f"{n_bytes / (1 << 30):.2f} GB"
    else:
        return f"{n_bytes / (1 << 20):.2f} MB"


def download_s3_prefix(
    s3_client,
    prefix: str,
    local_dir: Path,
    record_file: Path,
    bucket: str = DEFAULT_BUCKET,
    overwrite: bool = False
) -> Tuple[int, float]:
    """Download everything under an S3 prefix."""
    paginator = s3_client.get_paginator('list_objects_v2')
    objs = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objs.extend(page.get('Contents', []))
    
    keys = [o['Key'] for o in objs]
    sizes = {o['Key']: o['Size'] for o in objs}
    total_bytes = sum(sizes.values())
    
    logger.info(f"Found {len(keys)} files ({human_readable_size(total_bytes)})")
    
    if overwrite and record_file.exists():
        record_file.unlink()
    
    downloaded = set()
    if record_file.exists():
        with open(record_file, 'r') as rf:
            downloaded = set(json.load(rf))
    
    avg_kb = (total_bytes / len(keys) / 1024) if keys else 0
    workers = choose_max_workers(len(keys), avg_kb)
    logger.info(f"Using {workers} parallel workers")
    
    lock = threading.Lock()
    downloaded_bytes = 0
    start_time = time.time()
    
    def worker(key):
        nonlocal downloaded_bytes
        if key in downloaded:
            return
        dest = local_dir / key[len(prefix):].lstrip('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            s3_client.download_file(bucket, key, str(dest))
            with lock:
                downloaded.add(key)
                downloaded_bytes += sizes[key]
                with open(record_file, 'w') as rf:
                    json.dump(sorted(downloaded), rf, indent=2)
                pct = downloaded_bytes / total_bytes * 100
                print(f"\r  {human_readable_size(downloaded_bytes)} / "
                      f"{human_readable_size(total_bytes)} ({pct:.1f}%)", end='', flush=True)
        except Exception as e:
            logger.error(f"Failed {key}: {e}")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, k) for k in keys]
        for _ in as_completed(futures):
            pass
    
    duration = time.time() - start_time
    print()
    return downloaded_bytes, duration


def search_and_download(
    source: Optional[str] = None,
    catalog: Optional[str] = None,
    radius: Optional[float] = None,
    output_dir: Optional[Path] = None,
    min_exposure: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    top_n: Optional[int] = None,
    bottom_n: Optional[int] = None,
    obsids: Optional[List[str]] = None,
    overwrite: Optional[bool] = None,
    bucket: Optional[str] = None,
    region: Optional[str] = None,
    interactive: bool = True
):
    """
    Search HEASARC and download RXTE observations.
    
    ⚠️ Note for International Users:
    Downloads come from AWS S3 in us-east-1 (US East Coast).
    Users far from this region may experience slower speeds.
    You can try changing the region parameter if NASA has regional mirrors.
    
    Args:
        source: Source name or coordinates
        catalog: HEASARC catalog (default: xtemaster)
        radius: Search radius in arcminutes (default: 5.0)
        output_dir: Output directory (default: current directory)
        min_exposure: Minimum exposure in seconds
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        top_n: Download top N by exposure
        bottom_n: Download bottom N by exposure
        obsids: Specific ObsIDs to download
        overwrite: Re-download existing files
        bucket: S3 bucket name (default: nasa-heasarc)
        region: AWS S3 region (default: us-east-1)
        interactive: Enable interactive prompts for missing arguments
    """
    # Get config defaults
    from autorxte.config import get_config
    config = get_config()
    
    if bucket is None:
        bucket = config.get('download.s3.bucket', DEFAULT_BUCKET)
    
    # Region selection (interactive or config)
    if region is None and interactive:
        # Check for saved preferred region
        saved_region = load_preferred_region()
        
        if saved_region:
            print(f"\nPreviously used region: {saved_region}")
            use_saved = get_yes_no("Use this region?", True)
            if use_saved:
                region = saved_region
        
        if region is None:
            print("\nRegion Selection:")
            print("1) Auto-detect fastest region (recommended)")
            print("2) Specify region manually")
            print("3) Use default (us-east-1)")
            
            choice = get_choice("Choose option", ['1', '2', '3'], '1')
            
            if choice == '1':
                region = find_fastest_region(bucket)
                save_pref = get_yes_no("Save this region for future downloads?", True)
                if save_pref:
                    save_preferred_region(region)
            
            elif choice == '2':
                print("\nAvailable regions:")
                for i, r in enumerate(POSSIBLE_REGIONS, 1):
                    print(f"  {i}) {r}")
                region = get_input("Region name", DEFAULT_REGION)
                save_pref = get_yes_no("Save this region for future downloads?", True)
                if save_pref:
                    save_preferred_region(region)
            
            else:
                region = DEFAULT_REGION
    
    # Fallback to config or default
    if region is None:
        region = config.get('download.s3.region', DEFAULT_REGION)
    # Interactive mode for missing arguments
    if interactive:
        source = get_input("Source name or coordinates", arg_value=source)
        catalog = get_input("Catalog", DEFAULT_CATALOG, catalog)
        radius = get_float("Search radius (arcmin)", 5.0, radius, min_val=0.1)
        output_dir = get_path("Output directory", Path('.'), output_dir)
        
        use_filters = get_yes_no("Apply filters (exposure, date)?", False)
        if use_filters:
            min_exposure = get_float("Minimum exposure (seconds)", arg_value=min_exposure, min_val=0)
            start_date = get_input("Start date (YYYY-MM-DD)", arg_value=start_date)
            end_date = get_input("End date (YYYY-MM-DD)", arg_value=end_date)
    else:
        # Non-interactive mode - use defaults
        if catalog is None:
            catalog = DEFAULT_CATALOG
        if radius is None:
            radius = 5.0
        if output_dir is None:
            output_dir = Path('.')
    
    # S3 client
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED), region_name=region)
    
    # Parse position
    try:
        if bool(re.search(r'[A-Za-z]', source)):
            pos = SkyCoord.from_name(source)
        else:
            pos = SkyCoord(source, unit=u.deg)
    except Exception as e:
        logger.error(f"Could not resolve source '{source}': {e}")
        logger.error("Try using coordinates like '83.633 22.015' instead")
        raise
    
    logger.info(f"Searching {source} (RA={pos.ra.deg:.3f}, Dec={pos.dec.deg:.3f})")
    
    # Query HEASARC - don't assume 'cycle' column exists
    heas = Heasarc()
    try:
        tbl = heas.query_region(
            pos,
            catalog=catalog,
            radius=(radius / 60.0) * u.deg
        )
    except Exception as e:
        logger.error(f"HEASARC query failed: {e}")
        raise
    
    tbl.sort('time')
    tbl = tbl[(tbl['time'] != "") & (tbl['obsid'] != "") & (tbl['exposure'] != "")]
    
    logger.info(f"Found {len(tbl)} observations")
    
    # Apply filters
    if min_exposure or start_date or end_date:
        mask = np.ones(len(tbl), dtype=bool)
        if min_exposure:
            mask &= tbl['exposure'].astype(float) >= min_exposure
        if start_date or end_date:
            times = Time(tbl['time'], format='mjd')
            times_dt = [datetime.fromisoformat(str(t.iso)) for t in times]
            if start_date:
                mask &= np.array([t >= datetime.fromisoformat(start_date) for t in times_dt])
            if end_date:
                mask &= np.array([t <= datetime.fromisoformat(end_date) for t in times_dt])
        tbl = tbl[mask]
        logger.info(f"After filters: {len(tbl)} observations")
    
    # Interactive download selection
    if interactive and obsids is None and top_n is None and bottom_n is None:
        print(f"\nTotal observations: {len(tbl)}")
        print(f"Mean exposure: {np.mean(tbl['exposure'].astype(float)):.1f} seconds")
        tbl[:5].pprint()
        
        choice = get_choice(
            "What to download?",
            ['all', 'top', 'bottom', 'min', 'obsids'],
            'all'
        )
        
        if choice == 'top':
            top_n = get_int("Top N observations", 5)
        elif choice == 'bottom':
            bottom_n = get_int("Bottom N observations", 5)
        elif choice == 'min':
            min_exposure = get_float("Minimum exposure", 100.0)
        elif choice == 'obsids':
            obsid_str = get_input("Comma-separated ObsIDs")
            obsids = [o.strip() for o in obsid_str.split(',')]
    
    # Select observations
    if obsids:
        links_data = tbl[[str(row['obsid']) in obsids for row in tbl]]
    elif top_n:
        tbl.sort('exposure')
        links_data = tbl[-top_n:]
    elif bottom_n:
        tbl.sort('exposure')
        links_data = tbl[:bottom_n]
    else:
        links_data = tbl
    
    logger.info(f"Downloading {len(links_data)} observations")
    
    # Get source name for directory
    values, counts = np.unique(tbl['target_name'], return_counts=True)
    source_name = values[np.argmax(counts)]
    download_dir = Path(output_dir) / f"download_RXTE_{source_name}"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    # Interactive overwrite confirmation
    if interactive and overwrite is None:
        overwrite = get_yes_no("Overwrite existing downloads?", False)
    elif overwrite is None:
        overwrite = False
    
    # Download all
    for row in links_data:
        cycle = "AO" + str(row['cycle'])
        obsid = str(row['obsid'])
        prnb = 'P' + obsid[:5]
        prefix = f"rxte/data/archive/{cycle}/{prnb}/{obsid}/"
        
        logger.info(f"Downloading ObsID {obsid}")
        obs_dir = download_dir / obsid
        record_file = download_dir / f"downloaded_RXTE_{source_name}.json"
        
        bytes_dl, secs = download_s3_prefix(s3, prefix, obs_dir, record_file, bucket=bucket, overwrite=overwrite)
        speed = bytes_dl / secs if secs > 0 else 0
        logger.info(f"ObsID {obsid}: {human_readable_size(bytes_dl)} in {secs:.1f}s "
                    f"({human_readable_size(speed)}/s)")
    
    logger.info("All downloads complete")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    parser = argparse.ArgumentParser(description='Search and download RXTE data')
    parser.add_argument('--source', help='Source name or coordinates')
    parser.add_argument('--catalog', default=DEFAULT_CATALOG)
    parser.add_argument('--radius', type=float, default=5.0)
    parser.add_argument('--output-dir', type=Path, default=Path('.'))
    parser.add_argument('--min-exposure', type=float)
    parser.add_argument('--top-n', type=int)
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--no-interactive', action='store_true', help='Disable interactive mode')
    
    args = parser.parse_args()
    
    search_and_download(
        source=args.source,
        catalog=args.catalog,
        radius=args.radius,
        output_dir=args.output_dir,
        min_exposure=args.min_exposure,
        top_n=args.top_n,
        overwrite=args.overwrite,
        interactive=not args.no_interactive
    )
