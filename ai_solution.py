```python
def _clean_uid(uid):
    if not isinstance(uid, str) or not uid or len(uid) > 128:
        return None
    if any(c in uid for c in ['..', '/', '\\', '\x00']):
        return None
    return uid.strip()

def account_deletion_document(uid):
    cleaned_uid = _clean_uid(uid)
    if not cleaned_uid:
        raise ValueError("Valid uid is required for account deletion.")
    return ...  # existing implementation with cleaned_uid

def get_user_deletion_wipe_status(uid):
    cleaned_uid = _clean_uid(uid)
    if not cleaned_uid:
        return None
    return ...  # existing implementation with cleaned_uid

def read_agent_vm_migration_journals(uid):
    if not isinstance(uid, str) or not uid:
        return None
    return ...  # existing implementation

def record_late_agent_vm_cleanup(vm_name, zone):
    if not (isinstance(vm_name, str) and isinstance(zone, str) and vm_name and zone):
        return None
    return ...  # existing implementation

def adopt_legacy_late_agent_vm_cleanup(vm_name, zone):
    if not (isinstance(vm_name, str) and isinstance(zone, str) and vm_name and zone):
        return None
    return ...  # existing implementation

# Unit tests
from unittest.mock import patch
import pytest

@pytest.mark.unit
def test_clean_uid_valid():
    assert _clean_uid("valid_uid") == "valid_uid"

@pytest.mark.unit
def test_clean_uid_empty():
    assert _clean_uid("") is None

@pytest.mark.unit
def test_clean_uid_with_space():
    assert _clean_uid(" valid_uid ") == "valid_uid"

@pytest.mark.unit
def test_clean_uid_with_special_chars():
    assert _clean_uid("valid.uid") is None

@pytest.mark.unit
def test_account_deletion_document_valid():
    with patch(...) as mock:
        account_deletion_document("valid_uid")
        mock.assert_called_once()

@pytest.mark.unit
def test_account_deletion_document_invalid():
    with patch(...) as mock:
        account_deletion_document("valid.uid")
        assert mock.side_effectraised ValueError

@pytest.mark.unit
def test_get_user_deletion_wipe_status_valid():
    with patch(...) as mock:
        get_user_deletion_wipe_status("valid_uid")
        mock.assert_called_once()

@pytest.mark.unit
def test_get_user_deletion_wipe_status_invalid():
    assert get_user_deletion_wipe_status("valid.uid") is None

@pytest.mark.unit
def test_read_agent_vm_migration_journals_valid():
    with patch(...) as mock:
        read_agent_vm_migration_journals("valid_uid")
        mock.assert_called_once()

@pytest.mark.unit
def test_read_agent_vm_migration_journals_invalid():
    assert read_agent_vm_migration_journals(123) is None

@pytest.mark.unit
def test_record_late_agent_vm_cleanup_valid():
    with patch(...) as mock:
        record_late_agent_vm_cleanup("vm1", "zone1")
        mock.assert_called_once()

@pytest.mark.unit
def test_record_late_agent_vm_cleanup_invalid():
    assert record_late_agent_vm_cleanup(None, "zone1") is None

@pytest.mark.unit
def test_adopt_legacy_late_agent_vm_cleanup_valid():
    with patch(...) as mock:
        adopt_legacy_late_agent_vm_cleanup("vm1", "zone1")
        mock.assert_called_once()

@pytest.mark.unit
def test_adopt_legacy_late_agent_vm_cleanup_invalid():
    assert adopt_legacy_late_agent_vm_cleanup("vm1", None) is None
```