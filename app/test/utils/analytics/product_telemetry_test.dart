import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

void main() {
  test('attempt links first visible result and exactly one terminal outcome', () {
    final events = <RegisteredEvent>[];
    var now = DateTime.utc(2026, 9, 22);
    final telemetry = ProductTelemetry(emit: events.add, now: () => now, identityEpoch: () => 1);
    final attempt = telemetry.start(ProductJourney.search, surface: ProductSurface.conversations);
    now = now.add(const Duration(milliseconds: 250));
    attempt.firstResult();
    attempt.firstResult();
    attempt.complete(ProductOutcome.empty, resultCount: 0);
    attempt.complete(ProductOutcome.failure, failure: ProductFailure.server);
    expect(events.map((e) => e.wireName),
        ['Product Journey Started', 'Product Journey First Result', 'Product Journey Outcome']);
    expect(events.map((e) => e.properties['correlation_id']).toSet(), {attempt.correlationId});
    expect(events.last.properties['outcome'], 'empty');
    expect(events.last.properties['duration_ms'], 250);
    expect(events.last.properties['result_count'], 0);
  });

  test('late result after account switch never belongs to the next user', () {
    final events = <RegisteredEvent>[];
    var epoch = 1;
    final telemetry = ProductTelemetry(emit: events.add, identityEpoch: () => epoch);
    final attempt = telemetry.start(ProductJourney.chatText);
    epoch++;
    attempt.firstResult();
    attempt.complete(ProductOutcome.success);
    expect(events, hasLength(1));
  });

  test('technical error is not a genuine empty result', () {
    final events = <RegisteredEvent>[];
    final telemetry = ProductTelemetry(emit: events.add, identityEpoch: () => 0);
    telemetry.start(ProductJourney.search).complete(ProductOutcome.failure, failure: ProductFailure.network);
    expect(events.last.properties['outcome'], 'failure');
    expect(events.last.properties['failure'], 'network');
    expect(events.last.properties['result_count'], -1);
  });

  test('record references reject content and joins preserve the real key', () {
    expect(RecordReference.fromId('private transcript with spaces'), isNull);
    expect(RecordReference.fromId('https://example.com'), isNull);
    expect(RecordReference.fromId(''), isNull);
    final events = <RegisteredEvent>[];
    ProductTelemetry(emit: events.add).value(ProductValue.resultViewed,
        objectId: RecordReference.fromId('conversation_123'), surface: ProductSurface.conversationDetail);
    expect(events.single.properties,
        {'kind': 'result_viewed', 'surface': 'conversation_detail', 'object_id': 'conversation_123'});
  });

  test('telemetry failure cannot break an operation', () {
    final telemetry = ProductTelemetry(emit: (_) => throw StateError('unavailable'));
    expect(() => telemetry.start(ProductJourney.capture).complete(ProductOutcome.success), returnsNormally);
  });
}
