import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';

import 'package:omi/backend/preferences.dart';

/// Stable device-type labels returned by [ClientDeviceService.deviceProvenanceType].
///
/// The UI layer resolves these to localized strings via `context.l10n`.
enum DeviceProvenanceType { thisDevice, thisIphone, thisPhone, mac, iphone, android, other }

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

  /// Returns a semantic [DeviceProvenanceType] for the capture device, or null if
  /// [primaryCaptureDevice] is absent. The UI layer resolves the enum to a localized
  /// label — the service never hardcodes user-facing strings.
  DeviceProvenanceType? deviceProvenanceType({String? primaryCaptureDevice}) {
    if (primaryCaptureDevice == null || primaryCaptureDevice.isEmpty) {
      return null;
    }
    if (primaryCaptureDevice == clientDeviceId) {
      if (Platform.isIOS) return DeviceProvenanceType.thisIphone;
      if (Platform.isAndroid) return DeviceProvenanceType.thisPhone;
      return DeviceProvenanceType.thisDevice;
    }
    final platformPrefix = primaryCaptureDevice.split('_').first;
    switch (platformPrefix) {
      case 'macos':
        return DeviceProvenanceType.mac;
      case 'ios':
        return DeviceProvenanceType.iphone;
      case 'android':
        return DeviceProvenanceType.android;
      default:
        return DeviceProvenanceType.other;
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
