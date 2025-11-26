import 'dart:io';
import 'package:desktop_updater/desktop_updater.dart';
import 'package:desktop_updater/updater_controller.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Service to manage desktop application updates for macOS/Windows/Linux
class DesktopUpdateService {
  static final DesktopUpdateService _instance = DesktopUpdateService._internal();
  factory DesktopUpdateService() => _instance;
  DesktopUpdateService._internal();

  DesktopUpdaterController? _controller;

  /// Get the platform name for the current OS
  String get _platform {
    if (Platform.isMacOS) return 'macos';
    if (Platform.isWindows) return 'windows';
    if (Platform.isLinux) return 'linux';
    return 'unknown';
  }

  /// Initialize the desktop updater controller
  /// Should be called once during app initialization
  void initialize() {
    // Only initialize on desktop platforms
    if (!PlatformService.isDesktop) {
      Logger.debug('Desktop updater not supported on this platform');
      return;
    }

    try {
      final baseUrl = Env.apiBaseUrl;
      final updateUrl = Uri.parse('$baseUrl/v2/desktop/app-archive.json?platform=$_platform');

      _controller = DesktopUpdaterController(
        appArchiveUrl: updateUrl,
        localization: const DesktopUpdateLocalization(
          updateAvailableText: 'A new version of Omi is available',
          newVersionAvailableText: 'New Version Available',
          newVersionLongText: 'A new version of Omi is available. Would you like to update now?',
          restartText: 'Restart Now',
          warningTitleText: 'Update Required',
          restartWarningText: 'This update requires the app to restart. Any unsaved changes will be lost.',
          warningCancelText: 'Later',
          warningConfirmText: 'Update Now',
          skipThisVersionText: 'Skip This Version',
          downloadText: 'Download Update',
        ),
      );

      Logger.debug('Desktop updater initialized for platform: $_platform');
    } catch (e, stackTrace) {
      Logger.handle(e, stackTrace, message: 'Failed to initialize desktop updater');
    }
  }

  /// Get the updater controller
  /// Returns null if not initialized or not on a desktop platform
  DesktopUpdaterController? get controller => _controller;

  /// Check if desktop updates are available
  bool get isAvailable => _controller != null;

  /// Dispose the controller when no longer needed
  void dispose() {
    _controller = null;
  }
}
