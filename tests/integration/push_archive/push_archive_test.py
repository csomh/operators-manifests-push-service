#
# Copyright (C) 2019 Red Hat, Inc
# see the LICENSE file for license
#

import shutil
import pytest
import requests
from tests.integration.constants import TEST_NAMESPACE, TEST_PACKAGE


def test_initial_upload(omps, quay, tmp_path):
    """
    When uploading an archive to a repository which is empty,
    and no version is specified during the upload
    then a new release is created with version 1.0.0
    """

    # Make sure there TEST_PACKAGE operator is empty.
    releases = [r['release'] for r in
                quay.get_releases(TEST_NAMESPACE, TEST_PACKAGE)]
    quay.delete_releases('/'.join([TEST_NAMESPACE, TEST_PACKAGE]), releases)

    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive).json()

    assert response['organization'] == TEST_NAMESPACE
    assert response['repo'] == TEST_PACKAGE
    assert response['version'] == '1.0.0'

    releases = quay.get_releases(TEST_NAMESPACE, TEST_PACKAGE)
    assert releases
    assert len(releases) == 1
    assert releases[0]['release'] == '1.0.0'


def test_upload_with_version(omps, quay, tmp_path):
    """
    When specifying the version for an upload,
    then the release is created with the version specified.
    """
    version = '4.3.2'

    # Make sure the version to be uploaded does not exist.
    if quay.get_release(TEST_NAMESPACE, TEST_PACKAGE, version):
        quay.delete_releases('/'.join([TEST_NAMESPACE, TEST_PACKAGE]), [version])

    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, version=version, archive=archive).json()

    assert response['organization'] == TEST_NAMESPACE
    assert response['repo'] == TEST_PACKAGE
    assert response['version'] == version

    assert quay.get_release(TEST_NAMESPACE, TEST_PACKAGE, version)


def test_increment_version(omps, quay, tmp_path):
    """
    When no version is specified, and there already are some releases in
        the package,
    then the major bit of the semantically highest version is incremented,
        and used as the version of the new release.
    """
    expected_releases = set(['1.0.0', '4.3.2'])
    next_release = '5.0.0'

    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')

    # Make sure that only the expected releases are present
    package_releases = set(release['release'] for release in
                           quay.get_releases(TEST_NAMESPACE, TEST_PACKAGE))
    for release in expected_releases - package_releases:
        omps.upload(organization=TEST_NAMESPACE,
                    repo=TEST_PACKAGE, version=release, archive=archive)

    quay.delete_releases('/'.join([TEST_NAMESPACE, TEST_PACKAGE]),
                         package_releases - expected_releases)

    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive).json()

    assert response['organization'] == TEST_NAMESPACE
    assert response['repo'] == TEST_PACKAGE
    assert response['version'] == next_release

    assert quay.get_release(TEST_NAMESPACE, TEST_PACKAGE, next_release)


def test_version_exists(omps, quay, tmp_path):
    """
    When the version already exists in the package,
    then creating the new release fails.
    """
    release_used = '5.0.0'

    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')

    if not quay.get_release(TEST_NAMESPACE, TEST_PACKAGE, release_used):
        omps.upload(organization=TEST_NAMESPACE,
                    repo=TEST_PACKAGE, version=release_used, archive=archive)

    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, version=release_used, archive=archive)

    assert response.status_code == requests.codes.server_error
    assert response.json()['error'] == 'QuayCourierError'
    assert 'Failed to push' in response.json()['message']


@pytest.mark.parametrize("version", [
    ('1.0.0.1'),
    ('1.0.0-2'),
    ('1.0.02'),
    ('1.a.2'),
    ('1.1'),
])
def test_incorrect_version(omps, tmp_path, version):
    """
    When the version specified does not meet OMPS requirements,
    then the push fails.
    """
    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, version=version, archive=archive)

    assert response.status_code == requests.codes.bad_request
    assert response.json()['error'] == 'OMPSInvalidVersionFormat'
    assert version in response.json()['message']


def test_filetype_not_supported(omps, tmpdir):
    """
    If the file uploaded is not a ZIP file,
    then the push fails.
    """
    archive = tmpdir.join('not-a-zip.zip').ensure()
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive)

    assert response.status_code == requests.codes.bad_request
    assert response.json()['error'] == 'OMPSUploadedFileError'
    assert 'not a zip file' in response.json()['message']


def test_file_extension_not_zip(omps, tmpdir):
    """
    If the extension of the file is not '.zip',
    then the push fails.
    """
    archive = tmpdir.join('archive.tar.gz').ensure()
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive)

    assert response.status_code == requests.codes.bad_request
    assert response.json()['error'] == 'OMPSUploadedFileError'
    assert 'file extension' in response.json()['message']


def test_no_file_field(omps, tmp_path):
    """
    The ZIP file uploaded must be assigned to the 'file' field.
    """
    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive, field='archive')

    assert response.status_code == requests.codes.bad_request
    assert response.json()['error'] == 'OMPSExpectedFileError'
    assert 'No field "file"' in response.json()['message']


def test_organization_unaccessible_in_quay(omps, tmp_path):
    """
    Push fails, if the organization is not configured in OMPS.
    """
    organization = 'martian-green-operators'
    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/artifacts/')
    response = omps.upload(organization=organization,
                           repo=TEST_PACKAGE, archive=archive)

    assert response.status_code == requests.codes.internal_server_error
    assert response.json()['error'] == 'QuayPackageError'
    assert 'Cannot retrieve information about package' in response.json()['message']


def test_upload_password_protected_zip(omps):
    """
    Push fails, if the ZIP-file is password-protected.
    """
    archive = 'tests/integration/push_archive/encrypted.zip'
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive)

    assert response.status_code == requests.codes.bad_request
    assert response.json()['error'] == 'OMPSUploadedFileError'
    assert 'is encrypted' in response.json()['message']


def test_upload_invalid_artifact(omps, tmp_path):
    """
    Push fails, if the artifact does not pass quay-courier validation.
    """
    archive = shutil.make_archive(tmp_path / 'archive', 'zip',
                                  'tests/integration/push_archive/invalid_artifacts/')
    response = omps.upload(organization=TEST_NAMESPACE,
                           repo=TEST_PACKAGE, archive=archive)

    assert response.status_code == requests.codes.internal_server_error
    assert response.json()['error'] == 'QuayCourierError'
    assert 'bundle is invalid' in response.json()['message']