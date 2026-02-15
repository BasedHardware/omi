import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/announcement.dart';

/// Get app changelogs.
///
/// If [fromVersion] and [toVersion] are provided, returns changelogs between those versions.
/// Otherwise returns the most recent [limit] changelogs (for "What's New" in settings).
Future<List<Announcement>> getAppChangelogs({
  String? fromVersion,
  String? toVersion,
  String? maxVersion,
  int limit = 5,
}) async {
  String url;
  if (fromVersion != null && toVersion != null) {
    final encodedFrom = Uri.encodeComponent(fromVersion);
    final encodedTo = Uri.encodeComponent(toVersion);
    url = "${Env.apiBaseUrl}v1/announcements/changelogs?from_version=$encodedFrom&to_version=$encodedTo";
  } else {
    url = "${Env.apiBaseUrl}v1/announcements/changelogs?limit=$limit";
    if (maxVersion != null) {
      url += "&max_version=${Uri.encodeComponent(maxVersion)}";
    }
  }

  var res = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );

  if (res == null || res.statusCode != 200) {
    return [];
  }

  final List<dynamic> data = jsonDecode(res.body);
  return data.map((json) => Announcement.fromJson(json)).toList();
}

/// Get all pending announcements for the current user.
/// This endpoint supports flexible targeting and per-user dismissal tracking.
///
/// [trigger] should be one of:
/// - 'app_launch': Check every app launch (for immediate announcements)
/// - 'version_upgrade': Check only when app version changed
/// - 'firmware_upgrade': Check only when firmware version changed
Future<List<Announcement>> getPendingAnnouncements({
  required String appVersion,
  required String platform,
  required String trigger,
  String? firmwareVersion,
  String? deviceModel,
}) async {
  final encodedAppVersion = Uri.encodeComponent(appVersion);
  var url = "${Env.apiBaseUrl}v1/announcements/pending"
      "?app_version=$encodedAppVersion"
      "&platform=$platform"
      "&trigger=$trigger";

  if (firmwareVersion != null) {
    url += "&firmware_version=${Uri.encodeComponent(firmwareVersion)}";
  }
  if (deviceModel != null) {
    url += "&device_model=${Uri.encodeComponent(deviceModel)}";
  }

  var res = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );

  if (res == null || res.statusCode != 200) {
    return [];
  }

  final List<dynamic> data = jsonDecode(res.body);
  return data.map((json) => Announcement.fromJson(json)).toList();
}

/// Dismiss an announcement for the current user.
/// This prevents the announcement from being shown again if show_once is true.
Future<bool> dismissAnnouncement(String announcementId, {bool ctaClicked = false}) async {
  final url = "${Env.apiBaseUrl}v1/announcements/$announcementId/dismiss";

  var res = await makeApiCall(
    url: url,
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'cta_clicked': ctaClicked}),
    method: 'POST',
  );

  return res != null && res.statusCode == 200;
}
