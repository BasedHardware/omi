import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/background_resource_telemetry.dart';

class MemoryCheckpoint implements BackgroundCheckpointStore {
  Map<String, Object>? value;
  @override
  Future<Map<String, Object>?> read() async => value;
  @override
  Future<void> write(Map<String, Object> checkpoint) async {
    value = checkpoint;
  }

  @override
  Future<void> clear() async {
    value = null;
  }
}

void main() {
  const snapshot = BackgroundResourceSnapshot(
      bleBytesReceived: 0,
      websocketBytesSent: 0,
      recordingState: 'record',
      deviceConnected: false,
      deviceType: 'phone',
      batchModeEnabled: true);
  test('unobserved process interruption reconciles once without claiming lost audio', () async {
    final store = MemoryCheckpoint();
    var now = DateTime.utc(2026, 9, 22);
    final events = <Map<String, dynamic>>[];
    BackgroundResourceTelemetry create(String owner) => BackgroundResourceTelemetry(
        emit: (_, p) => events.add(p), checkpointStore: store, now: () => now, ownerKey: () => owner);
    final first = create('alice');
    first.onPaused(snapshot);
    // Await serialization without completing the background interval.
    await Future<void>.delayed(Duration.zero);
    now = now.add(const Duration(minutes: 5));
    final next = create('alice');
    await next.recoverInterrupted();
    await next.recoverInterrupted();
    expect(events, hasLength(1));
    expect(events.single['observation_state'], 'unobserved');
    expect(events.single, isNot(contains('owner')));
    expect(store.value, isNull);
    create('alice').onPaused(snapshot);
    await Future<void>.delayed(Duration.zero);
    await create('bob').recoverInterrupted();
    expect(events, hasLength(1));
    expect(store.value, isNull);
  });
  test('A to B to A while resume snapshot loads does not attribute the old interval', () async {
    var epoch = 1;
    var now = DateTime.utc(2026, 9, 22);
    final store = MemoryCheckpoint();
    final events = <Map<String, dynamic>>[];
    final telemetry = BackgroundResourceTelemetry(
        emit: (_, props) => events.add(props),
        checkpointStore: store,
        ownerKey: () => 'alice',
        identityEpoch: () => epoch,
        now: () => now);
    telemetry.onPaused(snapshot);
    await Future<void>.delayed(Duration.zero);
    now = now.add(const Duration(minutes: 2));
    final response = Completer<BackgroundResourceSnapshot>();
    final started = Completer<void>();
    final resumed = telemetry.onResumed((_, __) {
      started.complete();
      return response.future;
    });
    await started.future;
    epoch += 2;
    response.complete(snapshot);
    await resumed;
    expect(events, isEmpty);
    expect(store.value, isNull);
  });

  test('recovery rechecks generation after storage read completes', () async {
    var epoch = 1;
    final store = DelayedReadCheckpoint()
      ..value = {
        'owner': 'alice',
        'background_session_id': 'previous-session',
        'started_at': '2026-09-22T00:00:00Z',
        'recording_state': 'record',
      };
    final events = <Map<String, dynamic>>[];
    final telemetry = BackgroundResourceTelemetry(
        emit: (_, props) => events.add(props),
        checkpointStore: store,
        ownerKey: () => 'alice',
        identityEpoch: () => epoch,
        now: () => DateTime.utc(2026, 9, 22, 1));
    final recovered = telemetry.recoverInterrupted();
    await store.started.future;
    epoch += 2;
    store.release.complete();
    await recovered;
    expect(events, isEmpty);
    expect(store.value, isNull);
  });

  test('withdrawn consent suppresses queued writes and pending resume observations', () async {
    var enabled = true;
    var now = DateTime.utc(2026, 9, 22);
    final store = MemoryCheckpoint();
    final events = <Map<String, dynamic>>[];
    final telemetry = BackgroundResourceTelemetry(
        emit: (_, props) => events.add(props),
        checkpointStore: store,
        ownerKey: () => 'alice',
        enabled: () => enabled,
        now: () => now);
    telemetry.onPaused(snapshot);
    enabled = false;
    await Future<void>.delayed(Duration.zero);
    expect(store.value, isNull);
    now = now.add(const Duration(minutes: 2));
    var called = false;
    await telemetry.onResumed((_, __) async {
      called = true;
      return snapshot;
    });
    expect(called, false);
    expect(events, isEmpty);
  });

  test('a pending checkpoint write cannot restore consent-revoked data', () async {
    var enabled = true;
    var epoch = 1;
    final store = DelayedWriteCheckpoint();
    final telemetry = BackgroundResourceTelemetry(
        emit: (_, __) {},
        checkpointStore: store,
        ownerKey: () => 'alice',
        enabled: () => enabled,
        identityEpoch: () => epoch);
    telemetry.onPaused(snapshot);
    await store.started.future;
    enabled = false;
    epoch++;
    await store.clear();
    store.release.complete();
    // Drain the service's write/cleanup chain via its serialized recovery.
    await telemetry.recoverInterrupted();
    expect(store.value, isNull);
    expect(store.staleValueRead, false);
  });

  test('diagnostic transport failures cannot fail resume or interrupted recovery', () async {
    var now = DateTime.utc(2026, 9, 22);
    final store = MemoryCheckpoint();
    final telemetry = BackgroundResourceTelemetry(
        emit: (_, __) => throw StateError('synthetic failure'),
        checkpointStore: store,
        ownerKey: () => 'alice',
        now: () => now);
    telemetry.onPaused(snapshot);
    await Future<void>.delayed(Duration.zero);
    now = now.add(const Duration(minutes: 2));
    await expectLater(telemetry.onResumed((_, __) async => snapshot), completes);
    store.value = {'owner': 'alice', 'background_session_id': 'old', 'started_at': '2026-09-22T00:00:00Z'};
    await expectLater(telemetry.recoverInterrupted(), completes);
    expect(store.value, isNull);
  });
}

class DelayedReadCheckpoint extends MemoryCheckpoint {
  final started = Completer<void>();
  final release = Completer<void>();
  @override
  Future<Map<String, Object>?> read() async {
    started.complete();
    await release.future;
    return value;
  }
}

class DelayedWriteCheckpoint extends MemoryCheckpoint {
  final started = Completer<void>();
  final release = Completer<void>();
  bool staleValueRead = false;
  @override
  Future<void> write(Map<String, Object> checkpoint) async {
    started.complete();
    await release.future;
    value = checkpoint;
  }

  @override
  Future<Map<String, Object>?> read() async {
    staleValueRead = value != null;
    return value;
  }
}
