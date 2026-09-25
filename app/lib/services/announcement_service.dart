import 'package:omi/utils/platform/platform_manager.dart';
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
import 'package:omi/ui/prompts/prompt_queue.dart';

/// Service that handles announcement detection and display.
/// Call this on app startup and after firmware updates.
///
/// Every announcement, feature screen and changelog is presented through [PromptQueue]: one at a
/// time, never while the reader is recording, on a call or updating firmware
/// (docs/ux-contract.md §14). An announcement is marked seen on the server only when the reader
/// answers it — its call to action, its close X or "Got It" — never on Not Now, system back or a
/// stray tap.
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
    _isShowingAnnouncement = true;

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
        final changelogs = await getAppChangelogs(fromVersion: lastKnownVersion, toVersion: currentVersion);
        if (changelogs.isNotEmpty) {
          PromptQueue.instance.enqueue(
            'changelog-$currentVersion',
            PromptPriority.normal,
            show: (context) async {
              PlatformManager.instance.analytics.changelogShown(
                changelogCount: changelogs.length,
                fromVersion: lastKnownVersion,
                toVersion: currentVersion,
              );
              await ChangelogSheet.show(context, changelogs);
              PlatformManager.instance.analytics.changelogDismissed(changelogCount: changelogs.length);
            },
          );
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
        _queuePendingAnnouncements(provider, PromptPriority.normal);
      }
    } catch (e) {
      debugPrint('Error checking announcements: $e');
    } finally {
      _isShowingAnnouncement = false;
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
        _queuePendingAnnouncements(provider, PromptPriority.high);
      }
    } catch (e) {
      debugPrint('Error showing firmware announcements: $e');
    }
  }

  /// Queues every pending announcement (the backend already sorts them by priority).
  /// Changelogs are handled separately via getAppChangelogs().
  void _queuePendingAnnouncements(AnnouncementProvider provider, int priority) {
    for (final Announcement announcement in List.of(provider.pendingAnnouncements)) {
      if (announcement.type == AnnouncementType.changelog) continue;
      PromptQueue.instance.enqueue(
        'announcement-${announcement.id}',
        priority,
        show: (context) => _present(context, provider, announcement),
      );
    }
  }

  Future<void> _present(BuildContext context, AnnouncementProvider provider, Announcement announcement) async {
    final typeName = announcement.type.toString().split('.').last;
    PlatformManager.instance.analytics.announcementShown(
      announcementId: announcement.id,
      type: typeName,
      priority: announcement.display?.priority,
    );

    final Future<AnnouncementOutcome> presented = switch (announcement.type) {
      AnnouncementType.changelog => Future.value(AnnouncementOutcome.none),
      AnnouncementType.feature => FeatureScreen.show(context, announcement),
      AnnouncementType.announcement => AnnouncementDialog.show(context, announcement),
    };
    final outcome = await presented;
    final ctaClicked = outcome == AnnouncementOutcome.cta;

    PlatformManager.instance.analytics.announcementDismissed(
      announcementId: announcement.id,
      type: typeName,
      ctaClicked: ctaClicked,
    );
    // Only an explicit answer marks it seen; Not Now and system back leave it pending so it comes
    // back next launch.
    if (outcome.marksSeen) {
      await provider.markAnnouncementDismissed(announcement.id, ctaClicked: ctaClicked);
    }
  }
}
