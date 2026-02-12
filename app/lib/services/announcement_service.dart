import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/backend/http/api/announcements.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/announcements/changelog_sheet.dart';
import 'package:omi/pages/announcements/feature_screen.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

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
      // Check if app version changed
      final lastKnownVersion = SharedPreferencesUtil().lastKnownAppVersion;
      final packageInfo = await PackageInfo.fromPlatform();
      final currentVersion = '${packageInfo.version}+${packageInfo.buildNumber}';

      final isVersionUpgrade = lastKnownVersion.isNotEmpty && currentVersion != lastKnownVersion;
      final isFreshInstall = lastKnownVersion.isEmpty;

      // Update stored version
      if (isVersionUpgrade || isFreshInstall) {
        SharedPreferencesUtil().lastKnownAppVersion = currentVersion;
      }

      // Skip announcements for fresh installs
      if (isFreshInstall) {
        return;
      }

      // 1. Show changelogs on version upgrade (fetched separately)
      if (isVersionUpgrade && context.mounted) {
        final changelogs = await getAppChangelogs(
          fromVersion: lastKnownVersion,
          toVersion: currentVersion,
        );
        if (changelogs.isNotEmpty && context.mounted) {
          _isShowingAnnouncement = true;
          try {
            MixpanelManager().changelogShown(
              changelogCount: changelogs.length,
              fromVersion: lastKnownVersion,
              toVersion: currentVersion,
            );
            await ChangelogSheet.show(context, changelogs);
            MixpanelManager().changelogDismissed(changelogCount: changelogs.length);
          } finally {
            _isShowingAnnouncement = false;
          }
        }
      }

      // 2. Fetch and show other pending announcements (features, promos)
      final trigger = isVersionUpgrade ? 'version_upgrade' : 'app_launch';
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
  /// Note: Changelogs are handled separately via getAppChangelogs().
  Future<void> _showPendingAnnouncements(
    BuildContext context,
    AnnouncementProvider provider,
  ) async {
    _isShowingAnnouncement = true;

    try {
      // Announcements are already sorted by priority from the backend
      for (final announcement in List.from(provider.pendingAnnouncements)) {
        if (!context.mounted) break;

        if (announcement.type == AnnouncementType.changelog) {
          continue;
        }

        final typeName = announcement.type.toString().split('.').last;

        // Track announcement shown
        MixpanelManager().announcementShown(
          announcementId: announcement.id,
          type: typeName,
          priority: announcement.display?.priority,
        );

        // Show based on announcement type
        bool ctaClicked = false;
        switch (announcement.type) {
          case AnnouncementType.changelog:
            break;
          case AnnouncementType.feature:
            await FeatureScreen.show(context, announcement);
            break;
          case AnnouncementType.announcement:
            ctaClicked = await AnnouncementDialog.show(context, announcement);
            break;
        }

        // Track dismissal and mark as dismissed
        MixpanelManager().announcementDismissed(
          announcementId: announcement.id,
          type: typeName,
          ctaClicked: ctaClicked,
        );
        await provider.markAnnouncementDismissed(announcement.id, ctaClicked: ctaClicked);
      }
    } finally {
      _isShowingAnnouncement = false;
    }
  }
}
