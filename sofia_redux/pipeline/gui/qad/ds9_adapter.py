# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""DS9 SAMP adapter to replace pyds9 XPA integration."""

from astropy import log
import os

__all__ = ['DS9']


class DS9:
    """
    DS9 SAMP adapter mimicking pyds9.DS9 API.

    This class provides a drop-in replacement for pyds9.DS9,
    using ds9samp (SAMP wrapper) to communicate with SAOImageDS9.
    """

    def __init__(self, target=None, **kwargs):
        """
        Initialize DS9 SAMP connection.

        Parameters
        ----------
        target : str, optional
            DS9 client name (for multiple DS9 instances).
        **kwargs
            Additional arguments (ignored for compatibility).
        """
        try:
            import ds9samp
        except ImportError as e:
            raise ImportError("ds9samp is required for DS9 SAMP integration") from e

        # Set XPA_METHOD to local for compatibility, though not used in SAMP
        os.environ["XPA_METHOD"] = "local"

        # Start ds9samp connection
        self._ds9 = ds9samp.start(client=target)

        # Ensure DS9 is running with SAMP
        if not self._is_ds9_running():
            raise ValueError("DS9 is not running or not SAMP-enabled. Please start DS9 with 'ds9 -samp'")

    def _is_ds9_running(self):
        """Check if DS9 is running and SAMP-enabled."""
        try:
            # Try a simple get command to check connection
            result = self._ds9.get("version", timeout=1)
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
                print(f"Region setting failed: {e}")
                return 0
        else:
            try:
                return self._ds9.set(f"{cmd} {buf}")
            except Exception as e:
                print(f"Command failed: {e}")
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
        # Translate commands that differ between pyds9 and ds9samp
        if cmd == 'frame':
            cmd = 'frame frameno'
        
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
            self._ds9.set('quit')
        except Exception:
            pass
        finally:
            import ds9samp
            ds9samp.end(self._ds9)