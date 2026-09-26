import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

import '../support/spine/contract.dart';

class Effects {
  final events = <String>[];
  Completer<void>? startGate;
  Completer<void>? drainGate;
  late final coordinator = RecordingTransferCoordinator(
    reconcile: () async => events.add('reconcile'),
    discover: () async => events.add('discover'),
    refreshPending: () async {},
    drain: () async {
      events.add('drain');
      await drainGate?.future;
      return const RecordingTransferDrainResult(attempted: true, failed: false, needsReconciliation: false);
    },
    autoUploadEnabled: () => true,
  );
  late final owner = CaptureSessionOwner(
    coordinator: coordinator,
    startForeground: () async {
      events.add('start');
      await startGate?.future;
      events.add('started');
    },
    stopForeground: () async => events.add('stop'),
  );
}

void main() {
  contractTest('C1 concurrent recovery requesters share one drain; a later wake still runs', () async {
    final e = Effects()..drainGate = Completer<void>();
    addTearDown(e.coordinator.dispose);
    final a = e.owner.requestRecovery(WakeTrigger.deviceConnected);
    final b = e.owner.requestRecovery(WakeTrigger.userRetry);
    await pumpEventQueue();
    expect(e.events.where((v) => v == 'drain'), hasLength(1));
    e.drainGate!.complete();
    await Future.wait([a, b]);
    await e.coordinator.waitUntilIdle();
    expect(e.events.where((v) => v == 'drain'), hasLength(1));
    await e.owner.requestRecovery(WakeTrigger.userRetry);
    expect(e.events.where((v) => v == 'drain'), hasLength(2));
    await e.owner.close();
  });

  contractTest('C1 stop while native FGS start is pending stops once after completion', () async {
    final e = Effects()..startGate = Completer<void>();
    final a = e.owner.setForegroundRequired(true);
    await pumpEventQueue();
    final b = e.owner.setForegroundRequired(false);
    expect(e.events, ['start']);
    e.startGate!.complete();
    await Future.wait([a, b]);
    expect(e.events, ['start', 'started', 'stop']);
    expect(e.owner.foregroundRunning, isFalse);
    await e.owner.setForegroundRequired(false);
    expect(e.events.where((v) => v == 'stop'), hasLength(1));
    await e.owner.setForegroundRequired(true);
    expect(e.owner.foregroundRunning, isTrue);
    await e.owner.close();
    expect(e.events.where((v) => v == 'stop'), hasLength(2));
  });

  contractTest('C1 failed FGS start can retry; failure is observable', () async {
    var starts = 0;
    final e = Effects();
    final owner = CaptureSessionOwner(
      coordinator: e.coordinator,
      startForeground: () async {
        if (++starts == 1) throw StateError('native failure');
      },
      stopForeground: () async {},
    );
    await expectLater(owner.setForegroundRequired(true), throwsStateError);
    expect(owner.foregroundRunning, isFalse);
    await owner.setForegroundRequired(true);
    expect(owner.foregroundRunning, isTrue);
    expect(starts, 2);
    await owner.close();
  });

  contractTest('C1 keepalive joins pending connect and stale socket is closed', () async {
    final e = Effects();
    e.owner.replaceSession('user-a/device-a');
    final gate = Completer<String>();
    var opens = 0;
    final closed = <String>[];
    Future<String> open() {
      opens++;
      return gate.future;
    }

    Future<void> close(String socket) async {
      closed.add(socket);
    }

    final a = e.owner.connect(configuration: 'pcm16/16000', open: open, close: close);
    final b = e.owner.connect(configuration: 'pcm16/16000', open: open, close: close);
    await pumpEventQueue();
    expect(opens, 1);
    e.owner.replaceSession('user-a/device-b');
    gate.complete('old-socket');
    expect(await a, isNull);
    expect(await b, isNull);
    expect(closed, ['old-socket']);
    final c = await e.owner.connect(configuration: 'pcm16/16000', open: () async => 'fresh', close: close);
    expect(c, 'fresh');
    await e.owner.close();
    expect(closed, ['old-socket', 'fresh']);
  });

  contractTest('C1 changed configuration supersedes but cannot publish an older completion', () async {
    final e = Effects();
    e.owner.replaceSession('a');
    final old = Completer<String>();
    final closed = <String>[];
    Future<void> close(String s) async => closed.add(s);
    final a = e.owner.connect(configuration: 'opus', open: () => old.future, close: close);
    expect(await e.owner.connect(configuration: 'pcm', open: () async => 'new', close: close), 'new');
    old.complete('old');
    expect(await a, isNull);
    expect(closed, ['old']);
    await e.owner.close();
    expect(closed, ['old', 'new']);
  });

  {
    const stage = 'generation primitive';
    contractTest('C1 $stage cannot commit an obsolete generation or disposed completion', () async {
      final e = Effects();
      e.owner.replaceSession('same-user/same-device');
      final before = e.owner.token;
      final gate = Completer<String>();
      final commits = <String>[];
      final work = e.owner.prepareCurrent(() => gate.future, commits.add);
      // Same identity still starts a NEW session; comparing just uid/device is wrong.
      e.owner.replaceSession('same-user/same-device');
      expect(e.owner.isCurrent(before), isFalse);
      expect(e.owner.token.generation, greaterThan(before.generation));
      gate.complete(stage);
      await work;
      expect(commits, isEmpty);
      await e.owner.prepareCurrent(() async => 'current', commits.add);
      expect(commits, ['current']);
      final late = Completer<String>();
      final afterDispose = e.owner.prepareCurrent(() => late.future, commits.add);
      await e.owner.close();
      late.complete('disposed');
      await afterDispose;
      expect(commits, ['current']);
    });
  }
}
