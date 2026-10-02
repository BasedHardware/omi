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

  test('an empty filtered page still preserves the server continuation cursor', () {
    final result = memoriesResultFromHttp(
      statusCode: 200,
      body: '[]',
      nextCursor: 'cursor-2',
      beliefEnabled: true,
    );

    expect(result.ok, isTrue);
    expect(result.memories, isEmpty);
    expect(result.nextCursor, 'cursor-2');
    expect(result.beliefEnabled, isTrue);
  });

  test('memory cursor URL omits offset and preserves the server paging contract', () {
    final uri = Uri.parse(
      buildMemoriesListUrl(
        baseUrl: 'https://example.test/',
        limit: 100,
        offset: 500,
        cursor: 'cursor-2',
        thisDeviceOnly: true,
        view: MemoryReadView.usefulNow,
      ),
    );

    expect(uri.path, '/v3/memories');
    expect(uri.queryParameters, {
      'limit': '100',
      'cursor': 'cursor-2',
      'device_scope': 'current',
      'view': 'useful_now',
    });
  });

  test('ledger history URL uses offset paging for the initial request', () {
    final uri = Uri.parse(
      buildLedgerHistoryUrl(
        baseUrl: 'https://example.test/',
        limit: 500,
        offset: 500,
      ),
    );

    expect(uri.path, '/v3/memories/ledger-history');
    expect(uri.queryParameters, {'limit': '500', 'offset': '500'});
    expect(uri.queryParameters, isNot(contains('cursor')));
  });

  test('ledger history uses a server cursor when the route returns one', () {
    final uri = Uri.parse(
      buildLedgerHistoryUrl(
        baseUrl: 'https://example.test/',
        limit: 500,
        offset: 500,
        cursor: 'history-2',
      ),
    );

    expect(uri.path, '/v3/memories/ledger-history');
    expect(uri.queryParameters, {'limit': '500', 'cursor': 'history-2'});
    expect(uri.queryParameters, isNot(contains('offset')));
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
