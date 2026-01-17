import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class WifiNetworkService {
  static const _channel = MethodChannel('com.omi.wifi_network');

  static WifiNetworkService? _instance;
  static WifiNetworkService get instance {
    _instance ??= WifiNetworkService._();
    return _instance!;
  }

  WifiNetworkService._();

  factory WifiNetworkService() => instance;

  /// Format: omi_{last4chars} e.g., "omi_a1b2"
  static String generateSsid(String deviceId) {
    final cleanId = deviceId.replaceAll(':', '').replaceAll('-', '');
    final suffix = cleanId.length >= 4 ? cleanId.substring(cleanId.length - 4).toLowerCase() : cleanId.toLowerCase();
    return 'omi_$suffix';
  }

  /// Generates a password from device ID
  /// Format: omi_{last8chars} e.g., "omi_a1b2c3d4"
  static String generatePassword(String deviceId) {
    final cleanId = deviceId.replaceAll(':', '').replaceAll('-', '');
    final suffix = cleanId.length >= 8 ? cleanId.substring(cleanId.length - 8).toLowerCase() : cleanId.toLowerCase();
    return 'omi_$suffix';
  }

  Future<WifiConnectionResult> connectToAp(String ssid, {String? password}) async {
    try {
      final result = await _channel.invokeMethod<Map<dynamic, dynamic>>('connectToWifi', {
        'ssid': ssid,
        if (password != null) 'password': password,
      });

      if (result == null) {
        return WifiConnectionResult.failure('No response from platform');
      }

      return WifiConnectionResult.fromMap(result);
    } on PlatformException catch (e) {
      debugPrint('WifiNetworkService: Platform exception: ${e.message}');
      return WifiConnectionResult.failure(e.message ?? 'Connection failed');
    } catch (e) {
      debugPrint('WifiNetworkService: Error connecting to AP: $e');
      return WifiConnectionResult.failure('Connection failed: $e');
    }
  }

  Future<bool> disconnectFromAp(String ssid) async {
    debugPrint('WifiNetworkService: Disconnecting from AP: $ssid');
    try {
      final result = await _channel.invokeMethod<bool>('disconnectFromWifi', {
        'ssid': ssid,
      });
      return result ?? false;
    } catch (e) {
      debugPrint('WifiNetworkService: Error disconnecting from AP: $e');
      return false;
    }
  }

  Future<bool> isConnectedToAp(String ssid) async {
    try {
      final result = await _channel.invokeMethod<bool>('isConnectedToWifi', {
        'ssid': ssid,
      });
      return result ?? false;
    } catch (e) {
      debugPrint('WifiNetworkService: Error checking connection: $e');
      return false;
    }
  }
}

/// Result of a WiFi connection attempt.
class WifiConnectionResult {
  final bool success;
  final String? errorMessage;
  final WifiConnectionError? error;

  WifiConnectionResult._({
    required this.success,
    this.errorMessage,
    this.error,
  });

  factory WifiConnectionResult.success() {
    return WifiConnectionResult._(success: true);
  }

  factory WifiConnectionResult.failure(String? message, {WifiConnectionError? error}) {
    return WifiConnectionResult._(
      success: false,
      errorMessage: message,
      error: error,
    );
  }

  factory WifiConnectionResult.fromMap(Map<dynamic, dynamic> map) {
    if (map['success'] == true) {
      return WifiConnectionResult.success();
    }
    return WifiConnectionResult.failure(
      map['error'] as String?,
      error: WifiConnectionError.fromCode(map['errorCode'] as int?),
    );
  }

  @override
  String toString() {
    if (success) return 'WifiConnectionResult(success)';
    return 'WifiConnectionResult(failed: $errorMessage, error: $error)';
  }
}

/// Error codes for WiFi connection failures.
enum WifiConnectionError {
  /// Device/OS doesn't support programmatic WiFi connection
  notSupported,

  /// User denied WiFi connection permission/prompt
  permissionDenied,

  /// SSID not found in range
  networkNotFound,

  /// Failed to connect to the network
  connectionFailed,

  /// Connection attempt timed out
  timeout,

  /// Already connected to this network (not an error)
  alreadyConnected,

  /// Failed to join network
  joinFailed,

  /// Unknown error
  unknown;

  static WifiConnectionError fromCode(int? code) {
    switch (code) {
      case 1:
        return notSupported;
      case 2:
        return permissionDenied;
      case 3:
        return networkNotFound;
      case 4:
        return connectionFailed;
      case 5:
        return joinFailed;
      case 6:
        return timeout;
      case 7:
        return alreadyConnected;
      default:
        return unknown;
    }
  }

  String get userMessage {
    switch (this) {
      case notSupported:
        return 'WiFi connection not supported on this device';
      case permissionDenied:
        return 'WiFi permission denied';
      case networkNotFound:
        return 'Device WiFi network not found. Make sure the device is nearby.';
      case connectionFailed:
        return 'Failed to connect to device WiFi';
      case timeout:
        return 'WiFi connection timed out';
      case alreadyConnected:
        return 'Already connected';
      case joinFailed:
        return 'Failed to join device WiFi. Please try again.';
      case unknown:
        return 'Unknown WiFi error';
    }
  }
}
