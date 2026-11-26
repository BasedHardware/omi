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
}
