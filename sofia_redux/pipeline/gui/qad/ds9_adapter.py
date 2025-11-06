"""DS9 SAMP adapter using ds9samp library."""

import os
import subprocess
import time
import re
import shutil

from astropy import log

__all__ = ['DS9']

class DS9:
    """
    DS9 SAMP adapter mimicking pyds9.DS9 API.

    This class provides a drop-in replacement for pyds9.DS9,
    using ds9samp (SAMP wrapper) to communicate with SAOImageDS9.
    """

    def __init__(self, target=None, start_ds9=True, **kwargs):
        """
        Initialize DS9 SAMP connection.

        Parameters
        ----------
        target : str, optional
            DS9 client name (for multiple DS9 instances).
        start_ds9 : bool, optional
            If True, automatically start DS9 if not running (default: True).
        **kwargs
            Additional arguments (ignored for compatibility).
        """
        self._ds9_process = None
        self._target = target
        self._ensure_ds9_available(start_ds9)
        self._connect_to_ds9()

    def _ensure_ds9_available(self, start_ds9):
        """
        Ensure DS9 is running and available.

        Parameters
        ----------
        start_ds9 : bool
            If True, start DS9 if not running.

        Raises
        ------
        ValueError
            If DS9 is not running and start_ds9 is False.
        """
        if self._is_ds9_running():
            return

        if not start_ds9:
            raise ValueError(
                "DS9 is not running or not SAMP-enabled. Please "
                "start DS9 with 'ds9 -samp' or set start_ds9=True")

        log.info("Starting DS9 with SAMP support...")
        self._start_ds9()
        self._wait_for_ds9_startup()

    def _connect_to_ds9(self):
        """Establish SAMP connection to DS9."""
        try:
            import ds9samp
        except ImportError:
            log.warning(
                "ds9samp is not installed. Please install it with: "
                "pip install ds9samp")
            raise ImportError(
                "ds9samp is required for DS9 SAMP integration. "
                "Install with: pip install ds9samp") from None
        self._ds9 = ds9samp.start(client=self._target)
        self._ds9.timeout = 30

    def _find_ds9_executable(self):
        """
        Find DS9 executable.

        Check common installation locations for Windows.
        """
        # First try PATH
        ds9_path = shutil.which('ds9')
        if ds9_path:
            return ds9_path

        # check common installation locations
        if os.name == 'nt':
            common_paths = [
                r'C:\Program Files\SAOImageDS9\ds9.exe',
                r'C:\Program Files (x86)\SAOImageDS9\ds9.exe',
                r'C:\SAOImageDS9\ds9.exe',
            ]
            for path in common_paths:
                if os.path.exists(path):
                    log.info(f"Found DS9 at: {path}")
                    return path

        # If no installation is found, just try the plain command
        return 'ds9'

    def _start_ds9(self):
        """Start DS9 with SAMP support in the background."""
        # Try to find DS9 executable
        ds9_cmd = self._find_ds9_executable()

        try:
            if os.name == 'nt':
                # Windows: use CREATE_NEW_PROCESS_GROUP flag
                import subprocess as sp
                self._ds9_process = subprocess.Popen(
                    [ds9_cmd, '-samp'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=sp.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # Unix/macOS: use process group with setsid
                self._ds9_process = subprocess.Popen(
                    [ds9_cmd, '-samp'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )
            log.info(f"Started DS9 process with PID: {self._ds9_process.pid}")
        except FileNotFoundError:
            raise FileNotFoundError(
                "DS9 executable not found. Please ensure DS9 is installed "
                "and in your PATH or open it manually before starting the "
                "reduction."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start DS9: {e}")

    def _wait_for_ds9_startup(self, timeout=30, check_interval=0.5):
        """
        Wait for DS9 to start and become SAMP-enabled.

        Parameters
        ----------
        timeout : float
            Maximum time to wait in seconds.
        check_interval : float
            Time between checks in seconds.
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._is_ds9_running():
                log.info(
                    "DS9 started successfully and SAMP connection is ready")
                return

            # Check if DS9 process is still running
            if self._ds9_process and self._ds9_process.poll() is not None:
                raise RuntimeError("DS9 process terminated unexpectedly")

            time.sleep(check_interval)

        raise TimeoutError(f"DS9 failed to start within {timeout} seconds")

    def _is_ds9_running(self):
        """Check if DS9 is running and SAMP-enabled."""
        try:
            import ds9samp
            # try to create a temporary connection to check if DS9 is SAMP-ready
            with ds9samp.ds9samp() as test_ds9:
                result = test_ds9.get("version", timeout=1)
            return result is not None and result.strip() != ""
        except Exception as e:
            log.debug(f"DS9 SAMP check failed: {e}")
            return False

    def set(self, cmd, buf=None):
        """
        Send a set command to DS9 via SAMP.

        Parameters
        ----------
        cmd : str
            DS9 command.
        buf : str, optional
            Additional string buffer (e.g., for regions commands).

        Returns
        -------
        int
            1 on success, 0 on failure.
        """
        if buf is not None:
            return self._set_with_buffer(cmd, buf)
        try:
            self._ds9.set(cmd)
            return 1
        except Exception as e:
            log.warning(f"DS9 set command '{cmd}' failed: {e}")
            return 0

    def _set_with_buffer(self, cmd, buf):
        """
        Handle set commands with buffer data.

        Parameters
        ----------
        cmd : str
            DS9 command.
        buf : str
            Buffer string to send.

        Returns
        -------
        int
            1 on success, 0 on failure.
        """
        if cmd == 'regions':
            try:
                self._ds9.set(f'regions command {{{buf}}}')
                return 1
            except Exception as e:
                log.error(f"Region setting failed: {e}")
                return 0
        else:
            try:
                self._ds9.set(f"{cmd} {buf}")
                return 1
            except Exception as e:
                log.error(f"Command failed: {e}")
                return 0

    def get(self, cmd):
        """
        Send a get command to DS9 via SAMP.

        Parameters
        ----------
        cmd : str
            DS9 command.

        Returns
        -------
        str
            Command result.
        """
        try:
            return self._ds9.get(cmd)
        except OSError as e:
            # WORKAROUND for ds9samp bug on Windows with fits commands
            # Only apply workaround for specific fits-related commands
            if (os.name == 'nt' and 'Invalid argument' in str(e)
                    and 'fits' in cmd.lower()):
                result = self._windows_path_workaround(e)
                if result is not None:
                    return result
            # If workaround didn't work or failed, raise original error
            raise

    def _windows_path_workaround(self, error):
        """
        Workaround for ds9samp bug on Windows: fixes /C:/path to C:/path.

        Parameters
        ----------
        error : OSError
            The OSError caught from ds9samp.

        Returns
        -------
        str or None
            File contents if workaround succeeded, None otherwise.
        """
        match = re.search(r"['\"](/[A-Za-z]:.+?)['\"]", str(error))
        if match:
            bad_path = match.group(1)
            fixed_path = bad_path[1:]  # Remove leading slash
            log.debug(f"Fixed Windows path: {bad_path} -> {fixed_path}")
            try:
                with open(fixed_path, 'r', encoding='ascii') as f:
                    return f.read()
            except Exception as read_error:
                log.error(f"Failed to read corrected path: {read_error}")
        return None

    def get_arr2np(self):
        """ds9samp function wrapper to fetch numpy array data."""
        try:
            return self._ds9.retrieve_array()
        except Exception as e:
            log.warning(f'Could not fetch array data from DS9 using SAMP: {e}')

    def quit(self):
        """Quit DS9."""
        try:
            import ds9samp
            ds9samp.end(self._ds9)
        except Exception as e:
            log.debug(f"Failed to end DS9 SAMP connection: {e}")

        if self._ds9_process:
            try:
                self._ds9_process.terminate()
                self._ds9_process.wait(timeout=5)
                log.info("DS9 process terminated successfully")
            except subprocess.TimeoutExpired:
                log.warning("DS9 did not terminate gracefully, forcing kill")
                self._ds9_process.kill()
            except Exception as e:
                log.warning(f"Could not terminate DS9 process: {e}")
            finally:
                self._ds9_process = None
