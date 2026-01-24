import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/debugging/crash_reporter.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Centralized platform manager for all platform-specific services
/// This provides a single point of access for all platform services
class PlatformManager {
  static final PlatformManager _instance = PlatformManager._internal();
  late PackageInfo _packageInfo;
  late String _deviceIdHash;

  factory PlatformManager() => _instance;
  PlatformManager._internal();

  static PlatformManager get instance => _instance;

  // Service instances
  MixpanelManager get mixpanel => MixpanelManager();
  IntercomManager get intercom => IntercomManager.instance;
  CrashReporter get crashReporter => CrashlyticsManager.instance;

  static Future<void> initializeServices() async {
    _instance._packageInfo = await PackageInfo.fromPlatform();
    _instance._deviceIdHash = await _instance._getDeviceIdHash();
    await MixpanelManager.init();
    await IntercomManager.instance.initIntercom();
  }

  Future<String> _getDeviceIdHash() async {
    // Check if already stored
    String? storedHash = SharedPreferencesUtil().deviceIdHash;
    if (storedHash != null && storedHash.isNotEmpty) {
      return storedHash;
    }

    // Generate hash from device info
    final deviceInfo = DeviceInfoPlugin();
    String deviceIdentifier = '';

    try {
      if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        deviceIdentifier = iosInfo.identifierForVendor ?? '';
      } else if (Platform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        deviceIdentifier = androidInfo.id;
      } else if (Platform.isMacOS) {
        final macInfo = await deviceInfo.macOsInfo;
        deviceIdentifier = macInfo.systemGUID ?? '';
      }
    } catch (e) {
      // Fallback to timestamp if device info fails
      deviceIdentifier = DateTime.now().millisecondsSinceEpoch.toString();
    }

    // Hash it (first 8 chars of SHA256)
    final hash = sha256.convert(utf8.encode(deviceIdentifier)).toString().substring(0, 8);
    SharedPreferencesUtil().deviceIdHash = hash;
    return hash;
  }

  String get platform => Platform.operatingSystem;
  String get appVersion => '${_packageInfo.version}+${_packageInfo.buildNumber}';
  String get deviceIdHash => _deviceIdHash;

  bool get isAnalyticsSupported => PlatformService.isAnalyticsSupported;
  bool get isDebuggingSupported => PlatformService.isCrashlyticsSupported;
  bool get isMacOS => PlatformService.isMacOS;
  bool get isFCMSupported => Platform.isAndroid || Platform.isIOS || Platform.isMacOS;
}
