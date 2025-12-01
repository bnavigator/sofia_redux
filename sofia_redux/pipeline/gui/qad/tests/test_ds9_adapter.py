# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Tests for the DS9 Adapter class."""

import pytest

from sofia_redux.pipeline.gui.qad.ds9_adapter import sanitize_path_ds9


@pytest.mark.parametrize(
    'path, expected',
    [pytest.param("/home/user/data dir/image 1.fits",
                  "/home/user/data\\ dir/image\\ 1.fits",
                  id="posix"),
     pytest.param("C:/Users/data dir/image 2.fits",
                  "C:/Users/data\\ dir/image\\ 2.fits",
                  id="windows /"),
     pytest.param("C:\\Users\\data dir\\image 3.fits",
                  "C:/Users/data\\ dir/image\\ 3.fits",
                  id="windows \\"),
    ]
)
def test_sanitize_path_ds9(path, expected):
    assert sanitize_path_ds9(path) == expected
