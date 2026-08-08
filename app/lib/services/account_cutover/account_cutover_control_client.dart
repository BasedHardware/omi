/// Fetches the authenticated account cutover control projection.
///
/// LIFECYCLE: permanent
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/utils/logger.dart';

enum AccountCutoverFetchKind {
  /// Parsed 200 control document.
  success,

  /// Server explicitly failed closed (503 / state-unavailable) or the body
  /// could not be parsed as a valid projection.
  unavailable,

  /// Transport / unexpected non-success without an explicit unavailable code.
  transportFailure,
}

class AccountCutoverFetchResult {
  const AccountCutoverFetchResult._(this.kind, {this.control});

  const AccountCutoverFetchResult.success(AccountCutoverControl control)
      : this._(AccountCutoverFetchKind.success, control: control);

  const AccountCutoverFetchResult.unavailable() : this._(AccountCutoverFetchKind.unavailable);

  const AccountCutoverFetchResult.transportFailure() : this._(AccountCutoverFetchKind.transportFailure);

  final AccountCutoverFetchKind kind;
  final AccountCutoverControl? control;
}

class AccountCutoverControlClient {
  AccountCutoverControlClient({
    Future<AccountCutoverFetchResult> Function()? fetch,
  }) : _fetch = fetch;

  final Future<AccountCutoverFetchResult> Function()? _fetch;

  Future<AccountCutoverFetchResult> fetchControl() async {
    try {
      return _fetch != null ? await _fetch!() : await _defaultFetch();
    } catch (e, st) {
      Logger.debug('Account cutover control fetch failed: $e\n$st');
      return const AccountCutoverFetchResult.transportFailure();
    }
  }

  Future<AccountCutoverFetchResult> _defaultFetch() async {
    final base = Env.apiBaseUrl;
    if (base == null || base.isEmpty) {
      return const AccountCutoverFetchResult.transportFailure();
    }
    final url = '${base.endsWith('/') ? base.substring(0, base.length - 1) : base}/v1/account/cutover/control';
    final response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');
    return interpretControlResponse(response);
  }

  /// Shared response classification for production and tests.
  static AccountCutoverFetchResult interpretControlResponse(http.Response? response) {
    if (response == null) {
      return const AccountCutoverFetchResult.transportFailure();
    }
    if (response.statusCode == 503) {
      return const AccountCutoverFetchResult.unavailable();
    }
    if (response.statusCode != 200) {
      return const AccountCutoverFetchResult.transportFailure();
    }

    try {
      final decoded = jsonDecode(response.body);
      final Map<String, dynamic>? json;
      if (decoded is Map<String, dynamic>) {
        json = decoded;
      } else if (decoded is Map) {
        json = Map<String, dynamic>.from(decoded);
      } else {
        return const AccountCutoverFetchResult.unavailable();
      }
      return AccountCutoverFetchResult.success(AccountCutoverControl.fromJson(json));
    } on AccountCutoverControlParseException catch (e) {
      Logger.debug('Account cutover control parse rejected: $e');
      return const AccountCutoverFetchResult.unavailable();
    } on FormatException catch (e) {
      Logger.debug('Account cutover control JSON rejected: $e');
      return const AccountCutoverFetchResult.unavailable();
    }
  }
}
