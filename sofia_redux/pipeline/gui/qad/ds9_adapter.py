"""DS9 SAMP adapter using ds9samp library."""

import os
import subprocess
import time
import re
import shutil
import pathlib

from astropy import log

try:
    import ds9samp
except ImportError:
    ds9samp = None

__all__ = ['DS9']

class DS9:
    """
    DS9 SAMP adapter for Redux.

    This class manages a SAMP connection to DS9 using the ds9samp library.
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
        self._ds9_connection = None
        self._target = target
        self._start_ds9 = start_ds9

        if ds9samp is None:
            log.warning(
                "ds9samp is not installed. Please install it with: "
                "pip install ds9samp")
            raise RuntimeError(
                "ds9samp is required for DS9 SAMP integration. "
                "Install with: pip install ds9samp")

        self._connect_to_ds9()

    def _connect_to_ds9(self):
        """Establish SAMP connection to DS9.

        Also start DS9 if not running and start_ds9 is True.
        """
        if ((self._ds9_process is None  # has not been started by us
             or self._ds9_process.poll() is not None) # process has died
            and not self._is_ds9_running()  # has not been started externally
            ):
            # Start DS9 if allowed
            if not self._start_ds9:
                raise RuntimeError(
                    "DS9 is not running or not SAMP-enabled. Please "
                    "start DS9 with 'ds9 -samp' or set start_ds9=True")
            log.info("Starting DS9 with SAMP support...")
            self._start_ds9_process()

        self._ds9_connection = ds9samp.start(client=self._target)
        self._ds9_connection.timeout = 30

    def _is_ds9_connected(self):
        """Check if DS9 SAMP connection is active.

        Resets connection status if not connected.
        """
        log.debug("Checking DS9 SAMP connection status ...")
        if self._ds9_connection is None:
            is_connected = False
        else:
            # This is astropy.samp.SAMPIntegratedClient.ping()
            try:
                self._ds9_connection.ds9.ping()
                is_connected = True
            except ConnectionRefusedError:
                is_connected = False
        log.debug(f"   ... {is_connected}")
        if not is_connected:
            self._ds9_connection = None
        return is_connected

    def _start_ds9_process(self, timeout=30, check_interval=1):
        """Start DS9 with SAMP support in the background."""
        ds9_path = shutil.which('ds9')

        # check common installation locations
        if ds9_path is None and os.name == 'nt':
            common_paths = [
                r'C:\Program Files\SAOImageDS9\ds9.exe',
                r'C:\Program Files (x86)\SAOImageDS9\ds9.exe',
                r'C:\SAOImageDS9\ds9.exe',
            ]
            for path in common_paths:
                if os.path.exists(path):
                    log.info(f"Found DS9 at: {path}")
                    ds9_path = path
                    break

        if ds9_path is None:
            ds9_path = 'ds9'

        start_time = time.time()
        if os.name == 'nt':
            # Windows: use CREATE_NEW_PROCESS_GROUP flag
            spkw = dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            # Unix/macOS: use process group with setsid
            spkw = dict(preexec_fn=os.setsid)
        try:
            self._ds9_process = subprocess.Popen(
                [ds9_path, '-samp'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **spkw)
        except FileNotFoundError as err:
            raise RuntimeError(
                "DS9 executable not found. Please ensure DS9 is installed "
                "and in your PATH or open it manually before starting the "
                "reduction."
            ) from err
        except Exception as err:
            raise RuntimeError("Failed to start DS9") from err
        log.info(f"Started DS9 process with PID: {self._ds9_process.pid}")

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
        """Check if DS9 process is running and SAMP-enabled."""
        if ds9samp is None:
            raise RuntimeError("ds9samp is not available")
        try:
            # try to create a temporary connection to check if DS9 is SAMP-ready
            with ds9samp.ds9samp(client=self._target) as test_ds9:
                result = test_ds9.get("version", timeout=1)
            return result is not None and result.strip() != ""
        except Exception as e:
            log.debug(f"DS9 SAMP check failed: {e}")
            return False

    def set(self, cmd):
        """
        Send a set command to DS9 via SAMP.

        Parameters
        ----------
        cmd : str
            DS9 command.

        Returns
        -------
        int
            1 on success, 0 on failure.
        """
        log.debug(f"Sending DS9 set command: {cmd}")
        if not self._is_ds9_connected():
            self._connect_to_ds9()
        try:
            self._ds9_connection.set(cmd)
            return 1
        except Exception as e:
            log.warning(f"DS9 set command '{cmd}' failed: {e}")
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
        log.debug(f"Sending DS9 get command : {cmd}")
        if not self._is_ds9_connected():
            self._connect_to_ds9()
        try:
            return self._ds9_connection.get(cmd)
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
        if not self._is_ds9_connected():
            self._connect_to_ds9()
        try:
            return self._ds9_connection.retrieve_array()
        except Exception as e:
            log.warning(f'Could not fetch array data from DS9 using SAMP: {e}')

    def quit(self):
        """Quit DS9."""
        try:
            ds9samp.end(self._ds9_connection)
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


def sanitize_path_ds9(path):
    """
    Sanitize file paths in DS9 commands for cross-platform compatibility.

    Parameters
    ----------
    cmd : str
        DS9 command.
    Returns
    -------
    str
        Sanitized DS9 command.
    """
    return pathlib.PureWindowsPath(path).as_posix().replace(' ', r'\ ')
