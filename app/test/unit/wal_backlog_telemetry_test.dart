import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/wal_backlog_telemetry.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('drop windows contain counts and closed reasons only, with no empty or duplicate emissions', () {
    final events = <RegisteredEvent>[];
    final telemetry = WalBacklogTelemetry(emit: events.add);
    telemetry.flushPendantDrops();
    expect(events, isEmpty);
    for (var i = 0; i < 3; i++) {
      telemetry.pendantFrameDropped(retentionReason: 'disk_reserve', storageWriteBlocked: false);
    }
    telemetry.pendantFrameDropped(retentionReason: 'disk_space_unknown', storageWriteBlocked: false);
    telemetry.pendantFrameDropped(retentionReason: 'count_cap', storageWriteBlocked: true);
    telemetry.pendantFrameDropped(retentionReason: 'count_cap', storageWriteBlocked: false);
    expect(events, isEmpty, reason: 'no SDK event per frame');
    telemetry.flushPendantDrops();
    expect(events.map((e) => e.wireName), everyElement('Pendant Frames Dropped'));
    expect(events.map((e) => e.properties), [
      {'count': 3, 'reason': 'disk_reserve'},
      {'count': 1, 'reason': 'disk_space_unknown'},
      {'count': 1, 'reason': 'storage_write_failed'},
      {'count': 1, 'reason': 'count_cap'},
    ]);
    telemetry.flushPendantDrops();
    expect(events, hasLength(4));
    telemetry.pendantFrameDropped(retentionReason: 'disk_reserve', storageWriteBlocked: true);
    telemetry.flushPendantDrops();
    expect(events.last.properties, {'count': 1, 'reason': 'disk_reserve'});
  });

  test('reconcile summaries distinguish real transients from local budget/cadence deferrals', () {
    final events = <RegisteredEvent>[];
    final telemetry = WalBacklogTelemetry(emit: events.add);
    telemetry.reconcilePass(backlogJobs: 5000, polledJobs: 18, transientJobs: 5, throttledJobs: 1);
    expect(events.single.wireName, 'WAL Reconcile Poll Summary');
    expect(events.single.properties, {
      'backlog_jobs': 5000,
      'polled_jobs': 18,
      'transient_jobs': 5,
      'throttled_jobs': 1,
      'missing_confirmation_jobs': 0,
      'locally_deferred_jobs': 4982,
    });
    telemetry.reconcilePass(backlogJobs: 5000, polledJobs: 0, transientJobs: 0, throttledJobs: 0);
    expect(events, hasLength(1), reason: 'budget-denied wakes never produce a stream of summary events');
    telemetry.reconcilePass(backlogJobs: 1, polledJobs: 1, transientJobs: 0, throttledJobs: 0);
    expect(events, hasLength(1), reason: 'routine successful/nonterminal polling is not rare-failure telemetry');
  });

  test('account cutover retires pending counters and emitter failures cannot affect producers', () {
    final events = <RegisteredEvent>[];
    final telemetry = WalBacklogTelemetry(emit: events.add);
    telemetry.pendantFrameDropped(retentionReason: 'disk_reserve', storageWriteBlocked: true);
    telemetry.clearUserData();
    telemetry.flushPendantDrops();
    expect(events, isEmpty);
    var attempts = 0;
    final failing = WalBacklogTelemetry(emit: (_) {
      attempts++;
      throw StateError('synthetic unavailable analytics');
    });
    failing.pendantFrameDropped(retentionReason: 'disk_reserve', storageWriteBlocked: true);
    expect(failing.flushPendantDrops, returnsNormally);
    expect(() => failing.reconcilePass(backlogJobs: 1, polledJobs: 1, transientJobs: 1, throttledJobs: 0),
        returnsNormally);
    failing.flushPendantDrops();
    expect(attempts, 2, reason: 'failed handoff is not retried per frame or duplicated in the next window');
  });
}
