import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_result.dart';
import '../support/spine/contract.dart';

void main() {
  contractTest('C3 malformed row cannot blank valid neighbors or escape through telemetry', () {
    final events = <ApiFallbackEvent>[];
    final result =
        decodeApiRows<int>('[{"n":1},{"private":"sensitive"},{"n":3}]', (row) => row['n'] as int, fallback: events.add);
    expect(result, isA<ApiSuccess<List<int>>>());
    final success = result as ApiSuccess<List<int>>;
    expect(success.data, [1, 3]);
    expect(success.rejectedRows, 1);
    expect(events, hasLength(1));
    expect(events.single.reason, ApiFallbackReason.partialDecode);
    expect(events.single.outcome, ApiFallbackOutcome.degraded);
    expect(events.single.toFields().toString(), isNot(contains('sensitive')));
    final view = presentApiResult(result, isEmpty: (List<int> values) => values.isEmpty, fallback: events.add);
    expect(view.phase, ApiViewPhase.data);
    expect(view.rejectedRows, 1);
    expect(events, hasLength(1)); // presentation must not double-count partial decoding
  });
  for (final body in ['bad-json', '{}', '[{}]', '[null,42,"private"]']) {
    contractTest('C3 $body is decode failure, never empty success or fallback', () {
      final events = <ApiFallbackEvent>[];
      final result = decodeApiRows<int>(body, (row) => row['n'] as int, fallback: events.add);
      expect((result as ApiFailure<List<int>>).problem.kind, ApiProblemKind.decode);
      expect(events, isEmpty);
    });
  }
  contractTest('C3 only valid empty success renders empty; stale data carries a visible error', () {
    final events = <ApiFallbackEvent>[];
    bool empty(List<int> rows) => rows.isEmpty;
    final success = decodeApiRows<int>('[]', (row) => row['n'] as int, fallback: events.add);
    expect(presentApiResult(success, isEmpty: empty).phase, ApiViewPhase.empty);
    for (final kind in ApiProblemKind.values) {
      final failure = ApiFailure<List<int>>(ApiProblem(kind));
      final first = presentApiResult(failure, isEmpty: empty, fallback: events.add);
      final expected = switch (kind) {
        ApiProblemKind.authTerminal => ApiViewPhase.authenticationRequired,
        ApiProblemKind.paymentRequired => ApiViewPhase.locked,
        ApiProblemKind.forbidden ||
        ApiProblemKind.notFound ||
        ApiProblemKind.unprocessable ||
        ApiProblemKind.rejected =>
          ApiViewPhase.terminal,
        _ => ApiViewPhase.error,
      };
      expect(first.phase, expected);
      expect(first.data, isNull);
      expect(first.problem!.kind, kind);
      expect(events, isEmpty); // hard failures are not fallbacks
    }
    final stale = presentApiResult(const ApiFailure<List<int>>(ApiProblem(ApiProblemKind.server)),
        previous: [7], isEmpty: empty, fallback: events.add);
    expect(stale.phase, ApiViewPhase.error);
    expect(stale.data, [7]);
    expect(stale.problem!.kind, ApiProblemKind.server);
    for (final kind in [
      ApiProblemKind.transport,
      ApiProblemKind.authTransient,
      ApiProblemKind.rateLimited,
      ApiProblemKind.decode
    ]) {
      final projected =
          presentApiResult(ApiFailure<List<int>>(ApiProblem(kind)), previous: [7], isEmpty: empty, fallback: (_) {});
      expect(projected.phase, ApiViewPhase.error);
      expect(projected.data, [7]);
      expect(projected.problem!.kind, kind);
    }
    expect(events.single.reason, ApiFallbackReason.staleData);
    expect(events.single.outcome, ApiFallbackOutcome.degraded);
  });
  contractTest('C3 terminal authorization and entitlement failures never render stale protected data', () {
    for (final kind in [
      ApiProblemKind.authTerminal,
      ApiProblemKind.forbidden,
      ApiProblemKind.paymentRequired,
      ApiProblemKind.notFound,
      ApiProblemKind.unprocessable,
      ApiProblemKind.rejected
    ]) {
      final events = <ApiFallbackEvent>[];
      final view = presentApiResult(ApiFailure<List<String>>(ApiProblem(kind)),
          previous: ['private-record'], isEmpty: (values) => values.isEmpty, fallback: events.add);
      expect(view.data, isNull);
      expect(events, isEmpty);
      expect(
          view.phase,
          kind == ApiProblemKind.authTerminal
              ? ApiViewPhase.authenticationRequired
              : kind == ApiProblemKind.paymentRequired
                  ? ApiViewPhase.locked
                  : ApiViewPhase.terminal);
    }
  });
  contractTest('C3 fallback emitter uses shared closed fields and one event', () {
    final emitted = <(String, Map<String, String>)>[];
    recordFallback(
        const ApiFallbackEvent(reason: ApiFallbackReason.partialDecode, outcome: ApiFallbackOutcome.degraded),
        emit: (name, fields) => emitted.add((name, fields)));
    expect(emitted, hasLength(1));
    expect(emitted.single.$1, 'fallback_triggered');
    expect(emitted.single.$2, {
      'component': 'other',
      'area': 'other',
      'from': 'none',
      'to': 'none',
      'reason': 'other',
      'outcome': 'degraded',
    });
  });
}
