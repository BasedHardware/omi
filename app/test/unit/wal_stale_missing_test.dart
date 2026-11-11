import 'dart:io';

import '../support/capture/capture_replay_world.dart';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  final start = DateTime.utc(2026, 10, 7);
  Wal wal(int end, {WalStatus status = WalStatus.miss, WalStorage storage = WalStorage.disk}) => Wal(
        timerStart: end - 60,
        seconds: 60,
        codec: BleAudioCodec.pcm16,
        status: status,
        storage: storage,
        device: 'phone-mic',
      );
  test('reports old miss disk WALs including exhausted retries without changing custody', () async {
    final events = <Map<String, Object?>>[];
    final nowSecs = start.millisecondsSinceEpoch ~/ 1000;
    final stuck = wal(nowSecs - 901)..retryCount = walMaxAutoRetries;
    final sync = LocalWalSyncImpl(Listener(), now: () => start, staleWalTelemetry: events.add)
      ..testWals = [
        stuck,
        wal(nowSecs - 60),
        wal(nowSecs - 2000, status: WalStatus.synced),
        wal(nowSecs - 2000, status: WalStatus.uploaded),
        wal(nowSecs - 2000, storage: WalStorage.mem),
        wal(nowSecs - 2000, status: WalStatus.inProgress),
      ];
    sync.reportStaleMissingWals(trigger: 'startup');
    expect(events, hasLength(1));
    expect(events.single, containsPair('pending_wal_count', 1));
    expect(events.single, containsPair('exhausted_retry_count', 1));
    expect(stuck.status, WalStatus.miss);
    expect(stuck.retryCount, walMaxAutoRetries);
    expect(sync.testWals, hasLength(6));
  });
  test('foreground reports after readiness, throttles noise, and repeats while stuck', () async {
    var now = start;
    final events = <Map<String, Object?>>[];
    final dir = await Directory.systemTemp.createTemp('wal_stale_missing_');
    addTearDown(() => dir.delete(recursive: true));
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    addTearDown(world.dispose);
    final stale = wal(start.millisecondsSinceEpoch ~/ 1000 - 1000);
    final sync = LocalWalSyncImpl(
      Listener(),
      now: () => now,
      staleWalTelemetry: events.add,
      loadWals: () async => [stale],
      periodic: world.scheduler.periodic,
    );
    sync.start();
    addTearDown(sync.stop);
    await sync.walReady;
    expect(events.single, containsPair('trigger', 'startup'));
    events.clear();
    now = now.add(const Duration(minutes: 5));
    sync.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await Future<void>.delayed(Duration.zero);
    expect(events.single, containsPair('trigger', 'foreground'));
    sync.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await Future<void>.delayed(Duration.zero);
    expect(events, hasLength(1));
    now = now.add(const Duration(minutes: 5));
    sync.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await Future<void>.delayed(Duration.zero);
    expect(events, hasLength(2));
    sync.testWals.single.status = WalStatus.synced;
    sync.reportStaleMissingWals(trigger: 'foreground');
    expect(events, hasLength(2));
  });
  test('telemetry failure does not abort recovery or remove recordings', () {
    final sync = LocalWalSyncImpl(Listener(), now: () => start, staleWalTelemetry: (_) => throw StateError('analytics'))
      ..testWals = [wal(start.millisecondsSinceEpoch ~/ 1000 - 1000)];
    expect(() => sync.reportStaleMissingWals(trigger: 'startup'), returnsNormally);
    expect(sync.testWals.single.status, WalStatus.miss);
  });
}
