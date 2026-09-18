import 'api_result.dart';
import 'api_fallback.dart';

enum ApiViewPhase { data, empty, error, locked, terminal, authenticationRequired }

class ApiViewState<T> {
  const ApiViewState({required this.phase, this.data, this.problem, this.rejectedRows = 0});
  final ApiViewPhase phase;
  final T? data;
  final ApiProblem? problem;
  final int rejectedRows;
}

/// No scheduling/caching policy here: only projection of a completed request.
ApiViewState<T> presentApiResult<T>(ApiResult<T> result,
        {T? previous, required bool Function(T) isEmpty, void Function(ApiFallbackEvent)? fallback}) =>
    throw UnimplementedError('C3 error is never empty');
