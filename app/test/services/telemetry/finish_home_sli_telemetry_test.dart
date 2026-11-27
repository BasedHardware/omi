import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/services/telemetry/finish_home_sli_telemetry.dart';

void main() {
  test('persists a content-free cut before returning', () async {
    final now = DateTime.utc(2026, 11, 26, 1, 0);
    final store = MemoryTelemetryStore();
    final outbox = ClientTelemetryOutbox(
      store: store,
      clock: () => now,
      newId: () => '22222222-2222-4222-8222-222222222222',
    );
    final telemetry = FinishHomeSliTelemetry(
      outbox: outbox,
      clock: () => now,
      newId: () => '22222222-2222-4222-8222-222222222222',
      armFlushTimer: false,
    );
    telemetry.testFlightEnabled = () => true;
    telemetry.ownerId = () => 'owner';
    telemetry.platform = () => 'ios';

    await telemetry.recordCut(
      operationId: '11111111-1111-4111-8111-111111111111',
      source: 'app',
      occurredAt: now,
    );

    final pending = outbox.pending('owner');
    expect(pending, hasLength(1));
    expect(pending.single.family, 'finish_cut');
    expect(pending.single.occurredAt, now);
    expect(pending.single.attributes, {
      'operation_id': '11111111-1111-4111-8111-111111111111',
      'source': 'app',
    });
    expect(pending.single.wire, isNot(contains('owner')));
    expect((await store.read())!['owners'], isNotNull);
  });

  group('cold start: identity binds before the transport installs', () {
    final now = DateTime.utc(2026, 11, 26, 1, 0);
    const operationId = '11111111-1111-4111-8111-111111111111';
    late Directory directory;
    var ids = 0;
    String nextId() => '00000000-0000-4000-8000-${(ids++).toString().padLeft(12, '0')}';

    setUp(() async {
      directory = await Directory.systemTemp.createTemp('finish_home_sli_outbox');
    });
    tearDown(() async {
      await directory.delete(recursive: true);
    });

    /// One app process: the singleton's shape (in-memory store until install) with a fresh outbox.
    FinishHomeSliTelemetry launch() => FinishHomeSliTelemetry(
          outbox: ClientTelemetryOutbox(
            store: MemoryTelemetryStore(),
            clock: () => now,
            newId: nextId,
            delay: (_) async {},
          ),
          clock: () => now,
          newId: nextId,
          armFlushTimer: false,
          deferUntilInstalled: true,
        );

    FileTelemetryStore fileStore() =>
        FileTelemetryStore(() async => directory, fileName: 'finish_home_sli_outbox.json');

    void install(
      FinishHomeSliTelemetry telemetry, {
      required String? Function() owner,
      required TelemetryToken tokenFor,
      required TelemetryPost post,
    }) {
      telemetry.install(
        store: fileStore(),
        testFlightEnabled: () => true,
        ownerId: owner,
        platform: () => 'ios',
        tokenFor: tokenFor,
        post: post,
      );
    }

    Future<TelemetryHttpResult> unreachable({
      required String ownerId,
      required String token,
      required String body,
      required Duration timeout,
    }) async =>
        fail('offline: no request may be sent');

    test('a cut recorded offline survives a restart and is delivered after it', () async {
      // First process: AnalyticsManager.bindIdentity runs before installFinishHomeSliTelemetryTransport.
      final first = launch();
      first.onOwnerChanged(next: 'owner');
      // Startup awaits other work between the two (main.dart), so anything the bind scheduled has run.
      await first.outbox.settled;
      install(first, owner: () => 'owner', tokenFor: (_, {required forceRefresh}) async => null, post: unreachable);
      await first.outbox.settled;
      await first.recordCut(operationId: operationId, source: 'pendant', occurredAt: now);
      await first.outbox.settled;
      // Offline (no token): the cut stays queued, and it is on disk, not only in memory.
      expect(first.outbox.pending('owner'), hasLength(1));
      final persisted = await fileStore().read();
      expect(jsonEncode(persisted), contains(operationId));

      // Restart: a new process binds identity first again, then installs and comes online.
      final second = launch();
      second.onOwnerChanged(next: 'owner');
      await second.outbox.settled;
      final bodies = <String>[];
      install(
        second,
        owner: () => 'owner',
        tokenFor: (_, {required forceRefresh}) async => 'token',
        post: ({required ownerId, required token, required body, required timeout}) async {
          bodies.add(body);
          final batch = jsonDecode(body) as Map<String, dynamic>;
          return TelemetryHttpResult.http(
            statusCode: 200,
            body: jsonEncode({
              'batch_id': batch['batch_id'],
              'schema_version': 1,
              'accepted_count': (batch['observations'] as List).length,
              'duplicate_count': 0,
            }),
          );
        },
      );
      await second.outbox.settled;

      expect(bodies, hasLength(1));
      final observation = ((jsonDecode(bodies.single) as Map)['observations'] as List).single as Map;
      expect(observation['family'], 'finish_cut');
      expect(observation['attributes'], {'operation_id': operationId, 'source': 'pendant'});
      expect(second.outbox.pending('owner'), isEmpty);
      expect(jsonEncode(await fileStore().read()), isNot(contains(operationId)));
    });

    test('an owner change before install purges the previous owner once the store is attached', () async {
      final first = launch();
      first.onOwnerChanged(next: 'previous');
      await first.outbox.settled;
      install(first, owner: () => 'previous', tokenFor: (_, {required forceRefresh}) async => null, post: unreachable);
      await first.recordCut(operationId: operationId, source: 'app', occurredAt: now);
      await first.outbox.settled;
      expect(jsonEncode(await fileStore().read()), contains(operationId));

      final second = launch();
      second.onOwnerChanged(next: 'previous');
      second.onOwnerChanged(previous: 'previous', next: 'owner');
      await second.outbox.settled;
      expect(second.installed, isFalse);
      install(second, owner: () => 'owner', tokenFor: (_, {required forceRefresh}) async => null, post: unreachable);
      await second.outbox.settled;

      expect(second.outbox.pending('previous'), isEmpty);
      expect(second.outbox.dropCounts('previous'), {'owner_changed': 1});
      expect(jsonEncode(await fileStore().read()), isNot(contains(operationId)));
    });
  });
}
