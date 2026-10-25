import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Count sort-key work rather than elapsed time on the shared host.
class _CountingWal extends Wal {
  _CountingWal(int start)
      : _start = start,
        super(timerStart: start, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.synced);

  int _start;
  int reads = 0;

  @override
  int get timerStart {
    reads++;
    return _start;
  }

  @override
  set timerStart(int value) => _start = value;
}

class _Syncs {
  final List<Wal> wals;
  _Syncs(this.wals);
  int inventoryReads = 0;
  Completer<List<Wal>>? blockedRead;
  Future<List<Wal>> getAllWals() async {
    inventoryReads++;
    final blocked = blockedRead;
    if (blocked != null) return blocked.future;
    return List.of(wals);
  }

  final entered = Completer<void>();
  final finished = Completer<SyncLocalFilesResponse?>();
  FlashSyncStallReason get flashStallReason => FlashSyncStallReason.none;
  void clearUserData() {}
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) {
    entered.complete();
    return finished.future;
  }
}

class _WalService implements IWalService {
  _WalService(this.syncs);
  final _Syncs syncs;
  @override
  dynamic getSyncs() => syncs;
  @override
  void start() {}
  @override
  Future<void> stop() async {}
  @override
  void subscribe(IWalServiceListener subscription, Object context) {}
  @override
  void unsubscribe(Object context) {}
}

SyncUploadGate _gate() => SyncUploadGate(
      limiter: SyncRateLimiter.instance..clear(),
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async =>
          UploadFilesResult.queued('unused'),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('slow background reads stay single-flight and deliver the trailing event', (tester) async {
    final syncs = _Syncs([]);
    final provider = SyncProvider(walService: _WalService(syncs), uploadGate: _gate(), startBackgroundSync: false);
    addTearDown(provider.dispose);
    await provider.initialized;
    syncs.inventoryReads = 0;
    final blocked = syncs.blockedRead = Completer<List<Wal>>();
    provider.onWalUpdated();
    await tester.pump(const Duration(milliseconds: 100));
    expect(syncs.inventoryReads, 1);
    for (var event = 0; event < 20; event++) {
      provider.onWalUpdated();
      await tester.pump(const Duration(milliseconds: 10));
    }
    expect(syncs.inventoryReads, 1, reason: 'a slow inventory read must not overlap more full-index reads');
    syncs.blockedRead = null;
    blocked.complete([]);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(syncs.inventoryReads, 2, reason: 'the last event during the slow read must not be lost');
    provider.onWalUpdated();
    await provider.refreshWals();
    final afterExplicitRefresh = syncs.inventoryReads;
    await tester.pump(const Duration(milliseconds: 100));
    expect(syncs.inventoryReads, afterExplicitRefresh, reason: 'an explicit refresh supersedes the queued read');
    provider.onWalUpdated();
    provider.clearUserData();
    await tester.pump(const Duration(milliseconds: 100));
    expect(syncs.inventoryReads, afterExplicitRefresh, reason: 'logout cancels queued work');
  });

  for (final semantics in [false, true]) {
    testWidgets('WAL event bursts coalesce before inventory work semantics=$semantics', (tester) async {
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        final syncs = _Syncs([]);
        final provider = SyncProvider(walService: _WalService(syncs), uploadGate: _gate(), startBackgroundSync: false);
        addTearDown(provider.dispose);
        await provider.initialized;
        var builds = 0;
        var notifications = 0;
        provider.addListener(() => notifications++);
        await tester.pumpWidget(ChangeNotifierProvider.value(
          value: provider,
          child: MaterialApp(
              home: IndexedStack(children: [
            for (final tab in ['Home', 'Tasks', 'Chat'])
              Consumer<SyncProvider>(builder: (context, sync, child) {
                builds++;
                return Text('$tab ${sync.allWals.length}');
              }),
          ])),
        ));
        syncs.inventoryReads = builds = notifications = 0;
        for (var event = 0; event < 20; event++) {
          provider.onWalUpdated();
          await tester.pump(const Duration(milliseconds: 10));
        }
        // Flush the trailing event window, including its provider delivery.
        await tester.pump(const Duration(milliseconds: 100));
        await tester.pump();
        debugPrint('GLOBAL walBurst semantics=$semantics events=20 durationMs=200 '
            'inventoryReads=${syncs.inventoryReads} notifications=$notifications tabConsumerBuilds=$builds');
        final reads = syncs.inventoryReads;
        final fanOut = builds;
        // Logout must invalidate a pending callback and disposal must cancel it.
        provider.onWalUpdated();
        provider.clearUserData();
        await tester.pump(const Duration(milliseconds: 100));
        expect(provider.allWals, isEmpty);
        await tester.pumpWidget(const SizedBox.shrink());
        expect(reads, lessThanOrEqualTo(2));
        expect(fanOut, lessThanOrEqualTo(6));
      } finally {
        handle?.dispose();
      }
    });

    testWidgets('repeated sync progress has no fan-out semantics=$semantics', (tester) async {
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        final syncs = _Syncs([]);
        final provider = SyncProvider(walService: _WalService(syncs), uploadGate: _gate(), startBackgroundSync: false);
        addTearDown(provider.dispose);
        await provider.initialized;
        late Future<void> sync;
        sync = provider.syncWals();
        await tester.pump();
        expect(syncs.entered.isCompleted, isTrue);
        var builds = 0;
        var notifications = 0;
        provider.addListener(() => notifications++);
        await tester.pumpWidget(ChangeNotifierProvider.value(
          value: provider,
          child: MaterialApp(
              home: IndexedStack(children: [
            for (final tab in ['Home', 'Tasks', 'Chat'])
              Consumer<SyncProvider>(builder: (context, sync, child) {
                builds++;
                return Text('$tab ${sync.syncState.progress}');
              }),
          ])),
        ));
        void report(double percentage, {double speed = 12, int current = 1}) => provider.onWalSyncedProgress(
              percentage,
              phase: SyncPhase.uploadingToCloud,
              speedKBps: speed,
              currentFile: current,
              totalFiles: 10,
              uploadedBytes: 100,
              totalBytesToUpload: 1000,
            );
        report(0.4);
        await tester.pump();
        builds = notifications = 0;
        for (var i = 0; i < 20; i++) {
          report(0.4);
          await tester.pump();
        }
        debugPrint('GLOBAL identicalProgress semantics=$semantics events=20 '
            'notifications=$notifications tabConsumerBuilds=$builds');
        final duplicateNotifications = notifications;
        final duplicateBuilds = builds;
        // Scalar state stays current even before its next UI publication. File
        // and phase transitions must publish immediately.
        report(0.5);
        expect(provider.syncState.progress, 0.5);
        report(0.5, speed: 20);
        expect(provider.syncState.speedKBps, 20);
        report(0.5, speed: 20, current: 2);
        expect(notifications, greaterThan(duplicateNotifications));
        await tester.pump(const Duration(milliseconds: 100));
        builds = notifications = 0;
        for (var event = 1; event <= 20; event++) {
          report(0.5 + event / 1000, speed: 20, current: 2);
          await tester.pump(const Duration(milliseconds: 10));
        }
        await tester.pump(const Duration(milliseconds: 100));
        await tester.pump();
        final progressNotifications = notifications;
        final progressBuilds = builds;
        debugPrint('GLOBAL changingProgress semantics=$semantics events=20 durationMs=200 '
            'notifications=$notifications tabConsumerBuilds=$builds');
        final beforePhase = notifications;
        provider.onWalSyncedProgress(0.6, phase: SyncPhase.waitingForInternet);
        expect(notifications, beforePhase + 1);
        provider.onWalSyncedProgress(1, phase: SyncPhase.waitingForInternet);
        expect(notifications, beforePhase + 2, reason: 'completion publishes without waiting for a timer');
        provider.onWalSyncedProgress(0.9, phase: SyncPhase.waitingForInternet);
        syncs.finished.complete(null);
        await sync;
        expect(provider.syncState.isCompleted, isTrue);
        final afterCompletion = notifications;
        await tester.pump(const Duration(milliseconds: 100));
        expect(notifications, afterCompletion, reason: 'terminal state cancels a pending progress publication');
        await tester.pumpWidget(const SizedBox.shrink());
        expect(duplicateNotifications, 0);
        expect(duplicateBuilds, 0);
        expect(progressNotifications, lessThanOrEqualTo(2));
        expect(progressBuilds, lessThanOrEqualTo(6));
      } finally {
        handle?.dispose();
      }
    });

    testWidgets('progress inventory refresh reuses order with semantics=$semantics', (tester) async {
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        final wals = List.generate(6000, (i) => _CountingWal(1700000000 + (i * 7919) % 6000));
        final syncs = _Syncs(wals);
        final provider = SyncProvider(walService: _WalService(syncs), uploadGate: _gate(), startBackgroundSync: false);
        addTearDown(provider.dispose);
        await provider.initialized;
        var shellBuilds = 0;
        // Three mounted tab consumers model broad listeners. This is an explicit
        // fan-out probe, not a timing or full production-shell measurement.
        await tester.pumpWidget(ChangeNotifierProvider.value(
          value: provider,
          child: MaterialApp(
            home: IndexedStack(children: [
              for (final tab in ['Home', 'Tasks', 'Chat'])
                Consumer<SyncProvider>(builder: (context, sync, child) {
                  shellBuilds++;
                  return Text('$tab ${sync.displaySortedWals.length}');
                }),
            ]),
          ),
        ));
        final initial = provider.displaySortedWals;
        var prior = initial;
        var orderDerivations = 0;
        for (final wal in wals) {
          wal.reads = 0;
        }
        shellBuilds = 0;
        for (var event = 0; event < 20; event++) {
          // Services publish new list containers containing the same mutable
          // WALs on every progress update, not just membership changes.
          wals.first.syncSpeedKBps = event.toDouble();
          await provider.refreshWals();
          await tester.pump();
          final sorted = provider.displaySortedWals;
          if (!identical(sorted, prior)) orderDerivations++;
          prior = sorted;
        }
        final keyReads = wals.fold<int>(0, (n, wal) => n + wal.reads);
        debugPrint('GLOBAL inventory semantics=$semantics refreshes=20 rows=6000 '
            'orderDerivations=$orderDerivations sortKeyReads=$keyReads tabConsumerBuilds=$shellBuilds');
        expect(orderDerivations, 0, reason: 'progress does not change inventory order');
        expect(keyReads, lessThanOrEqualTo(6000 * 20), reason: 'one linear cache validation per inventory refresh');

        // Cache must still invalidate for mutable sort keys, additions, removals
        // and replacement objects, even when the number of rows stays the same.
        final changed = wals.first;
        changed.timerStart = 1900000000;
        await provider.refreshWals();
        expect(provider.displaySortedWals.first, same(changed));
        wals[0] = _CountingWal(2000000000);
        await provider.refreshWals();
        expect(provider.displaySortedWals.first, same(wals.first));
        wals.removeAt(0);
        await provider.refreshWals();
        expect(provider.displaySortedWals.length, 5999);
        wals.add(_CountingWal(2100000000));
        await provider.refreshWals();
        expect(provider.displaySortedWals.first, same(wals.last));
        // Status partitions remain independently invalidated.
        wals.first.status = WalStatus.corrupted;
        await provider.refreshWals();
        expect(provider.corruptedWals, contains(wals.first));
        expect(provider.syncedWals, isNot(contains(wals.first)));
        await tester.pumpWidget(const SizedBox.shrink());
      } finally {
        handle?.dispose();
      }
    });
  }
}
