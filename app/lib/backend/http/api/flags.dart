import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/flags_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// Flags owned by Omi's flag store for the signed-in account. Null on any failure, so callers keep PostHog.
/// Keys the store does not list are absent and keep reading PostHog.
Future<List<wire.GeneratedClientFlag>?> getOmiClientFlags() async {
  try {
    final res =
        await makeApiCall(url: '${Env.apiBaseUrl}v1/flags?surface=mobile', headers: {}, body: '', method: 'GET');
    if (res == null || res.statusCode != 200) return null;
    return wire.GeneratedClientFlagsResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).flags;
  } catch (_) {
    return null;
  }
}
