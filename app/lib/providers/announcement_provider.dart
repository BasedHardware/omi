import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/backend/http/api/announcements.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/providers/base_provider.dart';

class AnnouncementProvider extends BaseProvider {
  List<Announcement> _changelogs = [];
  List<Announcement> _features = [];
  List<Announcement> _generalAnnouncements = [];

  List<Announcement> get changelogs => _changelogs;
  List<Announcement> get features => _features;
  List<Announcement> get generalAnnouncements => _generalAnnouncements;

  bool _hasAppUpgrade = false;
  bool get hasAppUpgrade => _hasAppUpgrade;

  String _previousAppVersion = '';
  String _currentAppVersion = '';
  String get previousAppVersion => _previousAppVersion;
  String get currentAppVersion => _currentAppVersion;

  /// Check if the app was upgraded and load changelogs if needed.
  /// Returns true if there are changelogs to show.
  Future<bool> checkForAppUpgrade() async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      // Combine version and build number (e.g., "1.0.510+240")
      _currentAppVersion = '${packageInfo.version}+${packageInfo.buildNumber}';
      _previousAppVersion = SharedPreferencesUtil().lastKnownAppVersion;

      if (_previousAppVersion.isEmpty) {
        final isExistingUser = SharedPreferencesUtil().onboardingCompleted;

        if (!isExistingUser) {
          SharedPreferencesUtil().lastKnownAppVersion = _currentAppVersion;
          _hasAppUpgrade = false;
          return false;
        }

        _previousAppVersion = '1.0.520+598';
      }

      // Check if upgrade occurred
      if (_isNewerVersion(_currentAppVersion, _previousAppVersion)) {
        _hasAppUpgrade = true;

        _changelogs = await getAppChangelogs(limit: 5);

        final appFeatures = await getFeatureAnnouncements(
          version: _currentAppVersion,
          versionType: 'app',
        );
        _features = [..._features, ...appFeatures];

        // Update last known version
        SharedPreferencesUtil().lastKnownAppVersion = _currentAppVersion;
        notifyListeners();

        return _changelogs.isNotEmpty || appFeatures.isNotEmpty;
      }

      _hasAppUpgrade = false;
      return false;
    } catch (e) {
      debugPrint('Error checking for app upgrade: $e');
      return false;
    }
  }

  /// Check for firmware upgrade and load feature announcements.
  Future<bool> checkForFirmwareUpgrade(String currentFirmwareVersion, String deviceModel) async {
    try {
      if (currentFirmwareVersion.isEmpty || currentFirmwareVersion == 'Unknown') {
        return false;
      }

      final lastKnownFirmware = SharedPreferencesUtil().lastKnownFirmwareVersion;

      if (lastKnownFirmware.isEmpty) {
        SharedPreferencesUtil().lastKnownFirmwareVersion = currentFirmwareVersion;
        return false;
      }

      if (currentFirmwareVersion == lastKnownFirmware) {
        return false;
      }

      debugPrint('Firmware upgraded from $lastKnownFirmware to $currentFirmwareVersion');

      // Update stored version
      SharedPreferencesUtil().lastKnownFirmwareVersion = currentFirmwareVersion;

      // Fetch feature announcements for the new firmware version
      final firmwareFeatures = await getFeatureAnnouncements(
        version: currentFirmwareVersion,
        versionType: 'firmware',
        deviceModel: deviceModel,
      );

      if (firmwareFeatures.isNotEmpty) {
        _features = [..._features, ...firmwareFeatures];
        notifyListeners();
      }

      return firmwareFeatures.isNotEmpty;
    } catch (e) {
      debugPrint('Error checking for firmware upgrade: $e');
      return false;
    }
  }

  /// Check for general announcements (time-based, not version-gated).
  Future<bool> checkForGeneralAnnouncements() async {
    try {
      final lastChecked = SharedPreferencesUtil().lastAnnouncementCheckTime;
      _generalAnnouncements = await getGeneralAnnouncements(lastCheckedAt: lastChecked);
      notifyListeners();
      return _generalAnnouncements.isNotEmpty;
    } catch (e) {
      debugPrint('Error checking for general announcements: $e');
      return false;
    }
  }

  void markAnnouncementsAsSeen() {
    SharedPreferencesUtil().lastAnnouncementCheckTime = DateTime.now().toUtc();
    _generalAnnouncements.clear();
    notifyListeners();
  }

  /// Clear changelogs after user has viewed them.
  void clearChangelogs() {
    _changelogs = [];
    _hasAppUpgrade = false;
    notifyListeners();
  }

  /// Clear features after user has viewed them.
  void clearFeatures() {
    _features = [];
    notifyListeners();
  }

  /// Compare two version strings.
  /// Returns true if v1 is newer than v2.
  bool _isNewerVersion(String v1, String v2) {
    final t1 = _versionTuple(v1);
    final t2 = _versionTuple(v2);

    for (int i = 0; i < t1.length && i < t2.length; i++) {
      if (t1[i] > t2[i]) return true;
      if (t1[i] < t2[i]) return false;
    }

    return t1.length > t2.length;
  }

  /// Convert version string to list of integers.
  /// Supports formats:
  /// - "1.0.10" -> [1, 0, 10, 0]
  /// - "v1.0.10" -> [1, 0, 10, 0]
  /// - "1.0.510+240" -> [1, 0, 510, 240]
  List<int> _versionTuple(String version) {
    if (version.isEmpty) return [0, 0, 0, 0];

    // Remove 'v' prefix if present
    version = version.toLowerCase();
    if (version.startsWith('v')) {
      version = version.substring(1);
    }

    // Extract build number if present (e.g., '1.0.510+240')
    int buildNumber = 0;
    if (version.contains('+')) {
      final parts = version.split('+');
      version = parts[0];
      try {
        buildNumber = int.parse(parts[1]);
      } catch (e) {
        buildNumber = 0;
      }
    }

    try {
      final versionParts = version.split('.').map((p) => int.parse(p)).toList();
      // Pad to 3 components and add build number as 4th
      while (versionParts.length < 3) {
        versionParts.add(0);
      }
      versionParts.add(buildNumber);
      return versionParts;
    } catch (e) {
      return [0, 0, 0, 0];
    }
  }
}
