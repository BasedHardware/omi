import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/memories.dart';

void main() {
  test('a 503 is a failed result, not an empty success', () {
    const body = '{"detail":"Historical memory unavailable"}';
    final result = memoriesResultFromHttp(statusCode: 503, body: body);

    expect(result.ok, isFalse, reason: 'a 503 must not be presented as a successful empty list');
    expect(result.memories, isEmpty);
    expect(result.failureReason, MemoriesFetchFailureReason.httpError);
    expect(result.statusCode, 503);
  });

  test('a 200 with an empty list is a genuine empty account', () {
    final result = memoriesResultFromHttp(statusCode: 200, body: '[]');

    expect(result.ok, isTrue);
    expect(result.memories, isEmpty);
    expect(result.failureReason, isNull);
  });

  test('a missing response is a failed result, not an empty success', () {
    final result = memoriesResultFromHttp(statusCode: null, body: null);

    expect(result.ok, isFalse);
    expect(result.failureReason, MemoriesFetchFailureReason.noResponse);
    expect(result.memories, isEmpty);
  });

  test('thisDeviceOnly plus a 503 is still a fetch failure, not unsupported device_scope', () {
    final result = memoriesResultFromHttp(statusCode: 503, body: 'unavailable');

    expect(result.ok, isFalse);
    expect(result.failureReason, MemoriesFetchFailureReason.httpError);
    expect(
      result.deviceScopeSupported,
      isTrue,
      reason: 'a 503 must not flip deviceScopeSupported; that flag is only for the 400 fallback',
    );
  });

  test('a 200 body that cannot be decoded is a failed result, not an empty success', () {
    final result = memoriesResultFromHttp(statusCode: 200, body: 'not-json');

    expect(result.ok, isFalse);
    expect(result.failureReason, MemoriesFetchFailureReason.decodeError);
    expect(result.memories, isEmpty);
  });
}
