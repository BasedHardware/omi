import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/announcement.dart';

Future<List<Announcement>> getAppChangelogs({
  String? fromVersion,
  String? toVersion,
  int limit = 5,
}) async {
  String url;
  if (fromVersion != null && toVersion != null) {
    final encodedFromVersion = Uri.encodeComponent(fromVersion);
    final encodedToVersion = Uri.encodeComponent(toVersion);
    url = "${Env.apiBaseUrl}v1/announcements/changelogs?from_version=$encodedFromVersion&to_version=$encodedToVersion";
  } else {
    url = "${Env.apiBaseUrl}v1/announcements/changelogs?limit=$limit";
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

/// Get feature announcements for a specific version.
/// For firmware updates: returns features explaining new device behavior.
/// For app updates: returns features explaining major new app functionality.
Future<List<Announcement>> getFeatureAnnouncements({
  required String version,
  required String versionType, // 'app' or 'firmware'
  String? deviceModel,
}) async {
  var url = "${Env.apiBaseUrl}v1/announcements/features?version=$version&version_type=$versionType";
  if (deviceModel != null) {
    url += "&device_model=$deviceModel";
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

/// Get active, non-expired general announcements.
/// Excludes announcements with IDs in excludeIds (already seen by user).
Future<List<Announcement>> getGeneralAnnouncements({
  List<String>? excludeIds,
}) async {
  var url = "${Env.apiBaseUrl}v1/announcements/general";
  if (excludeIds != null && excludeIds.isNotEmpty) {
    url += "?exclude_ids=${excludeIds.join(',')}";
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
