import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/announcements/changelog_sheet.dart';
import 'package:omi/pages/announcements/feature_screen.dart';
import 'package:omi/providers/announcement_provider.dart';

/// Service that handles announcement detection and display.
/// Call this on app startup and after firmware updates.
class AnnouncementService {
  static final AnnouncementService _instance = AnnouncementService._internal();
  factory AnnouncementService() => _instance;
  AnnouncementService._internal();

  bool _isShowingAnnouncement = false;

  /// Check for and display pending announcements on app startup.
  /// Should be called after the user is authenticated and home screen is ready.
  Future<void> checkAndShowAnnouncements(
    BuildContext context,
    AnnouncementProvider provider, {
    BtDevice? connectedDevice,
  }) async {
    if (_isShowingAnnouncement) return;

    try {
      // Determine the trigger type based on version changes
      String trigger = 'app_launch';

      // Check if app version changed
      final prefs = await SharedPreferences.getInstance();
      final lastKnownVersion = prefs.getString('lastKnownAppVersion') ?? '';
      final packageInfo = await PackageInfo.fromPlatform();
      final currentVersion = '${packageInfo.version}+${packageInfo.buildNumber}';

      if (lastKnownVersion.isNotEmpty && currentVersion != lastKnownVersion) {
        trigger = 'version_upgrade';
        await prefs.setString('lastKnownAppVersion', currentVersion);
      } else if (lastKnownVersion.isEmpty) {
        await prefs.setString('lastKnownAppVersion', currentVersion);
      }

      // Fetch pending announcements
      final hasAnnouncements = await provider.fetchPendingAnnouncements(
        trigger: trigger,
        firmwareVersion: connectedDevice?.firmwareRevision,
        deviceModel: connectedDevice?.modelNumber,
      );

      if (hasAnnouncements && context.mounted) {
        await _showPendingAnnouncements(context, provider);
      }
    } catch (e) {
      debugPrint('Error checking announcements: $e');
    }
  }

  /// Show announcements after a firmware update completes.
  Future<void> showFirmwareUpdateAnnouncements(
    BuildContext context,
    AnnouncementProvider provider,
    String newFirmwareVersion,
    String deviceModel,
  ) async {
    if (_isShowingAnnouncement) return;

    try {
      final hasAnnouncements = await provider.fetchPendingAnnouncements(
        trigger: 'firmware_upgrade',
        firmwareVersion: newFirmwareVersion,
        deviceModel: deviceModel,
      );

      if (hasAnnouncements && context.mounted) {
        await _showPendingAnnouncements(context, provider);
      }
    } catch (e) {
      debugPrint('Error showing firmware announcements: $e');
    }
  }

  /// Display all pending announcements in priority order.
  /// Announcements are automatically marked as dismissed after being shown.
  Future<void> _showPendingAnnouncements(
    BuildContext context,
    AnnouncementProvider provider,
  ) async {
    _isShowingAnnouncement = true;

    try {
      // Announcements are already sorted by priority from the backend
      for (final announcement in List.from(provider.pendingAnnouncements)) {
        if (!context.mounted) break;

        // Show based on announcement type
        switch (announcement.type) {
          case AnnouncementType.changelog:
            await ChangelogSheet.show(context, [announcement]);
            break;
          case AnnouncementType.feature:
            await FeatureScreen.show(context, announcement);
            break;
          case AnnouncementType.announcement:
            await AnnouncementDialog.show(context, announcement);
            break;
        }

        // Mark as dismissed after showing
        await provider.markAnnouncementDismissed(announcement.id);
      }
    } finally {
      _isShowingAnnouncement = false;
    }
  }
}
