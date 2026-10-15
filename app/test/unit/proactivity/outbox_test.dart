import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/services/proactivity/proactivity_outbox.dart';
import '../../helpers/proactivity_fakes.dart';

void main() {
  test('offline/503 retries retain UUID, wire shape and no content analytics', () async {
    var online = false;
    final h = OutcomeHarness(
      send: (_, __) async =>
          online ? outcomeSuccess : const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503)),
    );
    addTearDown(h.outbox.dispose);
    await h.bind();
    await h.outbox.record('item-1', ProactivityAction.opened);
    await Future<void>.delayed(Duration.zero);
    expect(h.outbox.pendingCount, 1);
    final original = h.events.single;
    expect(original.eventId, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')));
    online = true;
    await h.outbox.flush();
    expect(h.events.last.eventId, original.eventId);
    expect(h.outbox.pendingCount, 0);
    expect(h.analytics.single.keys, unorderedEquals(['action', 'channel', 'surface']));
    expect(original.toJson().keys, unorderedEquals(['action', 'channel', 'surface', 'event_id']));
  });

  test('timer retries transport failure with identical event ID', () async {
    var calls = 0;
    final h = OutcomeHarness(
      retryDelay: const Duration(milliseconds: 10),
      send: (_, __) async => ++calls == 1 ? const ApiFailure(ApiProblem(ApiProblemKind.transport)) : outcomeSuccess,
    );
    addTearDown(h.outbox.dispose);
    await h.bind();
    await h.outbox.record('item-1', ProactivityAction.thumbsUp);
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(h.events, hasLength(2));
    expect(h.events.last.eventId, h.events.first.eventId);
    expect(h.outbox.pendingCount, 0);
  });

  test('restart restores pending IDs and shown receipts only for same owner', () async {
    final a = OutcomeHarness(send: (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
    await a.bind();
    await a.outbox.record('item-1', ProactivityAction.shown);
    await Future<void>.delayed(Duration.zero);
    final b = OutcomeHarness()..saved = a.saved;
    a.outbox.dispose();
    addTearDown(b.outbox.dispose);
    await b.bind();
    await Future<void>.delayed(Duration.zero);
    expect(b.events.single.eventId, a.events.single.eventId);
    await b.outbox.record('item-1', ProactivityAction.shown);
    expect(b.events, hasLength(1));
    await b.bind('owner-b');
    expect(b.outbox.pendingCount, 0);
    expect(jsonDecode(b.saved)['owner'], 'owner-b');
  });

  test('sign-out purges durable data and late completion cannot affect new account', () async {
    final blocked = Completer<ApiResult<GeneratedProactivityOutcomeResponse>>();
    final h = OutcomeHarness(send: (_, __) => blocked.future);
    addTearDown(h.outbox.dispose);
    await h.bind();
    await h.outbox.record('item-1', ProactivityAction.producerDisabled, producer: 'producer-a');
    await Future<void>.delayed(Duration.zero);
    await h.bind(null);
    expect(h.saved, '');
    expect(h.outbox.pendingCount, 0);
    expect(h.outbox.disabledProducers, isEmpty);
    await h.bind('owner-b');
    blocked.complete(outcomeSuccess);
    await Future<void>.delayed(Duration.zero);
    expect(h.outbox.pendingCount, 0);
    expect(jsonDecode(h.saved)['owner'], 'owner-b');
  });

  test('terminal 404 is dropped and corrupt storage is purged', () async {
    final h = OutcomeHarness(
      send: (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404)),
    )..saved = '{broken';
    addTearDown(h.outbox.dispose);
    await h.bind();
    await h.outbox.record('missing', ProactivityAction.opened);
    await Future<void>.delayed(Duration.zero);
    expect(h.outbox.pendingCount, 0);
    expect(ProactivityAction.values.map((a) => a.wire), isNot(contains('timeout')));
  });
  test('outbox is bounded to 100 receipts while offline', () async {
    final h = OutcomeHarness(send: (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
    addTearDown(h.outbox.dispose);
    await h.bind();
    for (var i = 0; i < 120; i++) {
      await h.outbox.record('item-$i', ProactivityAction.shown);
    }
    expect(h.outbox.pendingCount, 100);
    expect((jsonDecode(h.saved)['pending'] as List), hasLength(100));
  });
  test('conflicting 409 event is terminal and never minted anew', () async {
    final h = OutcomeHarness(
      send: (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409)),
    );
    addTearDown(h.outbox.dispose);
    await h.bind();
    await h.outbox.record('item-1', ProactivityAction.opened);
    await Future<void>.delayed(Duration.zero);
    await h.outbox.flush();
    expect(h.events, hasLength(1));
    expect(h.outbox.pendingCount, 0);
  });
}
