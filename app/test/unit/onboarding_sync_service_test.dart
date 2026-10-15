import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:fake_async/fake_async.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/onboarding_sync_service.dart';

const alice = AuthSessionSnapshot(ownerUid: 'alice', generation: 1);
const bob = AuthSessionSnapshot(ownerUid: 'bob', generation: 2);

void main() {
  late Map<String, String> disk;
  late AuthSessionSnapshot? current;
  late List<({String owner, Map<String, dynamic> fields})> sent;
  late OnboardingSyncService service;
  late Future<bool> Function(AuthSessionSnapshot, Map<String, dynamic>) transport;
  late bool writesSucceed;

  OnboardingSyncService create() => OnboardingSyncService(
        read: (owner) => disk[owner] ?? '',
        write: (owner, value) async {
          if (!writesSucceed) return false;
          disk[owner] = value;
          return true;
        },
        send: (session, fields) async {
          sent.add((owner: session.ownerUid, fields: Map.of(fields)));
          return transport(session, fields);
        },
        isCurrent: (session) => current?.ownerUid == session.ownerUid && current?.generation == session.generation,
      );

  setUp(() {
    disk = {};
    current = alice;
    sent = [];
    writesSucceed = true;
    transport = (_, __) async => true;
    service = create()..bindSession(alice);
  });
  tearDown(() => service.dispose());

  test('failed send survives restart and clears only after acknowledgement', () async {
    transport = (_, __) async => false;
    expect(await service.enqueue(alice, completed: true), isTrue);
    await service.flush();
    expect(service.pending('alice'), {'completed': true});
    service.dispose();
    service = create()..bindSession(alice);
    transport = (_, __) async => true;
    await service.flush();
    expect(disk['alice'], '');
    expect(sent.last.fields, {'completed': true});
  });

  test('concurrent wakes join one send', () async {
    final reply = Completer<bool>();
    transport = (_, __) => reply.future;
    await service.enqueue(alice, completed: true);
    final first = service.flush();
    final second = service.flush();
    await Future<void>.delayed(Duration.zero);
    expect(sent, hasLength(1));
    reply.complete(true);
    await Future.wait([first, second]);
    expect(disk['alice'], '');
  });

  test('late acknowledgement preserves and sends a newer survey answer', () async {
    final reply = Completer<bool>();
    transport = (_, __) => sent.length == 1 ? reply.future : Future.value(true);
    await service.enqueue(alice, acquisitionSource: 'Friend');
    await Future<void>.delayed(Duration.zero);
    await service.enqueue(alice, acquisitionSource: 'YouTube', completed: true);
    expect(service.pending('alice')['acquisition_source'], 'YouTube');
    reply.complete(true);
    await service.flush();
    expect(sent.map((row) => row.fields['acquisition_source']), ['Friend', 'YouTube']);
    expect(sent.last.fields['completed'], true);
    expect(disk['alice'], '');
  });

  test('account switch never acknowledges Alice or sends her fields as Bob', () async {
    final reply = Completer<bool>();
    transport = (session, _) => session.ownerUid == 'alice' ? reply.future : Future.value(true);
    await service.enqueue(alice, acquisitionSource: 'Alice answer');
    await Future<void>.delayed(Duration.zero);
    current = bob;
    service.bindSession(bob);
    await service.enqueue(bob, completed: true);
    reply.complete(true);
    await service.flush();
    expect(service.pending('alice'), {'acquisition_source': 'Alice answer'});
    expect(sent.last.owner, 'bob');
    expect(sent.last.fields, {'completed': true});
    expect(disk['bob'], '');
    current = alice;
    service.bindSession(alice);
    transport = (_, __) async => true;
    await service.flush();
    expect(disk['alice'], '');
  });

  test('same-account reauthentication fences old acknowledgements', () async {
    final reply = Completer<bool>();
    transport = (_, __) => reply.future;
    await service.enqueue(alice, completed: true);
    await Future<void>.delayed(Duration.zero);
    current = const AuthSessionSnapshot(ownerUid: 'alice', generation: 3);
    service.bindSession(null);
    reply.complete(true);
    await service.flush();
    expect(service.pending('alice'), {'completed': true});
    expect(await service.enqueue(alice, acquisitionSource: 'stale'), isFalse);
    service.bindSession(current);
    transport = (_, __) async => true;
    await service.flush();
    expect(disk['alice'], '');
  });

  test('failed persistence does not send or report success and user can retry', () async {
    writesSucceed = false;
    expect(await service.enqueue(alice, completed: true), isFalse);
    expect(sent, isEmpty);
    writesSucceed = true;
    expect(await service.enqueue(alice, completed: true), isTrue);
    await service.flush();
    expect(sent, hasLength(1));
  });

  test('failed acknowledgement persistence retains intent for replay', () async {
    transport = (_, __) async {
      writesSucceed = false;
      return true;
    };
    await service.enqueue(alice, completed: true);
    await service.flush();
    expect(service.pending('alice'), {'completed': true});
    writesSucceed = true;
    transport = (_, __) async => true;
    await service.flush();
    expect(disk['alice'], '');
  });

  test('background defers coalesced state until foreground', () async {
    service.setActive(false);
    await service.enqueue(alice, completed: true);
    await service.enqueue(alice, deviceOnboardingCompleted: true, acquisitionSource: 'Friend');
    await service.flush();
    expect(sent, isEmpty);
    service.setActive(true);
    await service.flush();
    expect(sent.single.fields, {
      'completed': true,
      'device_onboarding_completed': true,
      'acquisition_source': 'Friend',
    });
  });

  test('active retry recovers automatically and successful ack stops timer', () {
    fakeAsync((clock) {
      service.dispose();
      service = create()..bindSession(alice);
      transport = (_, __) async => false;
      unawaited(service.enqueue(alice, completed: true));
      clock.flushMicrotasks();
      expect(sent, hasLength(1));
      transport = (_, __) async => true;
      clock.elapse(const Duration(seconds: 30));
      clock.flushMicrotasks();
      expect(sent, hasLength(2));
      expect(disk['alice'], '');
      clock.elapse(const Duration(seconds: 60));
      expect(sent, hasLength(2));
      expect(clock.nonPeriodicTimerCount, 0);
      service.dispose();
    });
  });

  test('background and disposal cancel retry timers', () {
    fakeAsync((clock) {
      service.dispose();
      service = create()..bindSession(alice);
      transport = (_, __) async => false;
      unawaited(service.enqueue(alice, completed: true));
      clock.flushMicrotasks();
      service.setActive(false);
      clock.elapse(const Duration(seconds: 60));
      expect(sent, hasLength(1));
      service.setActive(true);
      unawaited(service.flush());
      clock.flushMicrotasks();
      service.dispose();
      clock.elapse(const Duration(seconds: 60));
      expect(sent, hasLength(2));
      expect(clock.nonPeriodicTimerCount, 0);
    });
  });
}
