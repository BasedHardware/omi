import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
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

  /// Check for and display all pending announcements on app startup.
  /// Should be called after the user is authenticated and home screen is ready.
  Future<void> checkAndShowAnnouncements(
    BuildContext context,
    AnnouncementProvider provider, {
    BtDevice? connectedDevice,
  }) async {
    if (_isShowingAnnouncement) return;

    try {
      // 1. Check for app upgrade and show changelogs
      final hasAppUpgrade = await provider.checkForAppUpgrade();
      if (hasAppUpgrade && context.mounted) {
        await _showAppUpgradeAnnouncements(context, provider);
      }

      // 2. Check for firmware upgrade
      if (connectedDevice != null && context.mounted) {
        final hasFirmwareFeatures = await provider.checkForFirmwareUpgrade(
          connectedDevice.firmwareRevision,
          connectedDevice.modelNumber,
        );
        if (hasFirmwareFeatures && context.mounted) {
          await _showFeatureAnnouncements(context, provider);
        }
      }

      // 3. Check for general announcements
      if (context.mounted) {
        final hasAnnouncements = await provider.checkForGeneralAnnouncements();
        if (hasAnnouncements && context.mounted) {
          await _showGeneralAnnouncements(context, provider);
        }
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
      final hasFeatures = await provider.checkForFirmwareUpgrade(
        newFirmwareVersion,
        deviceModel,
      );

      if (hasFeatures && context.mounted) {
        await _showFeatureAnnouncements(context, provider);
      }
    } catch (e) {
      debugPrint('Error showing firmware announcements: $e');
    }
  }

  Future<void> _showAppUpgradeAnnouncements(
    BuildContext context,
    AnnouncementProvider provider,
  ) async {
    _isShowingAnnouncement = true;

    try {
      // Show feature announcements first (full screen, more important)
      if (provider.features.isNotEmpty) {
        for (final feature in provider.features.where((f) => f.appVersion != null)) {
          if (!context.mounted) break;
          await FeatureScreen.show(context, feature);
        }
      }

      // Then show changelogs (bottom sheet, less intrusive)
      if (provider.changelogs.isNotEmpty && context.mounted) {
        await ChangelogSheet.show(context, provider.changelogs);
      }

      provider.clearChangelogs();
      provider.clearFeatures();
    } finally {
      _isShowingAnnouncement = false;
    }
  }

  Future<void> _showFeatureAnnouncements(
    BuildContext context,
    AnnouncementProvider provider,
  ) async {
    _isShowingAnnouncement = true;

    try {
      for (final feature in provider.features.where((f) => f.firmwareVersion != null)) {
        if (!context.mounted) break;
        await FeatureScreen.show(context, feature);
      }

      provider.clearFeatures();
    } finally {
      _isShowingAnnouncement = false;
    }
  }

  Future<void> _showGeneralAnnouncements(
    BuildContext context,
    AnnouncementProvider provider,
  ) async {
    _isShowingAnnouncement = true;

    try {
      for (final announcement in List.from(provider.generalAnnouncements)) {
        if (!context.mounted) break;
        await AnnouncementDialog.show(context, announcement);
      }

      provider.markAnnouncementsAsSeen();
    } finally {
      _isShowingAnnouncement = false;
    }
  }
}
