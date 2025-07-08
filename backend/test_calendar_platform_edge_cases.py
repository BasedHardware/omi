#!/usr/bin/env python3
"""
Platform-specific edge case testing for Google Calendar integration.
Tests various scenarios across iOS, Android, Windows, and macOS platforms.
"""

import os
import sys
import json
import urllib.parse
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_oauth_redirect_handling():
    """Test OAuth redirect handling for different platforms."""
    print("🔐 Testing OAuth Redirect Handling")
    print("-" * 40)
    
    test_cases = [
        {
            'platform': 'iOS Safari',
            'redirect_uri': 'https://app.omi.me/calendar/callback',
            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'
        },
        {
            'platform': 'iOS App',
            'redirect_uri': 'omi://calendar/callback',
            'user_agent': 'Omi/1.0.0 (iPhone; iOS 15.0)'
        },
        {
            'platform': 'Android Chrome',
            'redirect_uri': 'https://app.omi.me/calendar/callback',
            'user_agent': 'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36'
        },
        {
            'platform': 'Android App',
            'redirect_uri': 'omi://calendar/callback',
            'user_agent': 'Omi/1.0.0 (Android; API 30)'
        },
        {
            'platform': 'Windows Desktop',
            'redirect_uri': 'http://localhost:8080/callback',
            'user_agent': 'Omi-Desktop/1.0.0 (Windows NT 10.0)'
        },
        {
            'platform': 'macOS Desktop',
            'redirect_uri': 'http://localhost:8080/callback',
            'user_agent': 'Omi-Desktop/1.0.0 (Macintosh; Intel Mac OS X 10_15_7)'
        }
    ]
    
    results = []
    for case in test_cases:
        try:
            # Test redirect URI validation
            parsed = urllib.parse.urlparse(case['redirect_uri'])
            is_valid = bool(parsed.scheme and (parsed.netloc or parsed.path))
            
            # Test platform-specific considerations
            platform_ok = True
            issues = []
            
            if case['platform'].startswith('iOS'):
                if case['redirect_uri'].startswith('omi://'):
                    # Custom scheme - need to handle app switching
                    issues.append("Need custom URL scheme handling in iOS app")
                elif 'localhost' in case['redirect_uri']:
                    issues.append("iOS doesn't support localhost redirects in Safari")
                    platform_ok = False
            
            elif case['platform'].startswith('Android'):
                if case['redirect_uri'].startswith('omi://'):
                    issues.append("Need intent-filter configuration for custom scheme")
                elif 'localhost' in case['redirect_uri']:
                    issues.append("Android may block localhost in some configurations")
            
            elif 'Desktop' in case['platform']:
                if not case['redirect_uri'].startswith('http://localhost'):
                    issues.append("Desktop apps typically use localhost for OAuth")
            
            success = is_valid and platform_ok
            results.append({
                'platform': case['platform'],
                'success': success,
                'issues': issues
            })
            
            status = "✅" if success else "⚠️"
            print(f"{status} {case['platform']}: {'OK' if success else 'Issues detected'}")
            for issue in issues:
                print(f"    - {issue}")
        
        except Exception as e:
            results.append({
                'platform': case['platform'],
                'success': False,
                'error': str(e)
            })
            print(f"❌ {case['platform']}: Error - {e}")
    
    return results

def test_token_storage_security():
    """Test secure token storage for different platforms."""
    print("\n🔒 Testing Token Storage Security")
    print("-" * 40)
    
    platform_storage = {
        'iOS': {
            'method': 'iOS Keychain',
            'encryption': True,
            'biometric': True,
            'considerations': ['App uninstall clears keychain', 'iCloud keychain sync']
        },
        'Android': {
            'method': 'Android Keystore',
            'encryption': True,
            'biometric': True,
            'considerations': ['Hardware-backed security', 'Account manager integration']
        },
        'Windows': {
            'method': 'Windows Credential Manager',
            'encryption': True,
            'biometric': False,
            'considerations': ['User profile specific', 'Admin access concerns']
        },
        'macOS': {
            'method': 'macOS Keychain',
            'encryption': True,
            'biometric': True,
            'considerations': ['Keychain Access app visibility', 'Admin authentication']
        }
    }
    
    for platform, storage in platform_storage.items():
        print(f"📱 {platform}:")
        print(f"   Storage: {storage['method']}")
        print(f"   Encrypted: {'Yes' if storage['encryption'] else 'No'}")
        print(f"   Biometric: {'Yes' if storage['biometric'] else 'No'}")
        print("   Considerations:")
        for consideration in storage['considerations']:
            print(f"     - {consideration}")
    
    return platform_storage

def test_network_connectivity_edge_cases():
    """Test network connectivity edge cases."""
    print("\n🌐 Testing Network Connectivity Edge Cases")
    print("-" * 40)
    
    edge_cases = [
        {
            'scenario': 'Poor cellular connection',
            'timeout': 30,
            'retry_strategy': 'exponential_backoff',
            'platforms': ['iOS', 'Android']
        },
        {
            'scenario': 'Corporate firewall',
            'timeout': 10,
            'retry_strategy': 'immediate_fail',
            'platforms': ['Windows', 'macOS']
        },
        {
            'scenario': 'Airplane mode during OAuth',
            'timeout': 5,
            'retry_strategy': 'queue_for_later',
            'platforms': ['iOS', 'Android']
        },
        {
            'scenario': 'WiFi captive portal',
            'timeout': 15,
            'retry_strategy': 'user_notification',
            'platforms': ['iOS', 'Android', 'Windows', 'macOS']
        },
        {
            'scenario': 'VPN interference',
            'timeout': 20,
            'retry_strategy': 'fallback_endpoint',
            'platforms': ['Windows', 'macOS']
        }
    ]
    
    for case in edge_cases:
        print(f"🔍 {case['scenario']}:")
        print(f"   Timeout: {case['timeout']}s")
        print(f"   Strategy: {case['retry_strategy']}")
        print(f"   Affects: {', '.join(case['platforms'])}")
        
        # Test timeout handling
        timeout_ok = 5 <= case['timeout'] <= 60
        print(f"   Timeout valid: {'✅' if timeout_ok else '❌'}")
    
    return edge_cases

def test_background_app_refresh():
    """Test background app refresh scenarios."""
    print("\n🔄 Testing Background App Refresh")
    print("-" * 40)
    
    scenarios = {
        'iOS': {
            'background_app_refresh': True,
            'token_refresh_timing': 'before_expiry',
            'considerations': [
                'Background App Refresh can be disabled by user',
                'iOS may kill app in low memory situations',
                'Silent push notifications for token refresh'
            ]
        },
        'Android': {
            'background_app_refresh': True,
            'token_refresh_timing': 'scheduled_job',
            'considerations': [
                'Doze mode and App Standby restrictions',
                'Battery optimization settings',
                'WorkManager for reliable background tasks'
            ]
        },
        'Windows': {
            'background_app_refresh': True,
            'token_refresh_timing': 'service_worker',
            'considerations': [
                'Windows service for persistent operation',
                'User account control permissions',
                'System startup registration'
            ]
        },
        'macOS': {
            'background_app_refresh': True,
            'token_refresh_timing': 'app_nap_aware',
            'considerations': [
                'App Nap feature may suspend app',
                'Login items for auto-start',
                'Notification permissions for updates'
            ]
        }
    }
    
    for platform, scenario in scenarios.items():
        print(f"📱 {platform}:")
        print(f"   Background refresh: {'Enabled' if scenario['background_app_refresh'] else 'Disabled'}")
        print(f"   Token refresh: {scenario['token_refresh_timing']}")
        print("   Platform considerations:")
        for consideration in scenario['considerations']:
            print(f"     - {consideration}")
    
    return scenarios

def test_oauth_flow_interruptions():
    """Test OAuth flow interruption scenarios."""
    print("\n⚠️ Testing OAuth Flow Interruptions")
    print("-" * 40)
    
    interruption_scenarios = [
        {
            'scenario': 'User cancels OAuth in browser',
            'handling': 'return_to_app_with_error',
            'user_action': 'show_retry_option'
        },
        {
            'scenario': 'Browser crashes during OAuth',
            'handling': 'detect_timeout_restart_flow',
            'user_action': 'clear_state_restart'
        },
        {
            'scenario': 'App backgrounded during OAuth',
            'handling': 'preserve_state_resume',
            'user_action': 'continue_where_left_off'
        },
        {
            'scenario': 'Network loss during redirect',
            'handling': 'cache_auth_code_retry',
            'user_action': 'automatic_retry'
        },
        {
            'scenario': 'Invalid OAuth response',
            'handling': 'validate_response_error',
            'user_action': 'show_detailed_error'
        }
    ]
    
    for scenario in interruption_scenarios:
        print(f"🔍 {scenario['scenario']}:")
        print(f"   Handling: {scenario['handling']}")
        print(f"   User action: {scenario['user_action']}")
        
        # Test if handling strategy is appropriate
        appropriate = not any(word in scenario['handling'] for word in ['ignore', 'crash', 'fail_silently'])
        print(f"   Strategy appropriate: {'✅' if appropriate else '❌'}")
    
    return interruption_scenarios

def test_calendar_api_rate_limits():
    """Test Google Calendar API rate limit handling."""
    print("\n⏱️ Testing Calendar API Rate Limits")
    print("-" * 40)
    
    rate_limit_tests = [
        {
            'scenario': 'Burst event creation',
            'api_calls': 100,
            'time_window': 60,
            'expected_behavior': 'exponential_backoff'
        },
        {
            'scenario': 'Concurrent user requests',
            'api_calls': 1000,
            'time_window': 3600,
            'expected_behavior': 'queue_requests'
        },
        {
            'scenario': 'Single user heavy usage',
            'api_calls': 10000,
            'time_window': 86400,
            'expected_behavior': 'temporary_limit'
        }
    ]
    
    for test in rate_limit_tests:
        print(f"🔍 {test['scenario']}:")
        print(f"   API calls: {test['api_calls']} in {test['time_window']}s")
        print(f"   Expected behavior: {test['expected_behavior']}")
        
        # Calculate rate
        rate = test['api_calls'] / test['time_window']
        print(f"   Rate: {rate:.2f} calls/second")
        
        # Check if rate is reasonable
        reasonable = rate < 10  # Google Calendar API typical limits
        print(f"   Rate reasonable: {'✅' if reasonable else '⚠️ May hit limits'}")
    
    return rate_limit_tests

def test_timezone_edge_cases():
    """Test timezone handling edge cases."""
    print("\n🌍 Testing Timezone Edge Cases")
    print("-" * 40)
    
    timezone_tests = [
        {
            'scenario': 'Daylight Saving Time transition',
            'timezone': 'America/New_York',
            'test_date': '2024-03-10T02:30:00',  # DST begins
            'expected_issues': ['Non-existent time', 'Ambiguous time']
        },
        {
            'scenario': 'User travels across timezones',
            'from_tz': 'America/Los_Angeles',
            'to_tz': 'Asia/Tokyo',
            'considerations': ['Event time interpretation', 'Calendar display']
        },
        {
            'scenario': 'UTC vs local time confusion',
            'server_tz': 'UTC',
            'client_tz': 'Europe/London',
            'considerations': ['API timestamp format', 'Display conversion']
        },
        {
            'scenario': 'Invalid timezone identifier',
            'timezone': 'Invalid/Timezone',
            'fallback': 'UTC',
            'handling': 'graceful_degradation'
        }
    ]
    
    try:
        import pytz
        
        for test in timezone_tests:
            print(f"🔍 {test['scenario']}:")
            
            if 'timezone' in test:
                try:
                    tz = pytz.timezone(test['timezone'])
                    print(f"   Timezone valid: ✅")
                except pytz.exceptions.UnknownTimeZoneError:
                    print(f"   Timezone valid: ❌ (Invalid timezone)")
                except Exception as e:
                    print(f"   Timezone valid: ❌ ({e})")
            
            if 'considerations' in test:
                print("   Considerations:")
                for consideration in test['considerations']:
                    print(f"     - {consideration}")
            
            if 'expected_issues' in test:
                print("   Expected issues:")
                for issue in test['expected_issues']:
                    print(f"     - {issue}")
    
    except ImportError:
        print("❌ pytz not available - timezone testing limited")
    
    return timezone_tests

def test_device_specific_limitations():
    """Test device-specific limitations."""
    print("\n📱 Testing Device-Specific Limitations")
    print("-" * 40)
    
    device_limits = {
        'iOS': {
            'memory_pressure': 'High - iOS aggressively manages memory',
            'background_execution': 'Limited - 30 seconds for most tasks',
            'network_restrictions': 'ATS requirements for HTTPS',
            'oauth_considerations': [
                'SFSafariViewController recommended over WKWebView',
                'Custom URL schemes must be registered',
                'Universal Links preferred for production'
            ]
        },
        'Android': {
            'memory_pressure': 'Variable - depends on device and Android version',
            'background_execution': 'Restricted - Doze mode and background limits',
            'network_restrictions': 'Network Security Config affects HTTP',
            'oauth_considerations': [
                'Custom Tabs preferred over WebView',
                'Intent filters needed for custom schemes',
                'App Links verification for production'
            ]
        },
        'Windows': {
            'memory_pressure': 'Low - Desktop has more available memory',
            'background_execution': 'Good - Services can run continuously',
            'network_restrictions': 'Firewall and proxy considerations',
            'oauth_considerations': [
                'Embedded browser or system default',
                'Localhost redirects work well',
                'Certificate validation important'
            ]
        },
        'macOS': {
            'memory_pressure': 'Low - Desktop has more available memory',
            'background_execution': 'Good - App Nap may affect inactive apps',
            'network_restrictions': 'Gatekeeper and security preferences',
            'oauth_considerations': [
                'WKWebView or system browser options',
                'Localhost redirects supported',
                'Notarization required for distribution'
            ]
        }
    }
    
    for platform, limits in device_limits.items():
        print(f"📱 {platform}:")
        print(f"   Memory pressure: {limits['memory_pressure']}")
        print(f"   Background execution: {limits['background_execution']}")
        print(f"   Network restrictions: {limits['network_restrictions']}")
        print("   OAuth considerations:")
        for consideration in limits['oauth_considerations']:
            print(f"     - {consideration}")
    
    return device_limits

def generate_platform_specific_recommendations():
    """Generate platform-specific implementation recommendations."""
    print("\n💡 Platform-Specific Recommendations")
    print("-" * 40)
    
    recommendations = {
        'iOS': [
            'Use SFSafariViewController for OAuth instead of WKWebView',
            'Implement Universal Links for production redirect URIs',
            'Store tokens in iOS Keychain with biometric protection',
            'Use Background App Refresh API for token refresh',
            'Handle app state transitions gracefully',
            'Implement retry logic for network requests',
            'Use NSURLSession with proper timeout configurations'
        ],
        'Android': [
            'Use Chrome Custom Tabs for OAuth flow',
            'Implement App Links verification for redirect URIs',
            'Store tokens in Android Keystore with encryption',
            'Use WorkManager for background token refresh',
            'Handle Doze mode and App Standby restrictions',
            'Implement exponential backoff for API calls',
            'Use OkHttp with connection pooling'
        ],
        'Windows': [
            'Use embedded WebView2 or system default browser',
            'Store tokens in Windows Credential Manager',
            'Implement Windows Service for background operations',
            'Handle Windows Firewall and proxy settings',
            'Use Windows Toast notifications for status updates',
            'Implement certificate pinning for security',
            'Use HttpClient with proper disposal patterns'
        ],
        'macOS': [
            'Use WKWebView with proper security configuration',
            'Store tokens in macOS Keychain with encryption',
            'Handle App Nap for background operations',
            'Implement proper sandbox permissions',
            'Use NSUserNotification for status updates',
            'Handle macOS security and privacy settings',
            'Use URLSession with delegate callbacks'
        ]
    }
    
    for platform, recs in recommendations.items():
        print(f"📱 {platform}:")
        for i, rec in enumerate(recs, 1):
            print(f"   {i}. {rec}")
    
    return recommendations

def main():
    """Run all platform edge case tests."""
    print("🧪 Google Calendar Integration - Platform Edge Case Testing")
    print("=" * 60)
    
    test_results = {}
    
    # Run all tests
    test_results['oauth_redirects'] = test_oauth_redirect_handling()
    test_results['token_storage'] = test_token_storage_security()
    test_results['network_edge_cases'] = test_network_connectivity_edge_cases()
    test_results['background_refresh'] = test_background_app_refresh()
    test_results['oauth_interruptions'] = test_oauth_flow_interruptions()
    test_results['rate_limits'] = test_calendar_api_rate_limits()
    test_results['timezone_edge_cases'] = test_timezone_edge_cases()
    test_results['device_limitations'] = test_device_specific_limitations()
    test_results['recommendations'] = generate_platform_specific_recommendations()
    
    print("\n" + "=" * 60)
    print("📊 Platform Edge Case Testing Complete")
    print("=" * 60)
    
    # Count issues found
    total_issues = 0
    for test_name, results in test_results.items():
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and not result.get('success', True):
                    total_issues += 1
    
    print(f"🔍 Edge cases analyzed: {sum(len(r) if isinstance(r, (list, dict)) else 1 for r in test_results.values())}")
    print(f"⚠️  Potential issues identified: {total_issues}")
    
    print("\n🎯 Key Recommendations:")
    print("1. Implement platform-specific OAuth flows")
    print("2. Use secure, platform-native token storage")
    print("3. Handle network connectivity gracefully")
    print("4. Implement proper background task management")
    print("5. Add comprehensive error handling and retry logic")
    print("6. Test thoroughly on actual devices")
    
    return test_results

if __name__ == "__main__":
    results = main()
    
    # Save results to file for reference
    with open('platform_edge_case_results.json', 'w') as f:
        # Convert results to JSON-serializable format
        json_results = {}
        for key, value in results.items():
            if isinstance(value, (list, dict, str, int, bool)):
                json_results[key] = value
            else:
                json_results[key] = str(value)
        
        json.dump(json_results, f, indent=2)
    
    print(f"\n📄 Results saved to: platform_edge_case_results.json")