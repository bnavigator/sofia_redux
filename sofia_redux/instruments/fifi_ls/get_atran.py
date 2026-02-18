# Licensed under a 3-clause BSD style license - see LICENSE.rst

import glob
import os
import re
from pathlib import Path

from astropy import log
from astropy.io import fits
from astropy.time import Time
import numpy as np

from sofia_redux.instruments import fifi_ls
from sofia_redux.instruments.fifi_ls.get_resolution import get_resolution
from sofia_redux.toolkit.utilities import goodfile, gethdul, hdinsert
from sofia_redux.spectroscopy.smoothres import smoothres


__all__ = ['clear_atran_cache', 'get_atran_from_cache',
           'store_atran_in_cache', 'get_atran', 'get_atran_interpolated',
           'clear_ecmwf_cache']

__atran_cache = {}
__ecmwf_cache = {}


def clear_atran_cache():
    """
    Clear all data from the atran cache.
    """
    global __atran_cache
    __atran_cache = {}


def clear_ecmwf_cache():
    """
    Clear all data from the ECMWF cache.
    """
    global __ecmwf_cache
    __ecmwf_cache = {}


def get_atran_from_cache(atranfile, resolution):
    """
    Retrieves atmospheric transmission data from the atran cache.

    Checks to see if the file still exists, can be read, and has not
    been altered since last time.  If the file has changed, it will be
    deleted from the cache so that it can be re-read.

    Parameters
    ----------
    atranfile : str
        File path to the atran file
    resolution : float
        Spectral resolution used for smoothing.

    Returns
    -------
    tuple
        filename : str
            Used to update ATRNFILE in FITS headers.
        wave : numpy.ndarray
            (nwave,) array of wavelengths.
        unsmoothed : numpy.ndarray
            (nwave,) array containing the atran data from file
        smoothed : numpy.ndarray
            (nwave,) array containing the smoothed atran data
    """
    global __atran_cache

    key = atranfile, int(resolution)

    if key not in __atran_cache:
        return

    if not goodfile(atranfile):
        try:
            del __atran_cache[key]
        except KeyError:   # pragma: no cover
            # could happen in race conditions, working in parallel
            pass
        return

    modtime = str(os.path.getmtime(atranfile))
    if modtime not in __atran_cache.get(key, {}):
        return

    log.debug(f'Retrieving ATRAN data from cache '
              f'({key[0]}, resolution {key[1]})')
    return __atran_cache.get(key, {}).get(modtime)


def store_atran_in_cache(atranfile, resolution, filename, wave,
                         unsmoothed, smoothed):
    """
    Store atran data in the atran cache.

    Parameters
    ----------
    atranfile : str
        File path to the atran file
    resolution : float
        Spectral resolution used for smoothing.
    filename : str
        Used to update ATRNFILE in FITS headers.
    wave : numpy.ndarray
        (nwave,) array of wavelengths.
    unsmoothed : numpy.ndarray
        (nwave,) array containing the atran data from file
    smoothed : numpy.ndarray
        (nwave,) array containing the smoothed atran data

    """
    global __atran_cache
    key = atranfile, int(resolution)
    log.debug(f'Storing ATRAN data in cache '
              f'({key[0]}, resolution {key[1]})')
    __atran_cache[key] = {}
    modtime = str(os.path.getmtime(atranfile))
    __atran_cache[key][modtime] = (
        filename, wave, unsmoothed, smoothed)


def get_atran_data(filename, resolution, atran_dir=None):
    """Get ATRAN data for given filename.

    Lookup Order:
        1. Memory cache if already read in
        2. ATRAN directory if provided
        3. DaRUS, SOFIA Astronomy Dataverse

    Parameters
    ----------
    filename : str
        Name of the ATRAN file to be read, also used for cache key
    resolution : float
        Spectral resolution to which ATRAN data should be smoothed.
    atran_dir : str
        Path to a directory containing ATRAN reference FITS files,
        comes from the recipe configuration.

    Returns
    -------
    atranfile : str
        The basename of the ATRAN file
    wave : numpy.ndarray
        (nwave,) array of wavelengths
    unsmoothed : numpy.ndarray
        (nwave,) array containing the transmission spectrum from file
    smoothed : numpy.ndarray
        (nwave,) array containing the smoothed transmission spectrum
    """
    atran_data = get_atran_from_cache(filename, resolution)

    if atran_data is not None:
        return atran_data

    if atran_dir is not None:
        if not os.path.isdir(str(atran_dir)):
            log.warning(f'Cannot find ATRAN directory: {atran_dir}')
            log.warning('Using default ATRAN set.')
            atran_dir = None
    if atran_dir is None:
        atran_dir = os.path.join(os.path.dirname(fifi_ls.__file__),
                                'data', 'atran_files')

    atranfile = os.path.basename(filename)

    hdul = gethdul(os.path.join(atran_dir, filename), verbose=True)
    if hdul is None or hdul[0].data is None:
        log.error(f'Invalid data in ATRAN file {filename}')
        return


    if len(hdul) < 2 or hdul[1].header['CONTENT'] != "ATRAN_SDC Model":
        log.warning("Did not find ATRAN SDC model data in FITS BinTableHDU "
                    f"in {filename}. Falling back to old format.")
        wave = hdul[0].data[0, :]
        unsmoothed = hdul[0].data[1, :]
    else:
        data_rec = hdul[1]
        wave = data_rec['wavelength']
        unsmoothed = data_rec['transmission']

    smoothed = smoothres(wave, unsmoothed, resolution)
    store_atran_in_cache(filename, resolution,
                         atranfile, wave, unsmoothed, smoothed)
    return (atranfile, wave, unsmoothed, smoothed)


def get_ecmwf_from_cache(ecmwf_file):
    """Return cached ECMWF arrays for ecmwf_file, or None if not cached."""
    global __ecmwf_cache
    return __ecmwf_cache.get(str(ecmwf_file))


def store_ecmwf_in_cache(ecmwf_file, unixtime, pwv, posconst, posjump):
    """Store ECMWF arrays in cache keyed by file path."""
    global __ecmwf_cache
    __ecmwf_cache[str(ecmwf_file)] = (unixtime, pwv, posconst, posjump)


def get_wv_from_ecmwf(header, ecmwf_dir):
    """
    Get water vapor value from ECMWF reanalysis data.

    ECMWF files are stored as binary table FITS files named
    <flight>_<instrument>_<YYYYMMDD>_pwv.fits in ecmwf_dir. This function
    finds the right file and extracts the water vapor value closest
    to the observation time.

    Parameters
    ----------
    header : fits.Header
        FITS header containing MISSN-ID and DATE-OBS keywords.
    ecmwf_dir : str
        Path to directory containing ECMWF FITS files.

    Returns
    ----------
    tuple or None
        Tuple of (wvz_ecmwf, wvz_fifi) where wvz_ecmwf is the raw ECMWF
        water vapor value and wvz_fifi is the converted FIFI-LS scale
        value. Returns None if ECMWF data could not be retrieved.
    """
    if ecmwf_dir is None or not os.path.isdir(str(ecmwf_dir)):
        log.warning(f'ECMWF directory not found: {ecmwf_dir}')
        return None

    # Construct mission ID path from header
    missn_id = header.get('MISSN-ID', '')
    if not missn_id:
        log.warning('MISSN-ID not found in header')
        return None

    # Format: last 3 chars + chars 10-14 + first 10 chars (no dashes)
    # Example: "2022-01-15_FI_F855" -> "855_FI_20220115"
    try:
        ecmwf_mission_id = (missn_id[-3:] + missn_id[10:14]
                           + missn_id[:10].replace('-', ''))
    except (IndexError, TypeError):
        log.warning(f'Could not get MISSN-ID: {missn_id}')
        return None

    # Get observation time
    date_obs = header.get('DATE-OBS', '')
    if not date_obs:
        log.warning('DATE-OBS not found in header')
        return None

    try:
        obs_time_unix = Time(date_obs).unix
    except Exception as e:
        log.warning(f'Could not get DATE-OBS: {date_obs} ({e})')
        return None

    # Search for matching ECMWF file: <mission_id>_pwv.fits in ecmwf_dir
    ecmwf_file = Path(ecmwf_dir, f'{ecmwf_mission_id}_pwv.fits')
    if not ecmwf_file.is_file():
        log.debug(f'ECMWF file not found: {ecmwf_file}')
        return None

    wvz_ecmwf = None
    wvz_fifi = None
    try:
        cached = get_ecmwf_from_cache(ecmwf_file)
        if cached is not None:
            unixtime, pwv, posconst, posjump = cached
            log.debug(f'Retrieved ECMWF data from cache: {ecmwf_file}')
        else:
            with fits.open(ecmwf_file) as ecmwf_hdul:
                data = ecmwf_hdul['DATA'].data
                unixtime = data['unixtime'].copy()
                pwv = data['pwv'].copy()
                posconst = data['posconst'].copy()
                posjump = data['posjump'].copy()
            store_ecmwf_in_cache(ecmwf_file, unixtime, pwv, posconst, posjump)
            log.debug(f'Stored ECMWF data in cache: {ecmwf_file}')

        # Check if observation time is within the data range
        if unixtime[0] < obs_time_unix < unixtime[-1]:
            # Binary search for closest time index (unixtime is sorted)
            ecmwf_idx = np.searchsorted(unixtime, obs_time_unix)
            # Check quality flags (posconst and posjump should be 0)
            if posconst[ecmwf_idx] == 0 and posjump[ecmwf_idx] == 0:
                wvz_ecmwf = float(pwv[ecmwf_idx])
                # Convert to FIFI-LS scale
                wv_offset, wv_slope = 0.34, 0.55
                wvz_fifi = wv_offset + wvz_ecmwf * wv_slope
                wv_formula = (f'WVZ_FIFI = {wv_offset} '
                              f'+ WVZ_ECMW * {wv_slope}')
                log.debug(f'ECMWF WV: {wvz_ecmwf:.2f} -> '
                          f'FIFI-LS WV: {wvz_fifi:.2f} '
                          f'({wv_formula})')
    except Exception as e:
        log.debug(f'Errror reading ECMWF file {ecmwf_file}: {e}')

    if wvz_fifi is None:
        log.warning('No valid ECMWF data found for this observation')
        return None

    return (wvz_ecmwf, wvz_fifi, wv_formula, ecmwf_file.name)


def get_atran(header, resolution=None, filename=None,
              get_unsmoothed=False, atran_dir=None):
    """
    Retrieve reference atmospheric transmission data.

    ATRAN files in the data/atran_files directory should be named
    according to description in https://doi.org/10.18419/DARUS-5705:

        atran_sdc_[alt]K_[za]deg_[wv]pwv_39deg_2nlayer_[wmin]-[wmax]mum_bt.fits

    "39deg" denotes the Ozone model; "2nlayer" denotes the number
    of atmospheric layers used in ATRAN. Both of these are currently
    fixed.

    The FIFI-LS files have a wavelength range of 40 to 300 microns.

    For example, the file generated for altitude of 41,000 feet,
    ZA of 45 degrees, and wavelengths between 40 and 300 microns
    should be named:

        atran_sdc_41K_45deg_10pwv_39deg_2nlayer_40-300mum_bt.fits

    The procedure is:

        1. Identify ATRAN file by ZA, Altitude, and WV, unless override is
           provided. Water vapor values are retrieved from WVZ_OBS in the
           header or from ECMWF data.
        2. Read ATRAN data from file and smooth to expected spectral
           resolution.
        3. Return transmission array.

    Parameters
    ----------
    header : fits.Header
        ATRNFILE keyword is written to the provided FITS header,
        containing the name of the ATRAN file used.
    resolution : float, optional
        Spectral resolution to which ATRAN data should be smoothed.
    filename : str, optional
        Atmospheric transmission file to be used.  If not provided,
        a default file will be retrieved from the data/atran_files
        directory if provided or downloaded from the SOFIA Astronomy
        Dataverse
        (https://darus.uni-stuttgart.de/dataverse/irs-sofia-ad).
        The file with the closest matching ZA, Altitude and PWV
        to the input data will be used.  If override file
        is provided, it should be a FITS image file containing
        wavelength and transmission data without smoothing.
    get_unsmoothed : bool, optional
        If True, return the unsmoothed atran data in addition to the
        smoothed.
    atran_dir : str, optional
        Path to a directory containing ATRAN reference FITS files.
        If not provided, the default set of files packaged with the
        pipeline will be used.

    Returns
    -------
    numpy.ndarray
        Filename of the atmospheric transmission file used and a
        (2, nw) array containing wavelengths and (optionally
        smoothed) transmission data.
    """
    if not isinstance(header, fits.Header):
        log.error('Invalid header')
        return
    if resolution is None:
        log.warning('Getting default resolution from G_WAVE in header')
        resolution = get_resolution(header)

    if filename is None:
        za_start = float(header.get('ZA_START', 0))
        za_end = float(header.get('ZA_END', 0))
        if za_start > 0 >= za_end:
            za = za_start
        elif za_end > 0 >= za_start:
            za = za_end
        else:
            za = 0.5 * (za_start + za_end)

        alt_start = float(header.get('ALTI_STA', 0))
        alt_end = float(header.get('ALTI_END', 0))
        if alt_start > 0 >= alt_end:
            alt = alt_start
        elif alt_end > 0 >= alt_start:
            alt = alt_end
        else:
            alt = 0.5 * (alt_start + alt_end)
        alt /= 1000

        wv_obs = float(header.get('WVZ_OBS', 0))
        wv = wv_obs

        log.debug(f'Alt, ZA, WV: {alt:.2f} {za:.2f} {wv:.2f}')

        # these are currently not variable
        O3_model = '39deg'
        atran_layers = '2nlayer'

        # see https://doi.org/10.18419/DARUS-5705 for naming convention.
        filename = (
            "atran_sdc"
            f"_{round(alt)}K_{za}deg_{wv}pwv"
            f"_{O3_model}_{atran_layers}_40-300mum_bt.fits")

        log.debug('Using nearest Alt/ZA/WV')

    # Read the atran data from cache if possible
    log.debug(f'Using ATRAN file: {filename}')

    atran_data = get_atran_data(filename, resolution, atran_dir)
    atranfile, wave, unsmoothed, smoothed = atran_data

    hdinsert(header, 'ATRNFILE', atranfile)
    if not get_unsmoothed:
        return np.vstack((wave, smoothed))
    else:
        return (np.vstack((wave, smoothed)),
                np.vstack((wave, unsmoothed)))


def get_atran_interpolated(header, resolution=None,
                          get_unsmoothed=False,
                          atran_dir=None, use_ecmwf=False,
                          ecmwf_dir=None):

    if not isinstance(header, fits.Header):
        log.error('Invalid header')
        return

    if resolution is None:
        log.warning('Getting default resolution from G_WAVE in header')
        resolution = get_resolution(header)

    # get ZA
    za_start = float(header.get('ZA_START', 0))
    za_end = float(header.get('ZA_END', 0))
    if za_start > 0 >= za_end:
        za = za_start
    elif za_end > 0 >= za_start:
        za = za_end
    else:
        za = 0.5 * (za_start + za_end)

    # get altitude in thousands feet
    alt_start = float(header.get('ALTI_STA', 0))
    alt_end = float(header.get('ALTI_END', 0))
    if alt_start > 0 >= alt_end:
        alt = alt_start
    elif alt_end > 0 >= alt_start:
        alt = alt_end
    else:
        alt = 0.5 * (alt_start + alt_end)
    alt /= 1000

    # get water vapor
    wv = None
    wvz_ecmwf = None
    wvz_fifi = None
    wv_formula = None
    wv_source = 'HEADER'

    if use_ecmwf:
        # Try to get water vapor from ECMWF reanalysis data
        ecmwf_result = get_wv_from_ecmwf(header, ecmwf_dir)
        if ecmwf_result is not None:
            wvz_ecmwf, wvz_fifi, wv_formula, wv_file = ecmwf_result
            wv = wvz_fifi
            wv_source = 'ECMWF'
            log.info(f'Using ECMWF water vapor: {wv:.2f}')

    if wv is None:
        # Fall back to header WVZ_OBS value
        wv_obs = float(header.get('WVZ_OBS', 0))
        wv = wv_obs
        if use_ecmwf and wv <= 0:
            log.warning('No valid water vapor value found')

    za_values = list(range(30,75,5))
    wv_values = [1, 2, 3, 4, 5, 6, 7,
                8, 9, 10, 11, 12, 13,
                14, 15, 16, 17, 18, 20,
                22, 25, 27, 30, 32, 35,
                37, 40, 45, 50]

    # clip values to atran data range
    if not za_values[-1] >= za >= za_values[0]:
        log.warning('za={} outside of available ATRAN data.'.format(za))
        za = np.clip(za, a_min=za_values[0], a_max=za_values[-1])
        log.warning('Setting zenith angle to {} deg'.format(za))
        za_high, za_low = za_values[-1], za_values[-2]
    else:
        za_high, za_low = np.inf, np.inf

    if not wv_values[-1] >= wv >= wv_values[0]:
        log.warning('wv={} outside of available ATRAN data.'.format(wv))
        wv = np.clip(wv, a_min=wv_values[0], a_max=wv_values[-1])
        log.warning('Setting water vapor to {} um'.format(wv))
        wv_high, wv_low = wv_values[-1], wv_values[-2]
    else:
        wv_high, wv_low = np.inf, np.inf

    if not 45 >= alt >= 38:
        log.warning('alt={} outside of available ATRAN data.'.format(alt))
        alt = np.clip(alt, a_min=38, a_max=45)
        log.warning('Setting altitude to {}K ft'.format(round(alt)))

    log.debug(f'Alt, ZA, WV: {alt:.2f} {za:.2f} {wv:.2f}')

    # find the higher and lower boundaries
    for i, w in enumerate(wv_values):
        if w > wv:
            wv_high = w
            wv_low = wv_values[i-1]
            break

    for i, z in enumerate(za_values):
        if z > za:
            za_high = z
            za_low = za_values[i-1]
            break


    # these are currently not variable
    O3_model = '39deg'
    atran_layers = '2nlayer'

    # load all files
    atran_data = {}
    atrnfile_fits_keyword = ''
    for key, _za, _wv in (("za1_wv1",  za_low, wv_low),
                          ("za1_wv2",  za_low, wv_high),
                          ("za2_wv1",  za_high, wv_low),
                          ("za2_wv2",  za_high, wv_high)):
        # see https://doi.org/10.18419/DARUS-5705 for naming convention.
        filename = (
            "atran_sdc"
            f"_{round(alt)}K_{_za}deg_{_wv}pwv"
            f"_{O3_model}_{atran_layers}_40-300mum_bt.fits")

        single_atran_data = get_atran_data(filename, resolution, atran_dir)
        atran_data[key] = (single_atran_data, _za, _wv)
        atrnfile_fits_keyword += filename + ', '

    # interpolate za for two pwv
    za1_za2_wv1 = interpolate_two_atran_files(
        atran_data["za1_wv1"], atran_data["za2_wv1"], za, 0)
    za1_za2_wv2 = interpolate_two_atran_files(
        atran_data["za1_wv2"], atran_data["za2_wv2"], za, 0)
    # interpolate WV and hold ZA
    interpolated = interpolate_two_atran_files(za1_za2_wv1, za1_za2_wv2, wv, 1)

    wave = interpolated[0][1]
    unsmoothed = interpolated[0][2]
    smoothed = smoothres(wave, unsmoothed, resolution)

    hdinsert(header, 'ATRNFILE', atrnfile_fits_keyword[:-2])

    # Add water vapor source and values to header
    hdinsert(header, 'WV_SRC', wv_source,
             comment='Source of water vapor value (ECMWF or HEADER)')
    hdinsert(header, 'WV_USED', round(wv, 2),
             comment='[um] Water vapor used for ATRAN selection')
    if wvz_ecmwf is not None:
        hdinsert(header, 'WVZ_ECMW', round(wvz_ecmwf, 2),
                 comment='[um] Raw ECMWF WV (before FIFI-LS conversion)')
        hdinsert(header, 'WV_FORM', wv_formula,
                 comment='Formula used to convert ECMWF WV to FIFI-LS scale')
        hdinsert(header, 'WV_FILE', wv_file,
                 comment='ECMWF PWV file used')

    if not get_unsmoothed:
        return np.vstack((wave, smoothed))
    else:
        return (np.vstack((wave, smoothed)),
                np.vstack((wave, unsmoothed)))


def interpolate_two_atran_files(atran_data1, atran_data2, des_val, itype=0):
    """
    Interpolate data from two atran files.

    Parameters
    ----------
    atran_data1, atran_data2 : tuple
        ((filename, wave, unsmoothed, smoothed), za, wv)
    des_val : float
        The value to be interpolated for. Can be zenith angle (ZA) or water
        vapor (WV)
    itype: int
        0 for ZA
        1 for WV

    Returns
    -------
    interpolated_atran_data: tuple
        same nested tuple format as input parameters
        (("", wave, unsmoothed, None), za, wv)
    """
    if not np.allclose(atran_data1[0][1], atran_data2[0][1]):
        raise ValueError("Incompatible atran wavelengths to interpolate")

    dy = atran_data2[0][2] - atran_data1[0][2]

    if itype == 0:
        # interpolating zenith angle
        dx = atran_data2[1] - atran_data1[1]
        t = dy/dx
        data_int = atran_data1[0][2] + t * (des_val - atran_data1[1])
        za = des_val
        wv = atran_data1[2]
    elif itype == 1:
        # interpolating water vapor
        dx = atran_data2[2] - atran_data1[2]
        t = dy/dx
        data_int = atran_data1[0][2] + t * (des_val - atran_data1[2])
        za = atran_data1[1]
        wv = des_val
    else:
        raise TypeError("itype has to be either 0 (ZA) or 1 (WV)")

    interpolated_atran_data0 = ("", atran_data1[0][1], data_int, None)
    return (interpolated_atran_data0, za, wv)
