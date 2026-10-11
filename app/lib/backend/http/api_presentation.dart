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

bool _hidesProtectedData(ApiProblemKind kind) => switch (kind) {
      ApiProblemKind.authTerminal ||
      ApiProblemKind.forbidden ||
      ApiProblemKind.paymentRequired ||
      ApiProblemKind.notFound ||
      ApiProblemKind.unprocessable ||
      ApiProblemKind.rejected =>
        true,
      _ => false,
    };

ApiViewPhase _phaseForFailure(ApiProblemKind kind) => switch (kind) {
      ApiProblemKind.authTerminal => ApiViewPhase.authenticationRequired,
      ApiProblemKind.paymentRequired => ApiViewPhase.locked,
      ApiProblemKind.forbidden ||
      ApiProblemKind.notFound ||
      ApiProblemKind.unprocessable ||
      ApiProblemKind.rejected =>
        ApiViewPhase.terminal,
      _ => ApiViewPhase.error,
    };

/// No scheduling/caching policy here: only projection of a completed request.
ApiViewState<T> presentApiResult<T>(
  ApiResult<T> result, {
  T? previous,
  required bool Function(T) isEmpty,
  void Function(ApiFallbackEvent)? fallback,
}) {
  switch (result) {
    case ApiSuccess<T>(:final data, :final rejectedRows):
      return ApiViewState(
        phase: isEmpty(data) ? ApiViewPhase.empty : ApiViewPhase.data,
        data: data,
        rejectedRows: rejectedRows,
      );
    case ApiFailure<T>(:final problem):
      if (previous != null && !_hidesProtectedData(problem.kind)) {
        fallback?.call(
          const ApiFallbackEvent(reason: ApiFallbackReason.staleData, outcome: ApiFallbackOutcome.degraded),
        );
        return ApiViewState(phase: ApiViewPhase.error, data: previous, problem: problem);
      }
      return ApiViewState(phase: _phaseForFailure(problem.kind), problem: problem);
  }
}
