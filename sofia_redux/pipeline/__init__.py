# Licensed under a 3-clause BSD style license - see LICENSE.rst

from .version import version as __version__

# automodapi docs require imports here
from sofia_redux.pipeline.application import Application
from sofia_redux.pipeline.chooser import Chooser
from sofia_redux.pipeline.configuration import Configuration
from sofia_redux.pipeline.interface import Interface
from sofia_redux.pipeline.parameters import Parameters, ParameterSet
from sofia_redux.pipeline.pipe import Pipe
from sofia_redux.pipeline.reduction import Reduction
from sofia_redux.pipeline.viewer import Viewer

__all__ = ['Application', 'Chooser', 'Configuration',
           'Interface', 'Parameters', 'ParameterSet',
           'Pipe', 'Reduction', 'Viewer']
