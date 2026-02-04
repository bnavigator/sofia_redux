# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
Unit tests for get_wv_from_ecmwf function.
"""

from astropy.io import fits
from sofia_redux.instruments.fifi_ls.get_atran import get_wv_from_ecmwf


class TestGetWvFromEcmwf:
    """Test ECMWF water vapor retrieval and selection of file."""

    def test_successful_retrieval(self):
        """
        Test successful WV retrieval using real ECMWF data.

        Uses flight F906 data from 2022-08-25.
        ECMWF directory: /mnt/sofiadata/data/WV_ECMWF/906_FI_20220825/
        THIS WILL CHANGE TO DARUS SOON
        """
        # Create a header that matches the F906 flight
        header = fits.Header()
        header['MISSN-ID'] = '2022-08-25_FI_F906'
        header['DATE-OBS'] = '2022-08-25T09:40:20'

        # Path to real ECMWF data
        ecmwf_dir = '/mnt/sofiadata/data/WV_ECMWF'
        # This will change to a DARUS link soon

        # Call the function
        result = get_wv_from_ecmwf(header, ecmwf_dir)

        # Should return (wvz_ecmwf, wvz_fifi)
        assert result is not None, "Expected valid result, got None"

        wvz_ecmwf, wvz_fifi = result

        # Check the conversion formula: wvz_fifi = 0.34 + wvz_ecmwf * 0.55
        expected_fifi = 0.34 + wvz_ecmwf * 0.55
        assert abs(wvz_fifi - expected_fifi) < 0.001, \
            f"Conversion mismatch: expected {expected_fifi}, got {wvz_fifi}"

    def test_missing_directory(self):
        """
        Test that function returns None when ECMWF directory doesn't exist.

        This allows the calling code to fall back to header WV values.

        # WE NEED TO DISCUSS IF THIS IS WANTED (AB, CI and BS)
        # Same for when Quality Flag is bad...

        """
        header = fits.Header()
        header['MISSN-ID'] = '2022-08-25_FI_F906'
        header['DATE-OBS'] = '2022-08-25T09:40:20'

        # Non existent folder Path
        result = get_wv_from_ecmwf(header, '/nonexistentpath')
        assert result is None

        # None as directory
        result = get_wv_from_ecmwf(header, None)
        assert result is None
