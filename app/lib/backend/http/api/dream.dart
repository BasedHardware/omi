import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/dream_report.dart';
import 'package:omi/env/env.dart';

/// The caller's own dream-agent report and a run-now trigger. Both answer 404 unless the account
/// is in the dream cohort; the Review page hides the entry point on any failure.

Future<ApiResult<DreamReport>> getDreamReport({int limit = 10}) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/dream/runs?limit=$limit', method: 'GET'),
      // The generated decoder enforces the wire contract; the screen keeps its own lenient model.
      decode: DreamReport.fromGeneratedWireJson,
    );

/// Runs one pass now. An idle pass (nothing queued) comes back as a run with status idle.
Future<ApiResult<DreamRun>> runDreamNow() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/dream/runs', method: 'POST', body: '{}'),
      decode: DreamRun.fromGeneratedWireJson,
    );

/// Maps a run-now failure to the two refusals the screen explains; anything else is a plain error.
DreamRunNowRefusal? dreamRunNowRefusal(ApiProblem problem) => switch (problem) {
      ApiProblem(kind: ApiProblemKind.rateLimited) => DreamRunNowRefusal.limit,
      ApiProblem(statusCode: 409) => DreamRunNowRefusal.inProgress,
      _ => null,
    };
