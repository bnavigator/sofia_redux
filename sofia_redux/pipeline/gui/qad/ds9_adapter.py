# ds9_adapter.py
"""
Adapter module that exposes a DS9-compatible API (class DS9) but uses
a SAMP backend (ds9samp / astropy.samp) when available, otherwise falls
back to using the real pyds9.DS9 implementation.

Drop this file next to qad_imview.py (same package) and import it by:
    import ds9_adapter as pyds9
so existing code that calls pyds9.DS9() will use this adapter.
"""

import os
import time

# Try to import preferred SAMP helpers first.
try:
    import ds9samp
except Exception:
    ds9samp = None

# Try to import the legacy pyds9 module as fallback.
try:
    import pyds9 as _real_pyds9
except Exception:
    _real_pyds9 = None

# Adapter DS9 class
class DS9Adapter:
    def __init__(self, *args, **kwargs):
        """
        Try SAMP-based DS9 first, otherwise instantiate pyds9.DS9.
        The adapter will expose .set(cmd, *args), .get(cmd), .get_arr2np(),
        .send_array(array, mask=False), .retrieve_array(), and .close()/quit() where possible.
        """
        self._backend = None
        self._client = None

        # 1) Prefer ds9samp (SAMP)
        if ds9samp is not None:
            try:
                # ds9samp.start() returns a DS9-like object
                # (it can be used in a context manager too)
                self._client = ds9samp.start()
                self._backend = "ds9samp"
            except Exception:
                # If start fails, ignore and try pyds9 below
                self._client = None
                self._backend = None

        # 2) Fallback to pyds9 if SAMP not available/failed
        if self._client is None and _real_pyds9 is not None:
            try:
                self._client = _real_pyds9.DS9(*args, **kwargs)
                self._backend = "pyds9"
            except Exception:
                self._client = None
                self._backend = None

        if self._client is None:
            raise RuntimeError("No DS9 backend available (neither ds9samp nor pyds9 succeeded).")

    # ---- Command interface ----
    def set(self, command, *args):
        """
        Accepts either:
          - a single string 'command' (ds9samp preferred)
          - pyds9 style: set(cmd, arg1, arg2)
        Adapter will try to call the underlying backend in an appropriate way.
        """
        if self._backend == "ds9samp":
            # ds9samp expects one full command string; join extras if given
            if args:
                full = f"{command} " + " ".join(str(a) for a in args)
            else:
                full = command
            return self._client.set(full)

        elif self._backend == "pyds9":
            # pyds9 supports set(cmd, *args)
            return self._client.set(command, *args)

        else:
            raise RuntimeError("No DS9 backend active in set()")

    def get(self, command, *args):
        """Retrieve a value from DS9."""
        if self._backend == "ds9samp":
            # ds9samp supports get(command, timeout=...) — assume simple get
            try:
                return self._client.get(command)
            except TypeError:
                # Some older wrappers might require different call; try concatenated args
                if args:
                    full = f"{command} " + " ".join(str(a) for a in args)
                else:
                    full = command
                return self._client.get(full)
        elif self._backend == "pyds9":
            return self._client.get(command)
        else:
            raise RuntimeError("No DS9 backend active in get()")

    def get_arr2np(self):
        """
        Return NumPy array of current frame. For pyds9 use get_arr2np; for ds9samp use retrieve_array.
        """
        if self._backend == "ds9samp":
            # ds9samp provides retrieve_array()
            return self._client.retrieve_array()
        elif self._backend == "pyds9":
            # many pyds9 versions expose get_arr2np()
            if hasattr(self._client, "get_arr2np"):
                return self._client.get_arr2np()
            # fallback: try get('data') or similar — but this is backend-dependent
            raise AttributeError("pyds9 backend does not have get_arr2np()")
        else:
            raise RuntimeError("No DS9 backend active in get_arr2np()")

    def send_array(self, arr, mask=False):
        """Send a numpy array to DS9 (if backend supports)."""
        if self._backend == "ds9samp":
            # ds9samp has send_array
            return self._client.send_array(arr)
        elif self._backend == "pyds9":
            # pyds9 may provide array sending; use a generic route via temporary FITS if needed
            # write to a temporary file and load it
            import tempfile
            from astropy.io import fits as _fits
            tf = tempfile.NamedTemporaryFile(suffix=".fits", delete=False)
            tf.close()
            _fits.PrimaryHDU(arr).writeto(tf.name, overwrite=True)
            self._client.set("file " + tf.name)
            # do not remove immediately — let user/DS9 read it; caller can remove
            return tf.name
        else:
            raise RuntimeError("No DS9 backend active in send_array()")

    def retrieve_array(self):
        """Alias for retrieve_array (ds9samp) or fallback."""
        if self._backend == "ds9samp":
            return self._client.retrieve_array()
        elif self._backend == "pyds9":
            if hasattr(self._client, "get_arr2np"):
                return self._client.get_arr2np()
            raise AttributeError("pyds9 backend does not support retrieve_array()")
        else:
            raise RuntimeError("No DS9 backend active in retrieve_array()")

    def notify(self, mtype, params):
        """
        If caller wants to use SAMP notify directly, allow it when using ds9samp.
        For pyds9 this is not supported.
        """
        if self._backend == "ds9samp":
            # ds9samp start returns object, but for SAMP notify you may use astropy.samp directly.
            # ds9samp client likely has a 'client' attribute or a 'notify' wrapper — try best effort:
            if hasattr(self._client, "notify"):
                return self._client.notify(mtype, params)
            # if not available, provide no-op or raise
            raise NotImplementedError("notify not available on ds9samp wrapper instance")
        else:
            raise NotImplementedError("notify only available for SAMP backend")

    def close(self):
        """Close/cleanup connection. For ds9samp call ds9samp.end(), for pyds9 call close/quit if available."""
        if self._backend == "ds9samp":
            try:
                if hasattr(ds9samp, "end"):
                    ds9samp.end(self._client)
                elif hasattr(self._client, "disconnect"):
                    self._client.disconnect()
            except Exception:
                pass
        elif self._backend == "pyds9":
            # pyds9 may expose quit/close
            if hasattr(self._client, "close"):
                try:
                    self._client.close()
                except Exception:
                    pass
            if hasattr(self._client, "quit"):
                try:
                    self._client.quit()
                except Exception:
                    pass

    # For compatibility
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
