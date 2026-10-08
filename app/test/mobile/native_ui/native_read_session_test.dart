import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/mobile/native_ui/native_read_session.dart';

void main() {
  test('reads through the existing service for the current session', () async {
    final session = NativeReadSession(isCurrent: () => true);
    expect(await session.read(() async => 'current conversation'), 'current conversation');
  });

  test('does not start a read after session expiration', () async {
    final session = NativeReadSession(isCurrent: () => false);
    var called = false;
    expect(
        await session.read(() async {
          called = true;
          return 'private';
        }),
        isNull);
    expect(called, isFalse);
  });

  test('account change fences an already pending read', () async {
    var current = true;
    final session = NativeReadSession(isCurrent: () => current);
    final pending = Completer<String>();
    final read = session.read(() => pending.future);
    current = false;
    pending.complete('previous account transcript');
    expect(await read, isNull);
  });

  test('leaving the native surface fences a pending read', () async {
    final session = NativeReadSession(isCurrent: () => true);
    final pending = Completer<String>();
    final read = session.read(() => pending.future);
    session.dispose();
    pending.complete('previous surface transcript');
    expect(await read, isNull);
    expect(session.active, isFalse);
  });

  test('a service failure remains a failure rather than an empty success', () async {
    final session = NativeReadSession(isCurrent: () => true);
    expect(session.read(() async => throw StateError('read failed')), throwsStateError);
  });
}
