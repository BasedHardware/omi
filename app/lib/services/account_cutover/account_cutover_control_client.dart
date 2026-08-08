/// Fetches the authenticated account cutover control projection.
///
/// LIFECYCLE: permanent
library;

import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/utils/logger.dart';

class AccountCutoverControlClient {
  AccountCutoverControlClient({
    Future<Map<String, dynamic>?> Function()? fetchJson,
  }) : _fetchJson = fetchJson;

  final Future<Map<String, dynamic>?> Function()? _fetchJson;

  Future<AccountCutoverControl> fetchControl() async {
    try {
      final json = _fetchJson != null ? await _fetchJson!() : await _defaultFetch();
      if (json == null) {
        // Fail closed into maintenance only when the server explicitly said so.
        // Transport failures keep legacy-compatible traffic so bridge rollout
        // does not brick signed-in users before enforcement is enabled.
        return AccountCutoverControl.legacyDefault();
      }
      return AccountCutoverControl.fromJson(json);
    } catch (e, st) {
      Logger.debug('Account cutover control fetch failed: $e\n$st');
      return AccountCutoverControl.legacyDefault();
    }
  }

  Future<Map<String, dynamic>?> _defaultFetch() async {
    final base = Env.apiBaseUrl;
    if (base == null || base.isEmpty) return null;
    final url = '${base.endsWith('/') ? base.substring(0, base.length - 1) : base}/v1/account/cutover/control';
    final response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');
    if (response == null || response.statusCode != 200) return null;
    final decoded = jsonDecode(response.body);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
    return null;
  }
}
