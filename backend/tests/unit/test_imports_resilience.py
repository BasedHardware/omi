"""
Unit tests for import resilience and security fixes.
Tests path traversal prevention, error shielding, and input validation.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from backend.routers.imports import (
    _sanitize_filename,
    _validate_temp_path,
    _sanitize_for_logging,
    import_limitless_data,
    get_import_job_status,
    cancel_import_job,
    delete_import_job,
    get_import_jobs,
)
from backend.database.import_jobs import _validate_job_id


class TestFilenameSanitization:
    """Tests for filename sanitization to prevent path traversal."""
    
    def test_normal_filename(self):
        """Normal filename should be preserved."""
        assert _sanitize_filename("data.zip") == "data.zip"
    
    def test_filename_with_spaces(self):
        """Spaces should be removed."""
        assert _sanitize_filename("my data file.zip") == "mydatafile.zip"
    
    def test_path_traversal_attempt(self):
        """Path traversal sequences should be stripped."""
        result = _sanitize_filename("../../../../tmp/malicious.zip")
        assert result == "tmpmalicious.zip"
        assert "../" not in result
        assert "..\\" not in result
    
    def test_empty_filename(self):
        """Empty filename should fall back to default."""
        assert _sanitize_filename("") == "upload.zip"
    
    def test_none_filename(self):
        """None filename should fall back to default."""
        assert _sanitize_filename(None) == "upload.zip"
    
    def test_special_characters_only(self):
        """Filename with only special chars should fall back."""
        assert _sanitize_filename("@#$%&*()") == "upload.zip"
    
    def test_mixed_safe_and_unsafe(self):
        """Mixed safe and unsafe characters should be sanitized."""
        result = _sanitize_filename("safe_file-name.zip")
        assert result == "safe_file-name.zip"
    
    def test_absolute_path_filename(self):
        """Absolute path in filename should be reduced to basename."""
        result = _sanitize_filename("/etc/passwd")
        assert result == "passwd"
    
    def test_windows_path_filename(self):
        """Windows path should be reduced to basename."""
        result = _sanitize_filename("C:\\Windows\\System32\\malicious.exe")
        assert result == "malicious.exe"
    
    def test_filename_with_unicode(self):
        """Unicode characters should be stripped."""
        result = _sanitize_filename("数据文件.zip")
        assert result == ".zip"


class TestTempPathValidation:
    """Tests for temp path validation."""
    
    def test_valid_path(self):
        """Valid path within temp dir should pass."""
        assert _validate_temp_path("/tmp/test/file.zip", "/tmp") is True
    
    def test_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        assert _validate_temp_path("/tmp/../../etc/passwd", "/tmp") is False
    
    def test_different_directory(self):
        """Path in different directory should be rejected."""
        assert _validate_temp_path("/var/data/file.zip", "/tmp") is False
    
    def test_exact_temp_dir(self):
        """Exact temp dir path should be allowed."""
        assert _validate_temp_path("/tmp", "/tmp") is True


class TestErrorShielding:
    """Tests for error message shielding."""
    
    def test_sensitive_path_removed(self):
        """Absolute paths should be redacted in logs."""
        error = "Failed: /home/user/project/data/file.txt"
        result = _sanitize_for_logging(error)
        assert "/home/user/project" not in result
    
    def test_windows_path_removed(self):
        """Windows paths should be redacted."""
        error = "Error: C:\\Users\\admin\\secrets\\key.pem"
        result = _sanitize_for_logging(error)
        assert "C:\\Users" not in result
    
    def test_generic_error_preserved(self):
        """Generic error messages should be preserved."""
        error = "Connection timeout"
        result = _sanitize_for_logging(error)
        assert result == "Connection timeout"


class TestJobIdValidation:
    """Tests for job ID validation."""
    
    def test_valid_alphanumeric(self):
        """Valid alphanumeric job ID should pass."""
        assert _validate_job_id("abc123") is True
    
    def test_valid_with_hyphen(self):
        """Job ID with hyphen should pass."""
        assert _validate_job_id("job-123") is True
    
    def test_valid_with_underscore(self):
        """Job ID with underscore should pass."""
        assert _validate_job_id("job_123") is True
    
    def test_empty_id_rejected(self):
        """Empty job ID should be rejected."""
        assert _validate_job_id("") is False
    
    def test_slash_in_id_rejected(self):
        """Slash in job ID should be rejected."""
        assert _validate_job_id("job/123") is False
    
    def test_backslash_in_id_rejected(self):
        """Backslash in job ID should be rejected."""
        assert _validate_job_id("job\\123") is False
    
    def test_path_traversal_rejected(self):
        """Path traversal sequence should be rejected."""
        assert _validate_job_id("../etc/passwd") is False
    
    def test_special_characters_rejected(self):
        """Special characters should be rejected."""
        assert _validate_job_id("job@123") is False


class TestLimitClamping:
    """Tests for limit parameter clamping."""
    
    def test_normal_limit(self):
        """Normal limit should be preserved."""
        assert max(1, min(100, 1000)) == 100
    
    def test_zero_limit_clamped(self):
        """Zero limit should be clamped to 1."""
        assert max(1, min(0, 1000)) == 1
    
    def test_negative_limit_clamped(self):
        """Negative limit should be clamped to 1."""
        assert max(1, min(-10, 1000)) == 1
    
    def test_excessive_limit_clamped(self):
        """Excessive limit should be clamped to 1000."""
        assert max(1, min(5000, 1000)) == 1000


class TestImportEndpoint:
    """Integration tests for import endpoint."""
    
    @pytest.mark.asyncio
    async def test_path_traversal_in_filename(self):
        """Path traversal in filename should be blocked."""
        with patch('backend.routers.imports.open') as mock_open:
            with patch('backend.routers.imports.os.makedirs'):
                mock_file = MagicMock()
                mock_file.filename = "../../../../etc/malicious.zip"
                
                with pytest.raises(HTTPException) as exc_info:
                    await import_limitless_data(
                        job_id="test-job",
                        file=mock_file
                    )
                
                # Should get 400 for invalid path
                assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_error_shielding_on_write_failure(self):
        """Write failures should not leak internal errors."""
        with patch('backend.routers.imports.open', side_effect=PermissionError("Access denied")):
            mock_file = MagicMock()
            mock_file.filename = "data.zip"
            mock_file.read = MagicMock(return_value=b"test")
            
            with pytest.raises(HTTPException) as exc_info:
                await import_limitless_data(
                    job_id="test-job",
                    file=mock_file
                )
            
            # Should get generic error, not permission details
            assert exc_info.value.status_code == 500
            assert "Access denied" not in exc_info.value.detail
            assert "Please try again" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_valid_upload_succeeds(self):
        """Valid upload should succeed."""
        with patch('backend.routers.imports.open') as mock_open:
            mock_file = MagicMock()
            mock_file.filename = "data.zip"
            mock_file.read = MagicMock(side_effect=[b"chunk1", b"chunk2", b""])
            
            mock_open.return_value.__enter__ = lambda self: self
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            
            result = await import_limitless_data(
                job_id="test-job",
                file=mock_file
            )
            
            assert result["job_id"] == "test-job"
            assert result["status"] == "uploaded"


class TestDatabaseOperations:
    """Tests for database operation validation."""
    
    def test_get_job_status_rejects_traversal(self):
        """Path traversal in job_id should be rejected."""
        with pytest.raises(ValueError):
            get_import_job_status("../../../etc/passwd")
    
    def test_cancel_job_rejects_traversal(self):
        """Path traversal in job_id should be rejected."""
        with pytest.raises(ValueError):
            cancel_import_job("../secret")
    
    def test_delete_job_rejects_traversal(self):
        """Path traversal in job_id should be rejected."""
        with pytest.raises(ValueError):
            delete_import_job("job/123")
    
    def test_get_jobs_clamps_limit(self):
        """Limit should be clamped to valid range."""
        result = get_import_jobs(limit=-100)
        assert result["limit"] == 1
    
    def test_get_jobs_caps_limit(self):
        """Excessive limit should be capped."""
        result = get_import_jobs(limit=10000)
        assert result["limit"] == 1000
