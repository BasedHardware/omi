import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/debugging/instabug_manager.dart';
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
  InstabugManager get instabug => InstabugManager.instance;

  /// Initialize all platform services
  static Future<void> initializeServices() async {
    await MixpanelManager.init();
    await IntercomManager.instance.initIntercom();
    // Note: Instabug initialization is handled separately in main.dart
    // due to its specific initialization requirements
  }

  /// Check if analytics services are supported on current platform
  bool get isAnalyticsSupported => PlatformService.isAnalyticsSupported;

  /// Check if debugging services are supported on current platform
  bool get isDebuggingSupported => PlatformService.isInstabugSupported;

  /// Check if current platform is macOS
  bool get isMacOS => PlatformService.isMacOS;
}
