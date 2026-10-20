import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/debugging/non_fatal_reporter.dart';
import 'package:omi/backend/http/api/memories.dart';

void main() {
  test('recoverable failure is explicitly non-fatal and preserves backend health properties', () async {
    final attributes = <String, String>{};
    final error = Exception('Failed to fetch memories: 503 httpError');
    final stack = StackTrace.current;
    var records = 0;
    await recordNonFatalFailure(
      error,
      stack,
      attributes: {'response_status_code': '503', 'failure_reason': 'httpError'},
      setAttribute: (key, value) async => attributes[key] = value,
      record: (recordedError, recordedStack, {required fatal}) async {
        records++;
        expect(recordedError, same(error));
        expect(recordedStack, same(stack));
        expect(fatal, isFalse);
      },
    );
    expect(records, 1);
    expect(attributes, {'response_status_code': '503', 'failure_reason': 'httpError'});
  });

  test('failed attribute writes do not suppress the non-fatal event', () async {
    var records = 0;
    await recordNonFatalFailure(
      Exception('fetch'),
      StackTrace.current,
      attributes: {'response_status_code': '429', 'failure_reason': 'httpError'},
      setAttribute: (_, __) async => throw StateError('reporting unavailable'),
      record: (_, __, {required fatal}) async {
        expect(fatal, isFalse);
        records++;
      },
    );
    expect(records, 1);
  });

  test('failed diagnostics recording cannot become an uncaught asynchronous error', () async {
    await recordNonFatalFailure(
      Exception('fetch'),
      StackTrace.current,
      setAttribute: (_, __) async {},
      record: (_, __, {required fatal}) async => throw StateError('reporting unavailable'),
    );
  });

  test('memories failure writes one support line, one Product Error and one non-fatal record', () async {
    final logs = <String>[];
    final events = <Map<String, dynamic>>[];
    final records = <Map<String, String>>[];
    await reportMemoriesFetchFailure(
      const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError),
      supportLog: (line) async => logs.add(line),
      productError: events.add,
      nonFatal: (_, __, {required userAttributes}) async => records.add(userAttributes),
    );
    expect(logs, ['Failed to fetch memories: status=503 reason=httpError']);
    expect(events, [
      {
        'error': logs.single,
        'error_kind': 'memories_fetch',
        'diagnostic_source': 'memories_fetch',
        'response_status_code': '503',
        'failure_reason': 'httpError'
      },
    ]);
    expect(records, [
      {'response_status_code': '503', 'failure_reason': 'httpError'}
    ]);
  });

  test('failed support logging and analytics do not suppress the non-fatal record', () async {
    var records = 0;
    await reportMemoriesFetchFailure(
      const GetMemoriesResult([], true, statusCode: 429, failureReason: MemoriesFetchFailureReason.httpError),
      supportLog: (_) async => throw StateError('support log unavailable'),
      productError: (_) => throw StateError('analytics unavailable'),
      nonFatal: (_, __, {required userAttributes}) async {
        records++;
      },
    );
    expect(records, 1);
  });
}
