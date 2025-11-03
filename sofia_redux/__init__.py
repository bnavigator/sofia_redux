# Licensed under a 3-clause BSD style license - see LICENSE.rst

# version.py is written at install time by setuptools_scm
try:
    from .version import version as __version__
except ImportError:
    __version__ = ''

__all__ = []
