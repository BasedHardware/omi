import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/dream_report.dart';
import 'package:omi/backend/schema/gen/dream_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// The caller's own dream-agent report and a run-now trigger. Both answer 404 unless the account
/// is in the dream cohort; the Review page hides the entry point on any failure.

Map<String, dynamic> _object(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return decoded;
}

Future<ApiResult<DreamReport>> getDreamReport({int limit = 10}) {
  return executeApi(
    request: ApiRequest(url: '${Env.apiBaseUrl}v1/dream/runs?limit=$limit', method: 'GET'),
    // Decode the wire contract once, then adapt typed fields for the screen.
    decode: (body) => DreamReport.fromGenerated(wire.GeneratedDreamRunsResponse.fromJson(_object(body))),
  );
}

/// Runs one pass now. An idle pass (nothing queued) comes back as a run with status idle.
Future<ApiResult<DreamRun>> runDreamNow() {
  return executeApi(
    request: ApiRequest(url: '${Env.apiBaseUrl}v1/dream/runs', method: 'POST', body: '{}'),
    decode: (body) => DreamRun.fromGenerated(wire.GeneratedDreamRun.fromJson(_object(body))),
  );
}

/// Maps a run-now failure to the two refusals the screen explains; anything else is a plain error.
DreamRunNowRefusal? dreamRunNowRefusal(ApiProblem problem) => switch (problem) {
      ApiProblem(kind: ApiProblemKind.rateLimited) => DreamRunNowRefusal.limit,
      ApiProblem(statusCode: 409) => DreamRunNowRefusal.inProgress,
      _ => null,
    };
