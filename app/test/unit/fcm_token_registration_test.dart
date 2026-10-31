import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/notifications/fcm_token_registration.dart';

void main() {
  const alice = AuthSessionSnapshot(ownerUid: 'alice', generation: 1);
  late AuthSessionSnapshot? owner;
  late String? apns;
  late String? token;
  late String zone;
  late bool accept;
  late List<(String, String, String)> saves;
  late int tokenReads;
  setUp(() {
    owner = alice;
    apns = 'synthetic-apns';
    token = 'synthetic-fcm';
    zone = 'Asia/Tokyo';
    accept = true;
    saves = [];
    tokenReads = 0;
  });
  FcmTokenRegistration registrar({
    Future<String?> Function()? apnsRead,
    Future<String?> Function()? tokenRead,
    Future<bool> Function(String, String, AuthSessionSnapshot)? persist,
    bool requiresApns = true,
  }) =>
      FcmTokenRegistration(
        capture: () => owner,
        isCurrent: (snapshot) => snapshot.ownerUid == owner?.ownerUid && snapshot.generation == owner?.generation,
        readApns: apnsRead ?? () async => apns,
        readToken: tokenRead ??
            () async {
              tokenReads++;
              return token;
            },
        readTimeZone: () async => zone,
        persist: persist ??
            (value, timeZone, snapshot) async {
              saves.add((value, timeZone, snapshot.ownerUid));
              return accept;
            },
        requiresApns: requiresApns,
        deadline: const Duration(seconds: 2),
        retryDelays: const [Duration(seconds: 1), Duration(seconds: 2), Duration(seconds: 4), Duration(seconds: 8)],
      );

  test('launch with a restored owner registers without a token-refresh event', () async {
    final service = registrar();
    addTearDown(service.dispose);
    await service.refresh();
    expect(saves, [('synthetic-fcm', 'Asia/Tokyo', 'alice')]);
    await service.refresh();
    expect(saves, hasLength(1), reason: 'repeated lifecycle wakes do not repost an accepted token');
    zone = 'America/New_York';
    await service.refresh();
    expect(saves.last.$2, zone);
  });

  test('APNs arriving after the former ten-second window retries without rotation', () {
    fakeAsync((clock) {
      apns = null;
      final service = registrar();
      unawaited(service.refresh());
      clock.flushMicrotasks();
      clock.elapse(const Duration(seconds: 10));
      clock.flushMicrotasks();
      expect(saves, isEmpty);
      expect(tokenReads, 0);
      apns = 'late-apns';
      clock.elapse(const Duration(seconds: 5));
      clock.flushMicrotasks();
      expect(saves, hasLength(1));
      service.dispose();
      expect(clock.pendingTimers, isEmpty);
    });
  });

  test('a failed HTTP acknowledgement retries rather than becoming a saved receipt', () {
    fakeAsync((clock) {
      accept = false;
      final service = registrar();
      unawaited(service.refresh());
      clock.flushMicrotasks();
      expect(saves, hasLength(1));
      accept = true;
      clock.elapse(const Duration(seconds: 1));
      clock.flushMicrotasks();
      expect(saves, hasLength(2));
      clock.elapse(const Duration(seconds: 30));
      clock.flushMicrotasks();
      expect(saves, hasLength(2));
      service.dispose();
    });
  });

  test('SDK exceptions retry; Android does not require an APNs token', () {
    fakeAsync((clock) {
      var reads = 0;
      final service = registrar(
        requiresApns: false,
        apnsRead: () async => throw StateError('APNs must not be used'),
        tokenRead: () async {
          if (reads++ == 0) throw StateError('transient SDK failure');
          return token;
        },
      );
      unawaited(service.refresh());
      clock.flushMicrotasks();
      expect(saves, isEmpty);
      clock.elapse(const Duration(seconds: 1));
      clock.flushMicrotasks();
      expect(saves, hasLength(1));
      service.dispose();
    });
  });

  test('sign-out while APNs is pending cannot save a token', () async {
    final pending = Completer<String?>();
    final service = registrar(apnsRead: () => pending.future);
    addTearDown(service.dispose);
    final work = service.refresh();
    owner = null;
    await service.refresh();
    pending.complete('old-apns');
    await work;
    expect(saves, isEmpty);
  });

  test('a replacement account does not wait for the old SDK request', () async {
    final pending = Completer<String?>();
    var first = true;
    final service = registrar(apnsRead: () {
      if (first) {
        first = false;
        return pending.future;
      }
      return Future.value(apns);
    });
    addTearDown(service.dispose);
    final oldWork = service.refresh();
    owner = const AuthSessionSnapshot(ownerUid: 'bob', generation: 2);
    await service.refresh();
    expect(saves.single.$3, 'bob');
    pending.complete('late-alice-apns');
    await oldWork;
    expect(saves, hasLength(1));
  });

  test('same-user reauthentication invalidates the saved registration receipt', () async {
    final service = registrar();
    addTearDown(service.dispose);
    await service.refresh();
    owner = const AuthSessionSnapshot(ownerUid: 'alice', generation: 2);
    await service.refresh();
    expect(saves, hasLength(2));
  });

  test('rotation arriving during a save is persisted after that save', () async {
    final pending = Completer<bool>();
    final service = registrar(persist: (value, timeZone, snapshot) {
      saves.add((value, timeZone, snapshot.ownerUid));
      return saves.length == 1 ? pending.future : Future.value(true);
    });
    addTearDown(service.dispose);
    final work = service.refresh();
    // Allow the acquisition awaits to reach the physical save boundary.
    for (var i = 0; i < 12 && saves.isEmpty; i++) {
      await Future<void>.value();
    }
    expect(saves, hasLength(1));
    unawaited(service.refresh(token: 'rotated-fcm'));
    pending.complete(true);
    await work;
    for (var i = 0; i < 12 && saves.length < 2; i++) {
      await Future<void>.value();
    }
    expect(saves.map((row) => row.$1), ['synthetic-fcm', 'rotated-fcm']);
  });

  test('a hanging SDK is deadline bounded and exhausts only the retry budget', () {
    fakeAsync((clock) {
      var reads = 0;
      final service = registrar(apnsRead: () {
        reads++;
        return Completer<String?>().future;
      });
      unawaited(service.refresh());
      clock.flushMicrotasks();
      clock.elapse(const Duration(minutes: 2));
      clock.flushMicrotasks();
      expect(reads, 5);
      expect(saves, isEmpty);
      expect(clock.pendingTimers, isEmpty);
      unawaited(service.refresh());
      clock.flushMicrotasks();
      expect(reads, 6, reason: 'foreground/permission wake starts a fresh bounded attempt');
      service.dispose();
      clock.flushMicrotasks();
      expect(clock.pendingTimers, isEmpty);
    });
  });
}
