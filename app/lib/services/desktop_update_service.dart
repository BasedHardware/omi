import 'dart:io';
import 'package:auto_updater/auto_updater.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Service to manage desktop application updates using auto_updater
/// Uses native Sparkle (macOS) and WinSparkle (Windows)
class DesktopUpdateService {
  static final DesktopUpdateService _instance = DesktopUpdateService._internal();
  factory DesktopUpdateService() => _instance;
  DesktopUpdateService._internal();

  bool _initialized = false;

  String get _platform {
    if (Platform.isMacOS) return 'macos';
    if (Platform.isWindows) return 'windows';
    if (Platform.isLinux) return 'linux';
    return 'unknown';
  }

  /// Initialize auto_updater
  Future<void> initialize() async {
    if (!PlatformService.isDesktop) {
      Logger.debug('Desktop updater not supported on this platform');
      return;
    }

    if (_initialized) {
      Logger.debug('Desktop updater already initialized');
      return;
    }

    try {
      final baseUrl = Env.apiBaseUrl;
      final feedURL = '${baseUrl}v2/desktop/appcast.xml?platform=$_platform';

      // Configure auto_updater
      await autoUpdater.setFeedURL(feedURL);
      await autoUpdater.checkForUpdates();
      await autoUpdater.setScheduledCheckInterval(21600); // 6 hours

      _initialized = true;
      Logger.info('Auto updater initialized: $feedURL');
    } catch (e, stackTrace) {
      Logger.handle(e, stackTrace, message: 'Failed to initialize auto updater');
    }
  }

  /// Manually check for updates
  Future<void> checkForUpdates() async {
    if (!_initialized) {
      Logger.warning('Auto updater not initialized');
      return;
    }

    try {
      await autoUpdater.checkForUpdates();
    } catch (e, stackTrace) {
      Logger.handle(e, stackTrace, message: 'Failed to check for updates');
    }
  }

  bool get isAvailable => _initialized;
}
