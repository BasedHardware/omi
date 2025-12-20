"""
Configuration module for white-labeling support.
Provides app name configuration via environment variables.
"""
import os
from functools import lru_cache


class AppConfig:
    """
    Central configuration for app branding.
    Follows the Flutter pattern with APP_NAME environment variable.
    """

    _DEFAULT_APP_NAME = "Nooto"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_app_name() -> str:
        """Get the configured app name (e.g., 'Nooto')"""
        return os.getenv("APP_NAME", AppConfig._DEFAULT_APP_NAME)

    @staticmethod
    def get_app_name_lower() -> str:
        """Get lowercase app name for identifiers (e.g., 'nooto')"""
        return AppConfig.get_app_name().lower()


# Convenience shortcuts for common usage
def get_app_name() -> str:
    """Shortcut for AppConfig.get_app_name()"""
    return AppConfig.get_app_name()


def get_app_name_lower() -> str:
    """Shortcut for AppConfig.get_app_name_lower()"""
    return AppConfig.get_app_name_lower()
