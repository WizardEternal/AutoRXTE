"""Configuration Management for AutoRXTE.

Loads and manages configuration parameters from autorxte_config.yaml.
Users can override defaults by placing a config file in their working directory.
"""
import yaml
import multiprocessing
from pathlib import Path
from typing import Any, Dict, Optional

# Default config file locations (in priority order)
CONFIG_SEARCH_PATHS = [
    Path.cwd() / 'autorxte_config.yaml',           # Current directory
    Path.home() / '.autorxte' / 'config.yaml',     # User home
    Path(__file__).parent.parent / 'autorxte_config.yaml',  # Package directory
]

class Config:
    """Configuration manager for AutoRXTE."""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        """Singleton pattern - only one config instance."""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize config by loading from file."""
        if self._config is None:
            self.load()
    
    def load(self, config_path: Optional[Path] = None):
        """Load configuration from YAML file.
        
        Args:
            config_path: Specific config file to load. If None, searches default locations.
        """
        if config_path:
            config_file = Path(config_path)
        else:
            # Search for config file in default locations
            config_file = None
            for path in CONFIG_SEARCH_PATHS:
                if path.exists():
                    config_file = path
                    break
        
        if config_file and config_file.exists():
            with open(config_file) as f:
                self._config = yaml.safe_load(f)
        else:
            # Use minimal defaults if no config file found
            self._config = self._get_minimal_defaults()
    
    def _get_minimal_defaults(self) -> Dict:
        """Get minimal default configuration."""
        return {
            'global': {
                'auto_workers': True,
                'default_workers': 4,
                'log_level': 'INFO',
                'cleanup_temp_files': True,
                'overwrite_outputs': False,
                'interactive_default': False,
            },
            'download': {'workers': 'auto'},
            'preparation': {'workers': 'auto', 'skip_existing': True},
            'organization': {'move_mode': True, 'overwrite': False},
            'bitmasks': {
                'e_token_bitmask': 'bitmask_event',
                'xenon_bitmask': 'bitmask_xenon',
                'overwrite': False
            },
            'filtering': {
                'filter_expression': "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) && .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)"
            },
            'extraction': {
                'token': 'e',
                'bitmask': 'bitmask_event',
                'prefix': 'event',
                'split_gti': False,
                'workers': 'auto',
                'time_bin': 0.004,
                'use_ranges': False
            },
            'lightcurves': {
                'type': 'std2',
                'std1': {'output_name': 'std1.lc', 'pcu_selection': 2, 'bin_size_sec': 0.125},
                'std2': {'output_name': 'light.lc', 'pcu_selection': 2, 'energy_channels': 'ALL', 'time_bins': 16}
            },
            'spectra': {
                'pcu_selection': 2,
                'energy_channels': 'ALL',
                'source_file': 'src.pha',
                'background_file': 'bkg.pha',
                'response_file': 'rsp.pha'
            },
            'pds': {
                'input_lightcurve': 'event.lc',
                'binning': '-1',
                'rebin': '-1.03',
                'max_bins': 8192,
                'window': 'none',
                'norm': -2,
                'output_png': 'pds.png/png',
                'workers': 'auto'
            },
            'color_analysis': {
                'ranges': {'soft': '0-13', 'medium': '14-35', 'hard': '36-255'},
                'color_names': ['soft', 'medium', 'hard'],
                'time_bin': 0.04,
                'lcurve_bin_size': '-1',
                'max_bins': 2000000,
                'plot_format': 'png',
                'workers': 'auto'
            },
            'xspec': {
                'default_model': 'diskbb_pexrav',
                'energy_range': {'min': 3.0, 'max': 30.0},
                'max_iterations': 1000,
                'save_plots': True,
                'plot_format': 'png'
            },
            'xenon': {
                'fits_extension': 'XTE_SP',
                'output_root': 'event',
                'event_pattern': 'xenon_event_gx*',
                'use_terminals': False
            },
            'plotting': {
                'bin_size': 1.0,
                'max_bins': 10000,
                'format': 'png',
                'workers': 'auto'
            }
        }
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated key path.
        
        Args:
            key_path: Dot-separated path (e.g., 'download.workers')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
            
        Examples:
            >>> config = Config()
            >>> config.get('download.workers')
            'auto'
            >>> config.get('lightcurves.std1.bin_size_sec')
            0.125
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        # Handle 'auto' workers
        if value == 'auto' and 'worker' in key_path.lower():
            return multiprocessing.cpu_count()
        
        return value
    
    def get_section(self, section: str) -> Dict:
        """Get entire configuration section.
        
        Args:
            section: Section name (e.g., 'download', 'lightcurves')
            
        Returns:
            Dictionary of all parameters in section
        """
        return self._config.get(section, {})
    
    def resolve_workers(self, workers: Optional[int]) -> int:
        """Resolve worker count (handles 'auto').
        
        Args:
            workers: Number of workers or None
            
        Returns:
            Resolved worker count
        """
        if workers is None:
            workers = self.get('global.default_workers', 4)
        
        if workers == 'auto' or (isinstance(workers, str) and workers.lower() == 'auto'):
            return multiprocessing.cpu_count()
        
        return int(workers)
    
    def get_color_ranges(self) -> tuple:
        """Get color analysis ranges and names.
        
        Returns:
            (ranges_list, names_list) tuple
        """
        ranges_dict = self.get('color_analysis.ranges', {})
        names = self.get('color_analysis.color_names', [])
        
        # Convert dict to list in order of names
        ranges_list = [ranges_dict.get(name, f"0-{i*10}") for i, name in enumerate(names)]
        
        return ranges_list, names
    
    def get_filter_expression(self) -> str:
        """Get GTI filter expression."""
        return self.get('filtering.filter_expression',
                       "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) && .NOT. ISNULL(ELV) && (NUM_PCU_ON < 6)")
    
    def get_xspec_model(self, model_name: Optional[str] = None) -> Dict:
        """Get XSPEC model configuration.
        
        Args:
            model_name: Model name or None for default
            
        Returns:
            Model configuration dict
        """
        if model_name is None:
            model_name = self.get('xspec.default_model', 'diskbb_pexrav')
        
        return self.get(f'xspec.models.{model_name}', {})

# Global config instance
_config_instance = None

def get_config() -> Config:
    """Get global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance

def load_config(config_path: Optional[Path] = None):
    """Load configuration from file.
    
    Args:
        config_path: Path to config file. If None, searches default locations.
    """
    config = get_config()
    config.load(config_path)

# Convenience functions
def get(key_path: str, default: Any = None) -> Any:
    """Get configuration value."""
    return get_config().get(key_path, default)

def get_section(section: str) -> Dict:
    """Get configuration section."""
    return get_config().get_section(section)
