"""The staging-job hook of testing/store_fixtures.py parses its target and never leaks a credential."""

import pytest

from testing import store_fixtures


def test_iam_target_parses_host_database_user(monkeypatch):
    monkeypatch.setenv('OMI_TEST_POSTGRES_IAM', '10.0.0.5, jobstore_staging ,staging-worker@p.iam')
    assert store_fixtures.iam_target() == ('10.0.0.5', 'jobstore_staging', 'staging-worker@p.iam')


def test_iam_target_absent_or_malformed(monkeypatch):
    monkeypatch.delenv('OMI_TEST_POSTGRES_IAM', raising=False)
    assert store_fixtures.iam_target() is None
    monkeypatch.setenv('OMI_TEST_POSTGRES_IAM', 'only,two')
    with pytest.raises(store_fixtures.BackendUnavailable):
        store_fixtures.iam_target()
