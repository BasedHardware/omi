"""Tests for desktop version tag parsing."""
import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from routers.updates import _parse_desktop_version


class TestDesktopVersionParser:
    """Test _parse_desktop_version function."""

    def test_old_3_component_format_with_cm_suffix(self):
        """Test old 3-component format: v1.0.77+464-desktop-cm"""
        result = _parse_desktop_version("v1.0.77+464-desktop-cm")
        assert result is not None
        assert result['major'] == '1'
        assert result['minor'] == '0'
        assert result['patch'] == '77'
        assert result['build'] == '464'
        assert result['version'] == '1.0.77+464'
        assert result['tag_name'] == 'v1.0.77+464-desktop-cm'

    def test_old_3_component_format_with_auto_suffix(self):
        """Test old 3-component format: v1.0.524+614-desktop-auto"""
        result = _parse_desktop_version("v1.0.524+614-desktop-auto")
        assert result is not None
        assert result['major'] == '1'
        assert result['minor'] == '0'
        assert result['patch'] == '524'
        assert result['build'] == '614'
        assert result['version'] == '1.0.524+614'

    def test_old_3_component_macos_format(self):
        """Test old 3-component format: v0.6.4+6004-macos"""
        result = _parse_desktop_version("v0.6.4+6004-macos")
        assert result is not None
        assert result['major'] == '0'
        assert result['minor'] == '6'
        assert result['patch'] == '4'
        assert result['build'] == '6004'
        assert result['version'] == '0.6.4+6004'

    def test_new_2_component_v11_format(self):
        """Test new 2-component format: v11.0+11000-macos"""
        result = _parse_desktop_version("v11.0+11000-macos")
        assert result is not None
        assert result['major'] == '11'
        assert result['minor'] == '0'
        assert result['patch'] == '0'  # defaults to 0
        assert result['build'] == '11000'
        assert result['version'] == '11.0.0+11000'

    def test_new_2_component_v11_3_format(self):
        """Test new 2-component format: v11.3+11003-macos"""
        result = _parse_desktop_version("v11.3+11003-macos")
        assert result is not None
        assert result['major'] == '11'
        assert result['minor'] == '3'
        assert result['patch'] == '0'  # defaults to 0
        assert result['build'] == '11003'
        assert result['version'] == '11.3.0+11003'

    def test_3_component_v0_11_format(self):
        """Test 3-component v0.11.x format: v0.11.38+11038-macos"""
        result = _parse_desktop_version("v0.11.38+11038-macos")
        assert result is not None
        assert result['major'] == '0'
        assert result['minor'] == '11'
        assert result['patch'] == '38'
        assert result['build'] == '11038'
        assert result['version'] == '0.11.38+11038'

    def test_without_v_prefix(self):
        """Test without v prefix: 0.11.41+1100-macos"""
        result = _parse_desktop_version("0.11.41+1100-macos")
        assert result is not None
        assert result['major'] == '0'
        assert result['minor'] == '11'
        assert result['patch'] == '41'
        assert result['build'] == '1100'
        assert result['version'] == '0.11.41+1100'

    def test_windows_platform(self):
        """Test Windows platform: v1.0.77+464-windows"""
        result = _parse_desktop_version("v1.0.77+464-windows")
        assert result is not None
        assert result['version'] == '1.0.77+464'

    def test_linux_platform(self):
        """Test Linux platform: v1.0.77+464-linux"""
        result = _parse_desktop_version("v1.0.77+464-linux")
        assert result is not None
        assert result['version'] == '1.0.77+464'

    def test_firmware_tag_rejected(self):
        """Test that firmware tags are rejected: Omi_CV1_v3.0.15"""
        result = _parse_desktop_version("Omi_CV1_v3.0.15")
        assert result is None

    def test_missing_build_number_rejected(self):
        """Test that tags without build number are rejected: v1.0.77-macos"""
        result = _parse_desktop_version("v1.0.77-macos")
        assert result is None

    def test_non_numeric_build_rejected(self):
        """Test that tags with non-numeric build are rejected: v1.0.77+abc-macos"""
        result = _parse_desktop_version("v1.0.77+abc-macos")
        assert result is None

    def test_case_insensitive_platform(self):
        """Test case insensitive platform matching: v1.0.77+464-MACOS"""
        result = _parse_desktop_version("v1.0.77+464-MACOS")
        assert result is not None
        assert result['version'] == '1.0.77+464'
