"""FITS file utilities shared across autorxte."""

import logging
from pathlib import Path
from typing import List
from astropy.io import fits

logger = logging.getLogger(__name__)


def split_gti(gti_path: Path, output_dir: Path) -> List[Path]:
    """
    Split a multi-row GTI FITS file into individual files.
    
    This is commonly needed when processing GTI files that contain multiple
    good time intervals. Each interval is split into a separate file for
    individual processing.
    
    Args:
        gti_path: Path to input GTI FITS file
        output_dir: Directory for output GTI files
        
    Returns:
        List of paths to created GTI files (sorted)
        
    Raises:
        FileNotFoundError: If gti_path doesn't exist
        ValueError: If GTI file is invalid or has wrong structure
    """
    if not gti_path.exists():
        raise FileNotFoundError(f"GTI file not found: {gti_path}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with fits.open(gti_path) as hdul:
            if len(hdul) < 2:
                raise ValueError(f"Invalid GTI file (needs at least 2 extensions): {gti_path}")
            
            data = hdul[1].data
            n_rows = len(data)
            
            # Check if already split
            existing = sorted(output_dir.glob("good_*.gti"))
            if len(existing) == n_rows:
                logger.info(f"GTI already split into {n_rows} files")
                return existing
            
            logger.info(f"Splitting GTI into {n_rows} individual files")
            output_files = []
            
            for idx, row in enumerate(data, start=1):
                # Create columns for single-row GTI
                cols = [
                    fits.Column(
                        name=col.name,
                        format=col.format,
                        array=[row[col.name]]
                    )
                    for col in hdul[1].columns
                ]
                
                # Create new HDU with single row
                tbl = fits.BinTableHDU.from_columns(cols, header=hdul[1].header)
                hdu_list = fits.HDUList([hdul[0], tbl])
                
                # Write to file
                out_path = output_dir / f"good_{idx}.gti"
                hdu_list.writeto(out_path, overwrite=True)
                output_files.append(out_path)
            
            logger.info(f"Created {len(output_files)} GTI files")
            return output_files
            
    except Exception as e:
        logger.error(f"Failed to split GTI file: {e}")
        raise


def validate_fits_file(fits_path: Path, required_extensions: List[str] = None) -> bool:
    """
    Validate a FITS file structure.
    
    Args:
        fits_path: Path to FITS file
        required_extensions: List of required extension names
        
    Returns:
        True if valid, False otherwise
    """
    try:
        with fits.open(fits_path) as hdul:
            if required_extensions:
                ext_names = [ext.name for ext in hdul]
                for req in required_extensions:
                    if req not in ext_names:
                        logger.warning(f"Missing extension '{req}' in {fits_path}")
                        return False
            return True
    except Exception as e:
        logger.error(f"Invalid FITS file {fits_path}: {e}")
        return False
