import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/services/experiments/session_replay_gate.dart';
import 'package:omi/utils/analytics/adapters/posthog_adapter.dart';
import 'package:omi/utils/analytics/session_replay.dart';

// Session replay records nobody unless the remote flag says so: never with product analytics off,
// a flag that is off, missing or unreadable, in App Review or in the background, and it starts only
// after the flag resolves true for a settled identity.

class _Replay {
  _Replay({this.flag = true, this.flagError, bool sandbox = false, bool forceFlag = false}) {
    replay = SessionReplay(
      consent: consent,
      identity: identity,
      readFlag: (key) async {
        reads.add(key);
        final pending = nextRead;
        if (pending != null) {
          nextRead = null;
          return pending.future;
        }
        if (flagError != null) throw flagError!;
        return flag;
      },
      sandboxInstall: () => sandbox,
      forceFlag: forceFlag,
      start: () async => calls.add('start'),
      stop: () async => calls.add('stop'),
      isRecording: () async => nativeActive,
      requestFrame: () => frames++,
    );
  }

  final consent = ValueNotifier<bool>(true);
  final identity = ValueNotifier<String?>(null);
  final reads = <String>[];
  final calls = <String>[];
  bool flag;
  Object? flagError;
  bool nativeActive = true;
  int frames = 0;
  Completer<bool>? nextRead;
  late final SessionReplay replay;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('the gate needs analytics on, the flag on and no App Review', () {
    bool allowed({bool tracking = true, bool flag = true, bool? review = false, bool sandbox = false}) =>
        SessionReplayGate.allowed(
            trackingEnabled: tracking, flagEnabled: flag, appReview: review, sandboxInstall: sandbox);

    expect(allowed(), isTrue);
    expect(allowed(tracking: false), isFalse);
    expect(allowed(flag: false), isFalse);
    expect(allowed(review: true), isFalse);
    expect(allowed(review: null), isTrue, reason: 'a store install records before the subscription loads');
    expect(allowed(review: null, sandbox: true), isFalse, reason: 'App Review installs carry a sandbox receipt');
    expect(allowed(review: false, sandbox: true), isTrue, reason: 'TestFlight records once the server says no');
    expect(allowed(review: true, sandbox: true), isFalse);
  });

  test('flag on: records only after the identity settles and the flag resolves true', () {
    fakeAsync((async) {
      final r = _Replay()..replay.attach();
      async.flushMicrotasks();
      expect(r.reads, isEmpty, reason: 'no flag read without a settled identity');
      expect(r.calls, isEmpty);

      r.identity.value = 'anon-1';
      async.flushMicrotasks();
      expect(r.reads, ['mobile-session-replay']);
      expect(r.calls, ['start']);

      async.elapse(const Duration(seconds: 30));
      expect(r.calls, ['start'], reason: 'the native SDK confirmed, so the recording keeps running');
      expect(r.replay.recording, isTrue);
    });
  });

  test('flag off, missing or unreadable: never records', () {
    for (final r in [_Replay(flag: false), _Replay(flagError: StateError('decide failed'))]) {
      fakeAsync((async) {
        r.replay.attach();
        r.identity.value = 'u1';
        async.elapse(const Duration(seconds: 30));
        expect(r.reads, ['mobile-session-replay']);
        expect(r.calls, isEmpty);
      });
    }
  });

  test('opted out: no flag read and no recording; opting out mid-recording stops it', () {
    fakeAsync((async) {
      final r = _Replay()..consent.value = false;
      r.replay.attach();
      r.identity.value = 'u1';
      async.elapse(const Duration(seconds: 30));
      expect(r.reads, isEmpty);
      expect(r.calls, isEmpty);

      // Opting back in re-settles the identity (AnalyticsManager clears it, then settles again).
      r.identity.value = null;
      r.consent.value = true;
      r.identity.value = 'u1';
      async.flushMicrotasks();
      expect(r.calls, ['start']);

      r.consent.value = false;
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop']);
      expect(r.replay.recording, isFalse);
    });
  });

  test('an identity change stops the recording and asks again for the new identity', () {
    fakeAsync((async) {
      final r = _Replay()..replay.attach();
      r.identity.value = 'anon-1';
      async.flushMicrotasks();
      expect(r.calls, ['start']);

      r.flag = false;
      r.identity.value = null; // signing in: the new identity is settling
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop']);
      r.identity.value = 'uid-1';
      async.elapse(const Duration(seconds: 30));
      expect(r.reads, ['mobile-session-replay', 'mobile-session-replay']);
      expect(r.calls, ['start', 'stop'], reason: 'the flag is off for the signed-in account');
    });
  });

  test('a slow read for a previous identity cannot start a recording', () {
    fakeAsync((async) {
      final r = _Replay(flag: false)..replay.attach();
      final slow = r.nextRead = Completer<bool>();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      r.identity.value = 'u2';
      async.flushMicrotasks();
      slow.complete(true);
      async.elapse(const Duration(seconds: 30));
      expect(r.reads, hasLength(2));
      expect(r.calls, isEmpty);
    });
  });

  test('App Review never records; a sandbox install waits for the server answer', () {
    fakeAsync((async) {
      final r = _Replay(sandbox: true)..replay.attach();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      expect(r.calls, isEmpty, reason: 'App Review state unknown on a sandbox-receipt install');

      r.replay.appReview = false;
      async.flushMicrotasks();
      expect(r.calls, ['start']);

      r.replay.appReview = true;
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop']);
    });
  });

  test('a native decline stops the capture ticker and is not retried for that identity', () {
    fakeAsync((async) {
      final r = _Replay()..nativeActive = false;
      r.replay.attach();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      expect(r.calls, ['start']);

      async.elapse(const Duration(seconds: 9));
      expect(r.calls, ['start'], reason: 'still waiting for the native SDK to confirm');
      async.elapse(const Duration(seconds: 1));
      expect(r.calls, ['start', 'stop']);

      r.replay
        ..foreground = false
        ..foreground = true
        ..appReview = false;
      async.elapse(const Duration(seconds: 30));
      expect(r.calls, ['start', 'stop']);

      r.nativeActive = true;
      r.identity.value = 'u2';
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop', 'start']);
    });
  });

  test('capture pauses in the background and resumes in the foreground', () {
    fakeAsync((async) {
      final r = _Replay()..replay.attach();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      r.replay.foreground = false;
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop']);
      r.replay.foreground = true;
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop', 'start']);
      expect(r.reads, hasLength(1), reason: 'the flag is read once per identity');
    });
  });

  test('while recording a frame is requested every tick, so a screen that went still is captured', () {
    fakeAsync((async) {
      final r = _Replay()..replay.attach();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      expect(r.frames, 1, reason: 'the first capture does not wait for the screen to change');
      async.elapse(const Duration(seconds: 6));
      expect(r.frames, 4);

      r.replay.foreground = false;
      async.elapse(const Duration(seconds: 10));
      expect(r.frames, 4, reason: 'no frames while not recording');
    });
  });

  test('the debug override reads the flag as on without asking PostHog', () {
    fakeAsync((async) {
      final r = _Replay(flag: false, forceFlag: true)..replay.attach();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      expect(r.reads, isEmpty);
      expect(r.calls, ['start']);
    });
  });

  test('detaching stops a recording', () {
    fakeAsync((async) {
      final r = _Replay()..replay.attach();
      r.identity.value = 'u1';
      async.flushMicrotasks();
      r.replay.detach();
      async.flushMicrotasks();
      expect(r.calls, ['start', 'stop']);
    });
  });

  group('PostHog setup', () {
    test('never starts replay and records frames unmasked', () async {
      SharedPreferences.setMockInitialValues({});
      Map<Object?, Object?>? setup;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('posthog_flutter'),
        (call) async {
          if (call.method == 'setup') setup = call.arguments as Map<Object?, Object?>;
          return null;
        },
      );

      await PostHogAnalyticsAdapter(apiKey: 'phc_test').init();

      expect(SessionReplay.configured, isTrue);
      expect(setup?['sessionReplay'], isFalse);
      expect(setup?['sessionReplayConfig'], {'maskAllImages': false, 'maskAllTexts': false, 'throttleDelayMs': 2000});
    });
  });
}
