import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/debugging/non_fatal_reporter.dart';

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
}
