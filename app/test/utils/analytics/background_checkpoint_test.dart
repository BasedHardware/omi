import 'dart:async';
import 'dart:convert';
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

  test('checkpoint round-trips origin build and git sha through json', () async {
    final store = MemoryCheckpoint();
    final now = DateTime.utc(2026, 10, 9);
    final telemetry = BackgroundResourceTelemetry(
      emit: (_, __) {},
      checkpointStore: store,
      ownerKey: () => 'alice',
      now: () => now,
      sessionIdFactory: () => 'session-origin',
      currentBuild: () => '1001',
      currentGitSha: () => 'abc123def',
    );
    telemetry.onPaused(snapshot);
    await telemetry.pendingCheckpointWrites;
    final encoded = jsonEncode(store.value);
    final decoded = Map<String, Object>.from(jsonDecode(encoded) as Map);
    expect(decoded['origin_build'], '1001');
    expect(decoded['origin_git_sha'], 'abc123def');
    expect(decoded['background_session_id'], 'session-origin');
  });

  test('recovery emits the upgrade flag when the origin build differs', () async {
    var build = '1001';
    final store = MemoryCheckpoint();
    var now = DateTime.utc(2026, 10, 9);
    final events = <Map<String, dynamic>>[];
    BackgroundResourceTelemetry create() => BackgroundResourceTelemetry(
          emit: (_, props) => events.add(props),
          checkpointStore: store,
          ownerKey: () => 'alice',
          now: () => now,
          sessionIdFactory: () => 'session-origin',
          currentBuild: () => build,
          currentGitSha: () => 'abc123def',
        );
    final writer = create();
    writer.onPaused(snapshot);
    await writer.pendingCheckpointWrites;
    now = now.add(const Duration(minutes: 4));
    build = '1002';
    await create().recoverInterrupted(launchContext: backgroundInterruptLaunchColdStart);
    expect(events, hasLength(1));
    expect(events.single['interrupt_origin_build'], '1001');
    expect(events.single['interrupt_origin_git_sha'], 'abc123def');
    expect(events.single['interrupted_after_upgrade'], isTrue);
    expect(events.single['launch_context'], 'cold_start');
    expect(events.single['observation_state'], 'unobserved');
    expect(store.value, isNull);
  });

  test('same build clears the upgrade flag and a same-process launch is resume', () async {
    final store = MemoryCheckpoint();
    var now = DateTime.utc(2026, 10, 9);
    final events = <Map<String, dynamic>>[];
    final writer = BackgroundResourceTelemetry(
      emit: (_, props) => events.add(props),
      checkpointStore: store,
      ownerKey: () => 'alice',
      now: () => now,
      currentBuild: () => '1001',
      currentGitSha: () => 'abc123def',
    );
    writer.onPaused(snapshot);
    await writer.pendingCheckpointWrites;
    now = now.add(const Duration(minutes: 2));
    await writer.recoverInterrupted(launchContext: backgroundInterruptLaunchResume);
    expect(events.single['interrupt_origin_build'], '1001');
    expect(events.single['interrupted_after_upgrade'], isFalse);
    expect(events.single['launch_context'], 'resume');
  });

  test('legacy checkpoints omit origin fields and unknown launch context', () async {
    final store = MemoryCheckpoint()
      ..value = {
        'owner': 'alice',
        'background_session_id': 'legacy',
        'started_at': '2026-10-09T00:00:00.000Z',
        'recording_state': 'record',
        'batch_mode_enabled': true,
      };
    final events = <Map<String, dynamic>>[];
    final telemetry = BackgroundResourceTelemetry(
      emit: (_, props) => events.add(props),
      checkpointStore: store,
      ownerKey: () => 'alice',
      now: () => DateTime.utc(2026, 10, 9, 1),
      currentBuild: () => '1002',
      currentGitSha: () => 'abc123def',
    );
    await telemetry.recoverInterrupted(launchContext: 'force_quit');
    expect(events, hasLength(1));
    expect(events.single.containsKey('interrupt_origin_build'), isFalse);
    expect(events.single.containsKey('interrupt_origin_git_sha'), isFalse);
    expect(events.single.containsKey('interrupted_after_upgrade'), isFalse);
    expect(events.single.containsKey('launch_context'), isFalse);
    expect(events.single['background_session_id'], 'legacy');
  });

  test('missing or sentinel identity is not written and does not invent an upgrade', () async {
    final store = MemoryCheckpoint();
    final events = <Map<String, dynamic>>[];
    var now = DateTime.utc(2026, 10, 9);
    final writer = BackgroundResourceTelemetry(
      emit: (_, props) => events.add(props),
      checkpointStore: store,
      ownerKey: () => 'alice',
      now: () => now,
      currentBuild: () => 'unknown',
      currentGitSha: () => '',
    );
    writer.onPaused(snapshot);
    await writer.pendingCheckpointWrites;
    expect(store.value, isNot(contains('origin_build')));
    expect(store.value, isNot(contains('origin_git_sha')));
    store.value = {
      ...?store.value,
      'origin_build': 'unknown',
    };
    now = now.add(const Duration(minutes: 3));
    await writer.recoverInterrupted();
    expect(events.single.containsKey('interrupt_origin_build'), isFalse);
    expect(events.single.containsKey('interrupted_after_upgrade'), isFalse);
  });

  test('a throwing build reader still persists the checkpoint', () async {
    final store = MemoryCheckpoint();
    final telemetry = BackgroundResourceTelemetry(
      emit: (_, __) {},
      checkpointStore: store,
      ownerKey: () => 'alice',
      currentBuild: () => throw StateError('package info unavailable'),
      currentGitSha: () => throw StateError('sha unavailable'),
    );
    telemetry.onPaused(snapshot);
    await telemetry.pendingCheckpointWrites;
    expect(store.value?['background_session_id'], isNotNull);
    expect(store.value, isNot(contains('origin_build')));
    expect(store.value, isNot(contains('origin_git_sha')));
  });

  test('launch context mapping distinguishes cold start, resume, restoration, and unknown', () {
    BackgroundInterruptProcessLaunch.resetForTesting();
    expect(BackgroundInterruptProcessLaunch.peek(), isFalse);
    expect(BackgroundInterruptProcessLaunch.peek(), isFalse);
    expect(
      classifyBackgroundInterruptLaunch(processAlreadyObserved: BackgroundInterruptProcessLaunch.peek()),
      'cold_start',
    );
    expect(BackgroundInterruptProcessLaunch.peek(), isFalse);
    BackgroundInterruptProcessLaunch.mark();
    expect(BackgroundInterruptProcessLaunch.peek(), isTrue);
    expect(
      classifyBackgroundInterruptLaunch(processAlreadyObserved: BackgroundInterruptProcessLaunch.peek()),
      'resume',
    );
    expect(
      classifyBackgroundInterruptLaunch(processAlreadyObserved: false, osStateRestored: true),
      'restored',
    );
    expect(
      classifyBackgroundInterruptLaunch(processAlreadyObserved: true, osStateRestored: true),
      'restored',
    );
    expect(classifyBackgroundInterruptLaunch(processAlreadyObserved: null), isNull);
    expect(normalizeBackgroundInterruptLaunchContext(null), isNull);
    expect(normalizeBackgroundInterruptLaunchContext('force_quit'), isNull);
    expect(normalizeBackgroundInterruptLaunchContext('cold_start'), 'cold_start');
    BackgroundInterruptProcessLaunch.resetForTesting();
  });

  test('origin build without a current build omits the upgrade flag', () async {
    final store = MemoryCheckpoint()
      ..value = {
        'owner': 'alice',
        'background_session_id': 'partial',
        'started_at': '2026-10-09T00:00:00.000Z',
        'recording_state': 'record',
        'origin_build': '1001',
      };
    final events = <Map<String, dynamic>>[];
    final telemetry = BackgroundResourceTelemetry(
      emit: (_, props) => events.add(props),
      checkpointStore: store,
      ownerKey: () => 'alice',
      now: () => DateTime.utc(2026, 10, 9, 2),
      currentBuild: () => null,
    );
    await telemetry.recoverInterrupted(launchContext: backgroundInterruptLaunchRestored);
    expect(events.single['interrupt_origin_build'], '1001');
    expect(events.single.containsKey('interrupt_origin_git_sha'), isFalse);
    expect(events.single.containsKey('interrupted_after_upgrade'), isFalse);
    expect(events.single['launch_context'], 'restored');
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
