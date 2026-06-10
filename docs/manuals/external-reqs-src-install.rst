External Requirements
~~~~~~~~~~~~~~~~~~~~~

To run the |inst| pipeline for any mode, Python 3.11 or
higher is required, as well as  a number of packages
from the Scientific Python Ecosystem including numpy, scipy,
matplotlib, pandas, numba, astropy, and photutils.

Some display functions for the graphical user interface (GUI)
additionally require the PyQt6, ds9samp, and regions packages.
All required external packages are available to install via
PyPI.  See the `pyproject.toml` distributed with `sofia_redux`
for up-to-date version dependencies.

Running the pipeline interactively also requires an installation of
SAO DS9 for FITS image display. See http://ds9.si.edu/ for download
and installation instructions.  The *ds9* executable
must be available in the PATH environment variable for the ds9samp
interface to be able to find and control it. 

Source Code Installation
~~~~~~~~~~~~~~~~~~~~~~~~

The source code for the |inst| pipelines maintained by the SOFIA Data
Center (SDC) team can be obtained directly from the
external `GitHub repository <https://github.com/SOFIA-Data-Center/sofia_redux>`__.
This repository contains the configuration
files and Python code to run the instrument pipelines.

After obtaining the source code, install the package with
the command::

    pip install .

from the top-level directory.

Alternately, a development installation may be performed from inside the
directory with the command::

    pip install -e .


After installation, the top-level pipeline interface commands should
be available in the PATH.  Typing::

    redux

from the command line should launch the GUI interface, and::

    redux_pipe -h

should display a brief help message for the command line interface.
