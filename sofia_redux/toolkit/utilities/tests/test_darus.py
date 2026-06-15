# Licensed under a 3-clause BSD style license - see LICENSE.rst

import pytest
import requests

from sofia_redux.toolkit.utilities import darus


@pytest.fixture(autouse=True)
def clear_listing_cache():
    #reset cache before each test.
    darus.__dict__['__darus_files_in_ds'].clear()
    yield
    darus.__dict__['__darus_files_in_ds'].clear()


def _mock_listing(mocker, files):
    """Patch requests.get to return a DaRUS listing for `files`."""
    response = mocker.MagicMock()
    response.json.return_value = {
        'data': {'latestVersion': {'files': files}}}
    return mocker.patch.object(darus.requests, 'get', return_value=response)


def test_get_file_success(mocker):
    # first file does not match so it continues
    # unil it matches.
    files = [
        {'label': 'other.fits', 'dataFile': {'id': 1}},
        {'label': 'target.fits', 'dataFile': {'id': 42}},
    ]
    get = _mock_listing(mocker, files)
    download = mocker.patch.object(darus, 'download_file',
                                   return_value='/cache/target.fits')

    result = darus.get_file_from_darus('10.18419/DARUS-TEST', 'target.fits')

    assert result == '/cache/target.fits'
    # the listing is requested for the right dataset DOI
    get.assert_called_once()
    assert get.call_args.args[0] == \
        f'{darus.DARUS_URL_BASE}/api/datasets/:persistentId'
    assert get.call_args.kwargs['params'] == \
        {'persistentId': 'doi:10.18419/DARUS-TEST'}
    # the download URL is built from the matched file id (42)
    download.assert_called_once_with(
        f'{darus.DARUS_URL_BASE}/api/access/datafile/42',
        cache=True, pkgname='sofia_redux')


def test_get_file_not_found(mocker):
    files = [{'label': 'a.fits', 'dataFile': {'id': 1}}]
    _mock_listing(mocker, files)
    download = mocker.patch.object(darus, 'download_file')

    with pytest.raises(FileNotFoundError, match='missing.fits'):
        darus.get_file_from_darus('10.18419/DARUS-TEST', 'missing.fits')

    # nothing is downloaded when the file is not in the dataset
    download.assert_not_called()


def test_listing_is_cached(mocker):
    files = [{'label': 'a.fits', 'dataFile': {'id': 1}}]
    get = _mock_listing(mocker, files)
    mocker.patch.object(darus, 'download_file', return_value='/cache/a.fits')

    doi = '10.18419/DARUS-CACHE'
    darus.get_file_from_darus(doi, 'a.fits')
    darus.get_file_from_darus(doi, 'a.fits')

    # the dataset listing is fetched only once for repeated calls
    get.assert_called_once()


def test_http_error(mocker):
    response = mocker.MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError('500')
    mocker.patch.object(darus.requests, 'get', return_value=response)
    download = mocker.patch.object(darus, 'download_file')

    with pytest.raises(requests.HTTPError):
        darus.get_file_from_darus('10.18419/DARUS-BAD', 'a.fits')

    download.assert_not_called()
