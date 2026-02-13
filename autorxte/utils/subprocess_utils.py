"""Subprocess utilities for running HEASoft tools safely."""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class HEASoftToolError(Exception):
    """Raised when a HEASoft tool execution fails."""
    pass


def check_heasoft_tool(tool_name: str) -> bool:
    """
    Check if a HEASoft tool is available.
    
    Args:
        tool_name: Name of the tool (e.g., 'seextrct', 'lcurve')
        
    Returns:
        True if tool exists, False otherwise
    """
    return shutil.which(tool_name) is not None


def require_heasoft_tool(tool_name: str):
    """
    Check if a HEASoft tool exists, raise error if not.
    
    Args:
        tool_name: Name of the tool
        
    Raises:
        FileNotFoundError: If tool not found
    """
    if not check_heasoft_tool(tool_name):
        raise FileNotFoundError(
            f"HEASoft tool '{tool_name}' not found. "
            f"Is HEASoft installed and initialized? "
            f"Try running: heainit"
        )


def run_heasoft_tool(
    tool_name: str,
    script_lines: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict] = None,
    timeout: Optional[int] = None,
    capture_output: bool = True
) -> subprocess.CompletedProcess:
    """
    Run a HEASoft tool with input from a script.
    
    Args:
        tool_name: Name of the tool (e.g., 'seextrct', 'lcurve')
        script_lines: List of input lines for the tool
        cwd: Working directory
        env: Environment variables
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        
    Returns:
        CompletedProcess object
        
    Raises:
        FileNotFoundError: If tool not found
        HEASoftToolError: If tool execution fails
        subprocess.TimeoutExpired: If tool times out
    """
    # Verify tool exists
    require_heasoft_tool(tool_name)
    
    logger.debug(f"Running {tool_name} with {len(script_lines)} input lines")
    
    try:
        result = subprocess.run(
            [tool_name],
            input='\n'.join(script_lines) + '\n',
            text=True,
            capture_output=capture_output,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=True
        )
        logger.debug(f"{tool_name} completed successfully")
        return result
        
    except subprocess.TimeoutExpired as e:
        logger.error(f"{tool_name} timed out after {timeout}s")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"{tool_name} failed with return code {e.returncode}")
        if e.stderr:
            logger.error(f"Error output: {e.stderr}")
        raise HEASoftToolError(
            f"{tool_name} failed: {e.stderr if e.stderr else 'Unknown error'}"
        ) from e


@contextmanager
def temporary_script(script_lines: List[str], script_path: Path):
    """
    Context manager for creating temporary script files.
    
    Args:
        script_lines: Lines to write to script
        script_path: Path for temporary script file
        
    Yields:
        Path to the script file
        
    Example:
        with temporary_script(lines, Path('temp.txt')) as script:
            subprocess.run(['tool'], stdin=script.open('r'))
    """
    try:
        script_path.write_text('\n'.join(script_lines) + '\n')
        logger.debug(f"Created temporary script: {script_path}")
        yield script_path
    finally:
        if script_path.exists():
            script_path.unlink()
            logger.debug(f"Cleaned up temporary script: {script_path}")
