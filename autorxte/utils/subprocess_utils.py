"""Subprocess utilities for running HEASoft tools safely."""

import logging
import os
import pty
import select
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Tuple
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


def run_heasoft_pty(
    cmd: List[str],
    input_text: Optional[str] = None,
    cwd: Optional[Path] = None,
    env: Optional[Dict] = None,
    timeout: Optional[int] = None,
    must_exist: Optional[List[Path]] = None,
) -> Tuple[int, str]:
    """Run a HEASoft tool under a pseudo-terminal.

    HEASoft FTOOLS (pcaprepobsid, seextrct, maketime, lcurve, ...) open
    /dev/tty for prompts and refuse to start when stdin is a pipe or
    /dev/null, even when every parameter is supplied on the command line.
    They typically exit with OS code 0 even on this kind of failure
    ("Task <name> terminating with status N"), so checking the OS exit
    code alone is not enough.

    This wrapper:
      1. Allocates a pty so the tool sees a real TTY and starts.
      2. Optionally writes `input_text` (e.g. for stdin-driven tools like
         maketime) to the pty master before reading output.
      3. Captures combined stdout+stderr from the pty master.
      4. Enforces a timeout (default unlimited).
      5. After exit, checks any caller-provided output paths exist; if
         they do not, raises HEASoftToolError regardless of exit code.

    Args:
        cmd: Full argv list, e.g. ['pcaprepobsid', 'indir=...', 'outdir=...', 'mode=h']
        input_text: Lines to send on stdin (must end each line with \\n).
            For tools that read parameter values one-per-line (maketime, etc.).
        cwd: Working directory.
        env: Environment dict (default: inherit).
        timeout: Seconds before killing the child (default: no timeout).
        must_exist: Paths that must exist after the call. If any are
            missing, raise HEASoftToolError (catches silent failures).

    Returns:
        (returncode, combined_output_text)

    Raises:
        FileNotFoundError: tool not on PATH.
        HEASoftToolError: nonzero exit, or must_exist path missing.
        subprocess.TimeoutExpired: tool exceeded timeout.
    """
    require_heasoft_tool(cmd[0])

    master_fd, slave_fd = pty.openpty()

    # HEASoft tools open /dev/tty; for that to resolve to our pty, the child
    # must put the slave on a new session as its controlling terminal. Done
    # in a preexec_fn that runs after fork, before exec, in the child only.
    def _make_controlling_tty():
        os.setsid()
        try:
            import fcntl
            import termios
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        except (ImportError, OSError):
            pass

    # Provide a sane TERM if the parent didn't.
    child_env = dict(env) if env is not None else os.environ.copy()
    child_env.setdefault('TERM', 'dumb')

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(cwd) if cwd else None,
            env=child_env,
            close_fds=True,
            preexec_fn=_make_controlling_tty,
        )
        # Parent only needs the master end; close slave so we get EOF on exit.
        os.close(slave_fd)
        slave_fd = -1

        # If we have stdin lines to send, write them up-front. Tools that read
        # interactively will consume them line by line. Small inputs fit in the
        # pty buffer; larger ones may need chunked writes (not relevant for
        # parameter-style input, which is at most a few kB).
        if input_text:
            try:
                os.write(master_fd, input_text.encode())
            except OSError as e:
                logger.debug(f"Could not write stdin to pty: {e}")

        chunks: List[bytes] = []
        import time
        start = time.monotonic()
        while True:
            if timeout is not None and (time.monotonic() - start) > timeout:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(cmd, timeout)
            # Wait up to 1s for output, then re-check timeout/exit.
            r, _, _ = select.select([master_fd], [], [], 1.0)
            if r:
                try:
                    data = os.read(master_fd, 65536)
                except OSError:
                    data = b''
                if not data:
                    break
                chunks.append(data)
            elif proc.poll() is not None:
                # Drain any remaining output then exit.
                while True:
                    r2, _, _ = select.select([master_fd], [], [], 0.0)
                    if not r2:
                        break
                    try:
                        data = os.read(master_fd, 65536)
                    except OSError:
                        data = b''
                    if not data:
                        break
                    chunks.append(data)
                break

        proc.wait()
        output = b''.join(chunks).decode(errors='replace')
        rc = proc.returncode

        # Heuristic: HEASoft prints "Task <tool> ... terminating with status N"
        # where N != 0 means failure even when the OS exit code is 0.
        terminated_status = None
        for line in output.splitlines():
            line = line.strip()
            if 'terminating with status' in line.lower():
                # ".. terminating with status 6"
                try:
                    terminated_status = int(line.rstrip('.').split()[-1])
                except (ValueError, IndexError):
                    pass

        if rc != 0:
            raise HEASoftToolError(
                f"{cmd[0]} exited with code {rc}\n{output[-2000:]}"
            )

        if terminated_status not in (None, 0):
            raise HEASoftToolError(
                f"{cmd[0]} reported terminating status {terminated_status} "
                f"(OS exit code was {rc}).\n{output[-2000:]}"
            )

        if must_exist:
            missing = [str(p) for p in must_exist if not Path(p).exists()]
            if missing:
                raise HEASoftToolError(
                    f"{cmd[0]} returned 0 but expected outputs are missing: "
                    f"{missing}\n{output[-2000:]}"
                )

        return rc, output

    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        if slave_fd != -1:
            try:
                os.close(slave_fd)
            except OSError:
                pass


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
