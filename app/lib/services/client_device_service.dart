import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';

import 'package:omi/backend/preferences.dart';

/// Shared stable per-installation device identity for provenance (not notifications-only).
class ClientDeviceService {
  ClientDeviceService._();
  static final ClientDeviceService instance = ClientDeviceService._();

  String? _deviceIdHash;

  Future<void> initialize() async {
    _deviceIdHash = await _loadOrCreateDeviceIdHash();
  }

  String get deviceIdHash => _deviceIdHash ?? '';

  String get platform => Platform.operatingSystem;

  /// Contract: `{platform}_{hash}` — same shape as backend FCM `device_key`.
  String get clientDeviceId {
    final hash = deviceIdHash;
    if (hash.isEmpty) return '';
    return '${platform}_$hash';
  }

  String? deviceProvenanceLabel({String? primaryCaptureDevice}) {
    if (primaryCaptureDevice == null || primaryCaptureDevice.isEmpty) {
      return null;
    }
    if (primaryCaptureDevice == clientDeviceId) {
      return Platform.isIOS ? 'This iPhone' : Platform.isAndroid ? 'This phone' : 'This device';
    }
    final platformPrefix = primaryCaptureDevice.split('_').first;
    switch (platformPrefix) {
      case 'macos':
        return 'Mac';
      case 'ios':
        return 'iPhone';
      case 'android':
        return 'Android';
      default:
        return platformPrefix;
    }
  }

  bool memoryMatchesThisDevice({String? primaryCaptureDevice, List<String> captureDeviceIds = const []}) {
    final localId = clientDeviceId;
    if (localId.isEmpty) return false;
    if (primaryCaptureDevice == localId) return true;
    return captureDeviceIds.contains(localId);
  }

  Future<String> _loadOrCreateDeviceIdHash() async {
    final storedHash = SharedPreferencesUtil().deviceIdHash;
    if (storedHash != null && storedHash.isNotEmpty) {
      return storedHash;
    }

    final deviceInfo = DeviceInfoPlugin();
    String deviceIdentifier = '';

    try {
      if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        deviceIdentifier = iosInfo.identifierForVendor ?? '';
      } else if (Platform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        deviceIdentifier = androidInfo.id;
      }
    } catch (_) {
      deviceIdentifier = DateTime.now().millisecondsSinceEpoch.toString();
    }

    final hash = sha256.convert(utf8.encode(deviceIdentifier)).toString().substring(0, 8);
    SharedPreferencesUtil().deviceIdHash = hash;
    return hash;
  }
}
