import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
import 'package:omi/utils/debugging/crash_reporter.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Centralized platform manager for all platform-specific services
/// This provides a single point of access for all platform services
class PlatformManager {
  static final PlatformManager _instance = PlatformManager._internal();

  factory PlatformManager() => _instance;
  PlatformManager._internal();

  static PlatformManager get instance => _instance;

  // Service instances
  MixpanelManager get mixpanel => MixpanelManager();
  IntercomManager get intercom => IntercomManager.instance;
  CrashReporter get crashReporter => CrashlyticsManager.instance;

  static Future<void> initializeServices() async {
    await MixpanelManager.init();
    await IntercomManager.instance.initIntercom();
  }

  bool get isAnalyticsSupported => PlatformService.isAnalyticsSupported;
  bool get isDebuggingSupported => PlatformService.isCrashlyticsSupported;
  bool get isMacOS => PlatformService.isMacOS;
}
