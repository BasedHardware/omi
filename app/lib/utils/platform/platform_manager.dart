import 'dart:io';

import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/services/client_device_service.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
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
  AnalyticsManager get analytics => AnalyticsManager();
  IntercomManager get intercom => IntercomManager.instance;
  CrashReporter get crashReporter => CrashlyticsManager.instance;

  static Future<void> initializeServices() async {
    _instance._packageInfo = await PackageInfo.fromPlatform();
    await ClientDeviceService.instance.initialize();
    _instance._deviceIdHash = ClientDeviceService.instance.deviceIdHash;
    await AnalyticsManager.init();
    await IntercomManager.instance.initIntercom();
  }

  Future<String> _getDeviceIdHash() async {
    await ClientDeviceService.instance.initialize();
    return ClientDeviceService.instance.deviceIdHash;
  }

  String get platform => Platform.operatingSystem;
  String get appVersion => '${_packageInfo.version}+${_packageInfo.buildNumber}';
  String get deviceIdHash => ClientDeviceService.instance.deviceIdHash;

  bool get isAnalyticsSupported => PlatformService.isAnalyticsSupported;
  bool get isDebuggingSupported => PlatformService.isCrashlyticsSupported;
  bool get isFCMSupported => Platform.isAndroid || Platform.isIOS;
}
