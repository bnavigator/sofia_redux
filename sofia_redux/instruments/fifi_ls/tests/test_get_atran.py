# Licensed under a 3-clause BSD style license - see LICENSE.rst

import os
import time
from unittest.mock import patch

import numpy as np
from astropy.io import fits

from sofia_redux.instruments.fifi_ls.get_atran import (
    clear_atran_cache,
    get_atran,
    get_atran_from_cache,
    get_atran_from_darus,
    get_wv_from_ecmwf,
    store_atran_in_cache,
)


def test_atran_cache(tmpdir):

    tempdir = str(tmpdir.mkdir('test_get_atran'))
    atranfile = os.path.join(tempdir, 'test01')
    res = 100.0

    with open(atranfile, 'w') as f:
        print('this is the atran file', file=f)

    wave = unsmoothed = smoothed = np.arange(10)

    filename = 'ATRNFILE_header_value'
    store = atranfile, res, filename, wave, unsmoothed, smoothed

    clear_atran_cache()
    assert get_atran_from_cache(atranfile, res) is None
    store_atran_in_cache(*store)

    # It should be in there now
    result = get_atran_from_cache(atranfile, res)
    assert result[0] == filename

    for r in result[1:]:
        assert np.allclose(r, wave)

    # Check it's still in there
    assert get_atran_from_cache(atranfile, res) is not None

    # Check that a different resolution does not retrieve this file
    assert get_atran_from_cache(atranfile, res * 2) is None

    # Modify the file - the result should be None,
    # indicating it was removed from the file and
    # should be processed and stored again.
    time.sleep(0.5)
    with open(atranfile, 'w') as f:
        print('a modification', file=f)

    assert get_atran_from_cache(atranfile, res) is None

    # Store the data again
    store_atran_in_cache(*store)

    # Make sure it's there
    assert get_atran_from_cache(atranfile, res) is not None

    # Check clear works
    clear_atran_cache()
    assert get_atran_from_cache(atranfile, res) is None

    # Store then delete the atran file -- check that bad file
    # can't be retrieved
    store_atran_in_cache(*store)
    assert get_atran_from_cache(atranfile, res) is not None
    os.remove(atranfile)
    assert get_atran_from_cache(atranfile, res) is None


def test_filename(tmpdir, capsys, test_files):
    atranfile = tmpdir.join('test_file.fits')

    filename = test_files('scm')[0]
    header = fits.open(filename)[0].header

    # default: gets alt/za/resolution from header, no unsmoothed data
    default = get_atran(header)
    assert default is not None
    assert isinstance(default, np.ndarray)

    # provide a bad filename -- warns and gets default
    result = get_atran(header, filename=str(atranfile))
    assert np.allclose(result, default)
    capt = capsys.readouterr()
    assert 'not found; retrieving default' in capt.err

    # provide a good filename, bad file
    atranfile.write('Test data\n')
    result = get_atran(header, filename=str(atranfile))
    assert result is None
    capt = capsys.readouterr()
    assert 'Invalid data' in capt.err

    # good filename, minimum required data
    data = np.arange(100).reshape(2, 50).astype(float)
    hdul = fits.HDUList(fits.PrimaryHDU(data=data))
    hdul.writeto(str(atranfile), overwrite=True)
    result = get_atran(header, filename=str(atranfile))
    # wavelengths will match
    assert np.allclose(result[0], data[0])
    # data will be all nan
    assert np.all(np.isnan(result[1]))


def test_header(capsys, test_files):
    filename = test_files('scm')[0]
    header = fits.open(filename)[0].header

    # default
    default = get_atran(header)
    assert default is not None
    assert isinstance(default, np.ndarray)

    # bad header
    result = get_atran(['test'])
    assert result is None
    capt = capsys.readouterr()
    assert 'Invalid header' in capt.err

    # bad alti_sta -- should get end
    hdr = header.copy()
    hdr['ALTI_STA'] = -9999
    result = get_atran(hdr)
    assert np.allclose(result, default)

    # bad alti_end -- should get start
    hdr = header.copy()
    hdr['ALTI_END'] = -9999
    result = get_atran(hdr)
    assert np.allclose(result, default)

    # bad za_start -- should get end
    hdr = header.copy()
    hdr['ZA_START'] = -9999
    result = get_atran(hdr)
    assert np.allclose(result, default)

    # bad za_end -- should get start
    hdr = header.copy()
    hdr['ZA_END'] = -9999
    result = get_atran(hdr)
    assert np.allclose(result, default)


def test_header_wv(capsys, tmp_path, test_files):
    filename = test_files('scm')[0]
    header = fits.open(filename)[0].header

    # default
    default = get_atran(header)
    assert default is not None
    assert isinstance(default, np.ndarray)

    hdr = header.copy()

    # wvz_obs is used if not ecmwf
    hdr['WVZ_OBS'] = 5.0
    get_atran(hdr)
    capt = capsys.readouterr()
    assert "Alt, ZA, WV: 41.00 45.00 5.00" in capt.out

    # Fallback to 1um if it has a bad value
    hdr['WVZ_OBS'] = -9999.
    get_atran(hdr)
    capt = capsys.readouterr()
    assert "Alt, ZA, WV: 41.00 45.00 -9999.0" in capt.out
    assert "Using nearest Alt 41K, ZA 45deg, WV 1um" in capt.out


def test_atran_dir(tmp_path, capsys, test_files):
    filename = test_files('scm')[0]
    header = fits.open(filename)[0].header

    # get from cache or download from DaRUS
    default = get_atran(header)

    # specify bad directory: should get default
    result = get_atran(header, atran_dir='badval')
    assert np.allclose(result, default)
    capt = capsys.readouterr()
    assert 'Cannot find ATRAN directory' in capt.err

    # specify empty directory: should get the same as cached before
    result = get_atran(header, atran_dir=str(tmp_path))
    capt = capsys.readouterr()
    assert 'ATRAN file not found in ATRAN directory' in capt.out
    assert np.allclose(result, default)

    # put 2 files into the atran_directory
    atran_alt_dir = tmp_path / "41K"
    atran_alt_dir.mkdir()
    ref_files = [
        'atran_sdc_41K_45deg_1pwv_39deg_2nlayer_40-300mum_bt.fits',
        'atran_sdc_41K_45deg_5pwv_39deg_2nlayer_40-300mum_bt.fits',
    ]
    for pwvf in ref_files:
        cachefile = get_atran_from_darus(41, pwvf)
        (atran_alt_dir / pwvf).symlink_to(cachefile)

    for i, wv in [(0, 1.), (1, 5.)]:
        hdr = header.copy()
        # wvz_obs is used if not ecmwf
        hdr['WVZ_OBS'] = wv
        result = get_atran(hdr, atran_dir=str(tmp_path), use_ecmwf=False)
        capt = capsys.readouterr()
        assert f"Using ATRAN file: {ref_files[i]}" in capt.out
        assert 'ATRAN file not found in ATRAN directory' not in capt.out


def test_get_wv_from_ecmwf():
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

    wvz_ecmwf, wvz_fifi, wv_formula, filename = get_wv_from_ecmwf(
        header, ecmwf_dir)

    # Check the conversion formula: wvz_fifi = 0.34 + wvz_ecmwf * 0.55
    expected_fifi = 0.34 + wvz_ecmwf * 0.55
    assert abs(wvz_fifi - expected_fifi) < 0.001, \
        f"Conversion mismatch: expected {expected_fifi}, got {wvz_fifi}"


def test_missing_directory(caplog):
    """
    Test that function returns None when ECMWF data is unavailable

    When the local directory is missing, the function falls back to DaRUS.
    None is only returned if both the local directory and DaRUS fail.
    """
    header = fits.Header()
    header['MISSN-ID'] = '2022-08-25_FI_F906'
    header['DATE-OBS'] = '2022-08-25T09:40:20'

    darus_fail = patch(
        'sofia_redux.instruments.fifi_ls.get_atran.get_ecmwf_from_darus',
        side_effect=FileNotFoundError("DaRUS unavailable"))

    with darus_fail:
        # Non-existent directory: logs warning - falls back to DaRUS
        # DaRUS fails too then None
        result = get_wv_from_ecmwf(header, '/nonexistentpath')
        assert result is None
        assert "ECMWF directory not found" in caplog.text

        # None directory: goes straight to DaRUS, DaRUS fails then None
        result = get_wv_from_ecmwf(header, None)
        assert result is None
