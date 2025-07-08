"""
Comprehensive error handling and recovery system for Google Calendar integration.
Handles platform-specific errors, network issues, and provides graceful fallbacks.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum
import logging
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
import json

# Configure logging
logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    PERMISSION = "permission"
    DATA_VALIDATION = "data_validation"
    PLATFORM_SPECIFIC = "platform_specific"
    EXTERNAL_API = "external_api"

@dataclass
class CalendarError:
    code: str
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    platform: Optional[str] = None
    retry_after: Optional[int] = None
    recovery_action: Optional[str] = None
    user_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class CalendarErrorHandler:
    def __init__(self):
        self.error_registry = self._build_error_registry()
        self.retry_strategies = self._build_retry_strategies()
        self.platform_handlers = self._build_platform_handlers()
        
    def _build_error_registry(self) -> Dict[str, CalendarError]:
        """Build a comprehensive registry of known errors and their handling."""
        return {
            # Authentication Errors
            "auth_token_expired": CalendarError(
                code="auth_token_expired",
                message="Authentication token has expired",
                category=ErrorCategory.AUTHENTICATION,
                severity=ErrorSeverity.HIGH,
                recovery_action="refresh_token",
                user_message="Your calendar access has expired. Please reconnect your account."
            ),
            "auth_token_invalid": CalendarError(
                code="auth_token_invalid",
                message="Authentication token is invalid",
                category=ErrorCategory.AUTHENTICATION,
                severity=ErrorSeverity.HIGH,
                recovery_action="re_authenticate",
                user_message="Your calendar access is invalid. Please reconnect your account."
            ),
            "auth_refresh_failed": CalendarError(
                code="auth_refresh_failed",
                message="Failed to refresh authentication token",
                category=ErrorCategory.AUTHENTICATION,
                severity=ErrorSeverity.CRITICAL,
                recovery_action="re_authenticate",
                user_message="Failed to refresh your calendar access. Please reconnect your account."
            ),
            
            # Network Errors
            "network_timeout": CalendarError(
                code="network_timeout",
                message="Network request timed out",
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.MEDIUM,
                retry_after=30,
                recovery_action="retry_with_backoff",
                user_message="Network timeout. Please check your connection and try again."
            ),
            "network_unreachable": CalendarError(
                code="network_unreachable",
                message="Network is unreachable",
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.HIGH,
                retry_after=60,
                recovery_action="retry_when_connected",
                user_message="No internet connection. Please check your network and try again."
            ),
            "dns_resolution_failed": CalendarError(
                code="dns_resolution_failed",
                message="DNS resolution failed",
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.MEDIUM,
                retry_after=120,
                recovery_action="retry_with_backoff",
                user_message="Connection issues. Please try again in a few minutes."
            ),
            
            # Rate Limiting Errors
            "rate_limit_exceeded": CalendarError(
                code="rate_limit_exceeded",
                message="API rate limit exceeded",
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.MEDIUM,
                retry_after=3600,
                recovery_action="exponential_backoff",
                user_message="Too many requests. Please try again later."
            ),
            "quota_exceeded": CalendarError(
                code="quota_exceeded",
                message="API quota exceeded",
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.HIGH,
                retry_after=86400,
                recovery_action="wait_reset",
                user_message="Daily quota exceeded. Please try again tomorrow."
            ),
            
            # Permission Errors
            "insufficient_permissions": CalendarError(
                code="insufficient_permissions",
                message="Insufficient permissions for calendar access",
                category=ErrorCategory.PERMISSION,
                severity=ErrorSeverity.HIGH,
                recovery_action="request_permissions",
                user_message="Insufficient permissions. Please grant calendar access and reconnect."
            ),
            "calendar_not_found": CalendarError(
                code="calendar_not_found",
                message="Calendar not found or access denied",
                category=ErrorCategory.PERMISSION,
                severity=ErrorSeverity.HIGH,
                recovery_action="select_different_calendar",
                user_message="Calendar not accessible. Please select a different calendar."
            ),
            
            # Platform-Specific Errors
            "ios_safari_unavailable": CalendarError(
                code="ios_safari_unavailable",
                message="Safari View Controller is not available",
                category=ErrorCategory.PLATFORM_SPECIFIC,
                severity=ErrorSeverity.MEDIUM,
                platform="ios",
                recovery_action="use_external_browser",
                user_message="Safari is not available. Opening in external browser."
            ),
            "android_custom_tabs_unavailable": CalendarError(
                code="android_custom_tabs_unavailable",
                message="Chrome Custom Tabs is not available",
                category=ErrorCategory.PLATFORM_SPECIFIC,
                severity=ErrorSeverity.MEDIUM,
                platform="android",
                recovery_action="use_webview",
                user_message="Custom tabs not available. Using built-in browser."
            ),
            "keychain_access_denied": CalendarError(
                code="keychain_access_denied",
                message="Access to keychain was denied",
                category=ErrorCategory.PLATFORM_SPECIFIC,
                severity=ErrorSeverity.HIGH,
                platform="ios",
                recovery_action="request_keychain_access",
                user_message="Keychain access denied. Please check your security settings."
            ),
            "keystore_unavailable": CalendarError(
                code="keystore_unavailable",
                message="Android Keystore is not available",
                category=ErrorCategory.PLATFORM_SPECIFIC,
                severity=ErrorSeverity.HIGH,
                platform="android",
                recovery_action="use_fallback_storage",
                user_message="Secure storage unavailable. Using alternative storage method."
            ),
            
            # Data Validation Errors
            "invalid_event_data": CalendarError(
                code="invalid_event_data",
                message="Invalid event data provided",
                category=ErrorCategory.DATA_VALIDATION,
                severity=ErrorSeverity.LOW,
                recovery_action="validate_and_fix",
                user_message="Invalid event data. Please check your input."
            ),
            "timezone_invalid": CalendarError(
                code="timezone_invalid",
                message="Invalid timezone specified",
                category=ErrorCategory.DATA_VALIDATION,
                severity=ErrorSeverity.LOW,
                recovery_action="use_default_timezone",
                user_message="Invalid timezone. Using default timezone."
            ),
            "date_format_invalid": CalendarError(
                code="date_format_invalid",
                message="Invalid date format",
                category=ErrorCategory.DATA_VALIDATION,
                severity=ErrorSeverity.LOW,
                recovery_action="format_date",
                user_message="Invalid date format. Correcting automatically."
            ),
            
            # External API Errors
            "google_api_error": CalendarError(
                code="google_api_error",
                message="Google Calendar API error",
                category=ErrorCategory.EXTERNAL_API,
                severity=ErrorSeverity.MEDIUM,
                retry_after=60,
                recovery_action="retry_with_backoff",
                user_message="Calendar service error. Please try again."
            ),
            "service_unavailable": CalendarError(
                code="service_unavailable",
                message="Google Calendar service is unavailable",
                category=ErrorCategory.EXTERNAL_API,
                severity=ErrorSeverity.HIGH,
                retry_after=300,
                recovery_action="retry_later",
                user_message="Calendar service is currently unavailable. Please try again later."
            )
        }
    
    def _build_retry_strategies(self) -> Dict[str, Callable]:
        """Build retry strategies for different error types."""
        return {
            "retry_with_backoff": self._exponential_backoff_retry,
            "exponential_backoff": self._exponential_backoff_retry,
            "retry_when_connected": self._retry_when_network_available,
            "retry_later": self._fixed_delay_retry,
            "no_retry": lambda *args: False
        }
    
    def _build_platform_handlers(self) -> Dict[str, Callable]:
        """Build platform-specific error handlers."""
        return {
            "ios": self._handle_ios_error,
            "android": self._handle_android_error,
            "windows": self._handle_windows_error,
            "macos": self._handle_macos_error,
            "web": self._handle_web_error
        }
    
    def handle_error(self, 
                    error: Exception, 
                    context: Dict[str, Any] = None,
                    platform: str = None) -> CalendarError:
        """Main error handling entry point."""
        context = context or {}
        
        # Classify the error
        calendar_error = self._classify_error(error, platform)
        
        # Add context information
        calendar_error.details = {
            "original_error": str(error),
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
            "platform": platform
        }
        
        # Log the error
        self._log_error(calendar_error, error)
        
        # Apply platform-specific handling if needed
        if platform and platform in self.platform_handlers:
            calendar_error = self.platform_handlers[platform](calendar_error, error)
        
        return calendar_error
    
    def _classify_error(self, error: Exception, platform: str = None) -> CalendarError:
        """Classify an exception into a known CalendarError."""
        
        # Handle Google API errors
        if isinstance(error, HttpError):
            return self._handle_http_error(error)
        
        # Handle authentication errors
        if isinstance(error, RefreshError):
            return self.error_registry["auth_refresh_failed"]
        
        # Handle network errors
        error_str = str(error).lower()
        if any(keyword in error_str for keyword in ["timeout", "timed out"]):
            return self.error_registry["network_timeout"]
        elif any(keyword in error_str for keyword in ["unreachable", "connection refused", "network"]):
            return self.error_registry["network_unreachable"]
        elif "dns" in error_str:
            return self.error_registry["dns_resolution_failed"]
        
        # Handle platform-specific errors
        if platform:
            if platform == "ios" and "safari" in error_str:
                return self.error_registry["ios_safari_unavailable"]
            elif platform == "android" and "custom tabs" in error_str:
                return self.error_registry["android_custom_tabs_unavailable"]
            elif platform == "ios" and "keychain" in error_str:
                return self.error_registry["keychain_access_denied"]
            elif platform == "android" and "keystore" in error_str:
                return self.error_registry["keystore_unavailable"]
        
        # Default to generic error
        return CalendarError(
            code="unknown_error",
            message=f"Unknown error: {str(error)}",
            category=ErrorCategory.EXTERNAL_API,
            severity=ErrorSeverity.MEDIUM,
            recovery_action="retry_with_backoff",
            user_message="An unexpected error occurred. Please try again."
        )
    
    def _handle_http_error(self, error: HttpError) -> CalendarError:
        """Handle Google API HTTP errors."""
        status_code = error.resp.status
        reason = error.resp.reason
        
        if status_code == 401:
            return self.error_registry["auth_token_expired"]
        elif status_code == 403:
            error_details = json.loads(error.content.decode()) if error.content else {}
            error_reason = error_details.get("error", {}).get("errors", [{}])[0].get("reason", "")
            
            if "rateLimitExceeded" in error_reason:
                return self.error_registry["rate_limit_exceeded"]
            elif "quotaExceeded" in error_reason:
                return self.error_registry["quota_exceeded"]
            else:
                return self.error_registry["insufficient_permissions"]
        elif status_code == 404:
            return self.error_registry["calendar_not_found"]
        elif status_code == 429:
            return self.error_registry["rate_limit_exceeded"]
        elif status_code >= 500:
            return self.error_registry["service_unavailable"]
        else:
            error_obj = self.error_registry["google_api_error"]
            error_obj.details = {"status_code": status_code, "reason": reason}
            return error_obj
    
    def _handle_ios_error(self, calendar_error: CalendarError, original_error: Exception) -> CalendarError:
        """Handle iOS-specific errors."""
        error_str = str(original_error).lower()
        
        if "background app refresh" in error_str:
            calendar_error.user_message = "Background refresh disabled. Please enable it in Settings."
            calendar_error.recovery_action = "enable_background_refresh"
        elif "biometric" in error_str:
            calendar_error.user_message = "Biometric authentication failed. Please try again."
            calendar_error.recovery_action = "retry_biometric"
        
        return calendar_error
    
    def _handle_android_error(self, calendar_error: CalendarError, original_error: Exception) -> CalendarError:
        """Handle Android-specific errors."""
        error_str = str(original_error).lower()
        
        if "doze mode" in error_str or "app standby" in error_str:
            calendar_error.user_message = "App optimization interfering. Please disable battery optimization."
            calendar_error.recovery_action = "disable_battery_optimization"
        elif "work manager" in error_str:
            calendar_error.user_message = "Background task failed. Please try again."
            calendar_error.recovery_action = "reschedule_work"
        
        return calendar_error
    
    def _handle_windows_error(self, calendar_error: CalendarError, original_error: Exception) -> CalendarError:
        """Handle Windows-specific errors."""
        error_str = str(original_error).lower()
        
        if "firewall" in error_str:
            calendar_error.user_message = "Firewall blocking connection. Please check firewall settings."
            calendar_error.recovery_action = "check_firewall"
        elif "proxy" in error_str:
            calendar_error.user_message = "Proxy configuration issue. Please check proxy settings."
            calendar_error.recovery_action = "check_proxy"
        
        return calendar_error
    
    def _handle_macos_error(self, calendar_error: CalendarError, original_error: Exception) -> CalendarError:
        """Handle macOS-specific errors."""
        error_str = str(original_error).lower()
        
        if "app nap" in error_str:
            calendar_error.user_message = "App Nap is affecting background operations."
            calendar_error.recovery_action = "disable_app_nap"
        elif "gatekeeper" in error_str:
            calendar_error.user_message = "Security settings blocking operation."
            calendar_error.recovery_action = "check_security_settings"
        
        return calendar_error
    
    def _handle_web_error(self, calendar_error: CalendarError, original_error: Exception) -> CalendarError:
        """Handle web-specific errors."""
        error_str = str(original_error).lower()
        
        if "cors" in error_str:
            calendar_error.user_message = "Cross-origin request blocked. Please try a different browser."
            calendar_error.recovery_action = "try_different_browser"
        elif "popup blocked" in error_str:
            calendar_error.user_message = "Popup blocked. Please allow popups for this site."
            calendar_error.recovery_action = "allow_popups"
        
        return calendar_error
    
    def should_retry(self, calendar_error: CalendarError, attempt_count: int = 1) -> bool:
        """Determine if an operation should be retried."""
        if calendar_error.severity == ErrorSeverity.CRITICAL:
            return False
        
        if calendar_error.category == ErrorCategory.AUTHENTICATION and attempt_count > 1:
            return False
        
        if calendar_error.category == ErrorCategory.RATE_LIMIT and attempt_count > 3:
            return False
        
        if calendar_error.category == ErrorCategory.NETWORK and attempt_count > 5:
            return False
        
        return attempt_count <= 3
    
    def get_retry_delay(self, calendar_error: CalendarError, attempt_count: int = 1) -> int:
        """Calculate retry delay based on error type and attempt count."""
        if calendar_error.retry_after:
            return calendar_error.retry_after
        
        base_delays = {
            ErrorCategory.NETWORK: 5,
            ErrorCategory.RATE_LIMIT: 60,
            ErrorCategory.EXTERNAL_API: 30,
            ErrorCategory.AUTHENTICATION: 10
        }
        
        base_delay = base_delays.get(calendar_error.category, 30)
        
        # Exponential backoff with jitter
        import random
        delay = base_delay * (2 ** (attempt_count - 1))
        jitter = random.uniform(0.5, 1.5)
        
        return min(int(delay * jitter), 300)  # Cap at 5 minutes
    
    async def _exponential_backoff_retry(self, 
                                       operation: Callable,
                                       calendar_error: CalendarError,
                                       max_attempts: int = 3) -> bool:
        """Implement exponential backoff retry strategy."""
        for attempt in range(1, max_attempts + 1):
            try:
                await operation()
                return True
            except Exception as e:
                if attempt == max_attempts:
                    return False
                
                delay = self.get_retry_delay(calendar_error, attempt)
                logger.info(f"Retrying operation in {delay} seconds (attempt {attempt}/{max_attempts})")
                await asyncio.sleep(delay)
        
        return False
    
    async def _retry_when_network_available(self, 
                                          operation: Callable,
                                          calendar_error: CalendarError,
                                          max_wait: int = 300) -> bool:
        """Retry when network becomes available."""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                # Simple network check
                import socket
                socket.create_connection(("8.8.8.8", 53), timeout=5)
                
                # Network is available, try operation
                await operation()
                return True
            except:
                await asyncio.sleep(10)  # Check every 10 seconds
        
        return False
    
    async def _fixed_delay_retry(self, 
                               operation: Callable,
                               calendar_error: CalendarError,
                               delay: int = None) -> bool:
        """Retry after a fixed delay."""
        delay = delay or calendar_error.retry_after or 60
        
        logger.info(f"Retrying operation after {delay} seconds")
        await asyncio.sleep(delay)
        
        try:
            await operation()
            return True
        except:
            return False
    
    def _log_error(self, calendar_error: CalendarError, original_error: Exception):
        """Log error with appropriate level based on severity."""
        log_data = {
            "error_code": calendar_error.code,
            "category": calendar_error.category.value,
            "severity": calendar_error.severity.value,
            "message": calendar_error.message,
            "original_error": str(original_error),
            "details": calendar_error.details
        }
        
        if calendar_error.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical calendar error", extra=log_data)
        elif calendar_error.severity == ErrorSeverity.HIGH:
            logger.error("High severity calendar error", extra=log_data)
        elif calendar_error.severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity calendar error", extra=log_data)
        else:
            logger.info("Low severity calendar error", extra=log_data)
    
    def get_user_friendly_message(self, calendar_error: CalendarError) -> str:
        """Get a user-friendly error message."""
        return calendar_error.user_message or calendar_error.message
    
    def get_recovery_suggestions(self, calendar_error: CalendarError) -> List[str]:
        """Get recovery suggestions for the user."""
        suggestions = []
        
        if calendar_error.category == ErrorCategory.AUTHENTICATION:
            suggestions.extend([
                "Reconnect your Google Calendar account",
                "Check your internet connection",
                "Try signing out and signing back in"
            ])
        elif calendar_error.category == ErrorCategory.NETWORK:
            suggestions.extend([
                "Check your internet connection",
                "Try again in a few minutes",
                "Switch to a different network if available"
            ])
        elif calendar_error.category == ErrorCategory.RATE_LIMIT:
            suggestions.extend([
                "Wait a few minutes before trying again",
                "Reduce the frequency of calendar operations",
                "Try again during off-peak hours"
            ])
        elif calendar_error.category == ErrorCategory.PERMISSION:
            suggestions.extend([
                "Check your Google Calendar permissions",
                "Ensure the calendar exists and is accessible",
                "Reconnect with proper permissions"
            ])
        elif calendar_error.category == ErrorCategory.PLATFORM_SPECIFIC:
            if calendar_error.platform == "ios":
                suggestions.extend([
                    "Check iOS settings and permissions",
                    "Update to the latest iOS version",
                    "Restart the app"
                ])
            elif calendar_error.platform == "android":
                suggestions.extend([
                    "Check Android app permissions",
                    "Disable battery optimization for this app",
                    "Update Google Play Services"
                ])
        
        return suggestions

# Global error handler instance
calendar_error_handler = CalendarErrorHandler()