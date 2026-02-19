import 'package:flutter/foundation.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/backend/http/api/announcements.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/providers/base_provider.dart';

class AnnouncementProvider extends BaseProvider {
  List<Announcement> _pendingAnnouncements = [];
  List<Announcement> get pendingAnnouncements => _pendingAnnouncements;

  /// Fetch pending announcements using the unified endpoint.
  /// This supports flexible targeting and per-user dismissal tracking.
  ///
  /// [trigger] should be one of:
  /// - 'app_launch': Check every app launch (for immediate announcements)
  /// - 'version_upgrade': Check only when app version changed
  /// - 'firmware_upgrade': Check only when firmware version changed
  Future<bool> fetchPendingAnnouncements({
    required String trigger,
    String? firmwareVersion,
    String? deviceModel,
  }) async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      final appVersion = '${packageInfo.version}+${packageInfo.buildNumber}';
      final platform = defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';

      _pendingAnnouncements = await getPendingAnnouncements(
        appVersion: appVersion,
        platform: platform,
        trigger: trigger,
        firmwareVersion: firmwareVersion,
        deviceModel: deviceModel,
      );

      notifyListeners();
      return _pendingAnnouncements.isNotEmpty;
    } catch (e) {
      debugPrint('Error fetching pending announcements: $e');
      return false;
    }
  }

  /// Mark an announcement as dismissed via the API.
  /// This persists the dismissal on the server for per-user tracking.
  Future<bool> markAnnouncementDismissed(String announcementId, {bool ctaClicked = false}) async {
    try {
      final success = await dismissAnnouncement(announcementId, ctaClicked: ctaClicked);
      if (success) {
        _pendingAnnouncements.removeWhere((a) => a.id == announcementId);
        notifyListeners();
      }
      return success;
    } catch (e) {
      debugPrint('Error dismissing announcement: $e');
      return false;
    }
  }

  /// Clear all pending announcements from local state.
  void clearPendingAnnouncements() {
    _pendingAnnouncements = [];
    notifyListeners();
  }
}
