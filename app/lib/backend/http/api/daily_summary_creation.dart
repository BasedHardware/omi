import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/services/auth_service.dart';

/// The shared date-based creation endpoint also returns an existing recap.
/// It needs no push token and never replaces recordings or an existing recap.
class DailySummaryCreationApi {
  const DailySummaryCreationApi({this.send, this.execution, this.auth, this.baseUrl});

  final ApiSend? send;
  final ApiExecutionSeams? execution;
  final AuthService? auth;
  final String? baseUrl;

  Future<ApiResult<DailySummary>> create(String date) async {
    // A supplied send is already-authenticated test I/O. Production and raw
    // execution use the same session authority as every other HTTP request.
    final authority = auth ?? execution?.auth ?? (send == null ? AuthService.instance : null);
    final session = authority?.captureSessionSnapshot();
    bool current() => authority == null || (session != null && authority.isSessionSnapshotCurrent(session));
    final base = baseUrl ?? Env.apiBaseUrl ?? '';
    final root = base.endsWith('/') ? base : '$base/';
    final result = await executeApi<DailySummary>(
      request: ApiRequest(
        url: '${root}v1/users/daily-summaries',
        method: 'POST',
        body: jsonEncode({'date': date}),
      ),
      send: send,
      execution: execution,
      canSend: current,
      decode: (body) => _decode(body, date),
    );
    return current() ? result : const ApiFailure(ApiProblem(ApiProblemKind.authTerminal));
  }

  static DailySummary _decode(String body, String requestedDate) {
    final Object? value = jsonDecode(body);
    if (value is! Map<String, dynamic> ||
        value['id'] is! String ||
        (value['id'] as String).isEmpty ||
        value['date'] != requestedDate) {
      throw const FormatException('Invalid daily recap response');
    }
    try {
      return DailySummary.fromGenerated(wire.GeneratedDailySummaryResponse.fromJson(value));
    } on TypeError {
      throw const FormatException('Invalid daily recap response');
    }
  }
}
