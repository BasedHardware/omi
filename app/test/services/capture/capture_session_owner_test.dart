import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

RecordingTransferCoordinator _coordinator({int Function()? drains}) => RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        drains?.call();
        return const RecordingTransferDrainResult.skipped();
      },
      autoUploadEnabled: () => true,
    );

CaptureSessionOwner _owner({RecordingTransferCoordinator? coordinator}) => CaptureSessionOwner(
      coordinator: coordinator ?? _coordinator(),
      startForeground: () async {},
      stopForeground: () async {},
    );

void main() {
  test('keepalive joins pending connect and a generation roll closes the stale socket', () async {
    final owner = _owner();
    owner.replaceSession('user-a/device-a');
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

    final a = owner.connect(configuration: 'pcm16/16000', open: open, close: close);
    final b = owner.connect(configuration: 'pcm16/16000', open: open, close: close);
    await pumpEventQueue();
    expect(opens, 1);
    owner.replaceSession('user-a/device-b');
    gate.complete('old-socket');
    expect(await a, isNull);
    expect(await b, isNull);
    expect(closed, ['old-socket']);
    final c = await owner.connect(configuration: 'pcm16/16000', open: () async => 'fresh', close: close);
    expect(c, 'fresh');
    await owner.close();
    expect(closed, ['old-socket', 'fresh']);
  });

  test('changed configuration supersedes but cannot publish an older completion', () async {
    final owner = _owner();
    owner.replaceSession('a');
    final old = Completer<String>();
    final closed = <String>[];
    Future<void> close(String s) async => closed.add(s);
    final a = owner.connect(configuration: 'opus', open: () => old.future, close: close);
    expect(await owner.connect(configuration: 'pcm', open: () async => 'new', close: close), 'new');
    old.complete('old');
    expect(await a, isNull);
    expect(closed, ['old']);
    await owner.close();
    expect(closed, ['old', 'new']);
  });

  test('prepareCurrent cannot commit an obsolete generation or disposed completion', () async {
    final owner = _owner();
    owner.replaceSession('same-user/same-device');
    final before = owner.token;
    final gate = Completer<String>();
    final commits = <String>[];
    final work = owner.prepareCurrent(() => gate.future, commits.add);
    owner.replaceSession('same-user/same-device');
    expect(owner.isCurrent(before), isFalse);
    expect(owner.token.generation, greaterThan(before.generation));
    gate.complete('generation primitive');
    await work;
    expect(commits, isEmpty);
    await owner.prepareCurrent(() async => 'current', commits.add);
    expect(commits, ['current']);
    final late = Completer<String>();
    final afterDispose = owner.prepareCurrent(() => late.future, commits.add);
    await owner.close();
    late.complete('disposed');
    await afterDispose;
    expect(commits, ['current']);
  });

  test('wakeIfCurrent does not drain after a generation roll', () async {
    var drains = 0;
    final coordinator = _coordinator(drains: () => drains++);
    addTearDown(coordinator.dispose);
    final owner = _owner(coordinator: coordinator);
    owner.replaceSession('session-a');
    final token = owner.token;
    owner.replaceSession('session-b');
    await owner.wakeIfCurrent(token, WakeTrigger.cooldownElapsed);
    await coordinator.waitUntilIdle();
    expect(drains, 0);
    await owner.wakeIfCurrent(owner.token, WakeTrigger.cooldownElapsed);
    await coordinator.waitUntilIdle();
    expect(drains, 1);
    await owner.close();
  });
}
