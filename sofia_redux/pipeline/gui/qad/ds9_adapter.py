"""DS9 SAMP adapter using ds9samp library."""

from astropy import log
import os
import subprocess
import time

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
        try:
            import ds9samp
        except ImportError as e:
            raise ImportError("ds9samp is required for DS9 SAMP integration") from e

        self._ds9_process = None
        
        if not self._is_ds9_running():
            if start_ds9:
                log.info("DS9 not found. Starting DS9 with SAMP support...")
                self._start_ds9()
                self._wait_for_ds9_startup()
            else:
                raise ValueError("DS9 is not running or not SAMP-enabled. Please start DS9 with 'ds9 -samp' or set start_ds9=True")

        # Start ds9samp connection
        self._ds9 = ds9samp.start(client=target)
        self._ds9.timeout = 30

        # Final check to ensure connection is established
        if not self._is_ds9_running():
            raise ValueError("Failed to establish SAMP connection with DS9")

    def _start_ds9(self):
        """Start DS9 with SAMP support in the background."""
        try:
            # Start DS9 with SAMP enabled in background
            self._ds9_process = subprocess.Popen(
                ['ds9', '-samp'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            log.info(f"Started DS9 process with PID: {self._ds9_process.pid}")
        except FileNotFoundError:
            raise FileNotFoundError(
                "DS9 executable not found. Please ensure DS9 is installed and in your PATH."
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
                log.info("DS9 started successfully and SAMP connection is ready")
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
            # Try to create a temporary connection to check if DS9 is SAMP-ready
            test_ds9 = ds9samp.start()
            result = test_ds9.get("version", timeout=1)
            ds9samp.end(test_ds9)
            return result is not None and result.strip() != ""
        except Exception:
            return False

    def set(self, cmd, buf=None):
        """
        Send a set command to DS9 via SAMP.

        Parameters
        ----------
        cmd : str
            DS9 command.
        buf : str, bytes, or file-like, optional
            Additional buffer data (not supported in SAMP, logged as warning).

        Returns
        -------
        None
            ds9samp.set does not return a value.
        """
        if buf is not None:
            return self._set_with_buffer(cmd, buf)
        try:
            self._ds9.set(cmd)
            return 1
        except Exception:
            return 0

    def _set_with_buffer(self, cmd, buf):
        """Handle two-parameter calls"""
        if cmd == 'regions' and buf is not None:
            try:
                # DS9 accepts regions directly without "command" keyword
                self._ds9.set(f'regions command {{{buf}}}')
                return 1
            except Exception as e:
                log.error(f"Region setting failed: {e}")
                return 0
        else:
            try:
                return self._ds9.set(f"{cmd} {buf}")
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
        return self._ds9.get(cmd)

    def get_arr2np(self):
        """ds9samp function wrapper to fetch numpy array data."""
        try:
            return self._ds9.retrieve_array()
        except Exception:
            log.warning('Could not fetch array data from DS9 using SAMP')

    def quit(self):
        """Quit DS9."""
        try:
            import ds9samp
            ds9samp.end(self._ds9)   
        except Exception:
            pass
        
        if self._ds9_process:
            try:
                if os.name != 'nt':
                    # On Unix-like systems, kill the process group
                    os.killpg(os.getpgid(self._ds9_process.pid), subprocess.signal.SIGTERM)
                else:
                    # On Windows, terminate the process
                    self._ds9_process.terminate()
                self._ds9_process.wait(timeout=5)
                log.info("DS9 process terminated successfully")
            except Exception as e:
                log.warning(f"Could not cleanly terminate DS9 process: {e}")
                try:
                    self._ds9_process.kill()
                except Exception:
                    pass
            finally:
                self._ds9_process = None