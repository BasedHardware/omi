import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/local_preview_admission.dart';

import 'package:omi/utils/analytics/registry/events.g.dart';

import '../../support/live_preview_fakes.dart';

void main() {
  late DateTime clock;
  late LocalPreviewAdmission admission;
  late List<int> sent;
  late List<LocalPreviewVerdictReport> reports;
  late List<(Duration, void Function())> deadlines;
  late LivePreviewController preview;

  HeldPendantFrame frame(int value, {bool walAccepted = true}) => HeldPendantFrame([value], null, walAccepted);
  void send(HeldPendantFrame frame) => sent.add(frame.payload.single);
  void route(int value, {bool declared = true, bool walAccepted = true}) =>
      admission.routePendant(frame(value, walAccepted: walAccepted), socketDeclared: declared, send: send);

  setUp(() {
    clock = DateTime.utc(2026, 10, 26);
    sent = [];
    reports = [];
    deadlines = [];
    admission = LocalPreviewAdmission(
      now: () => clock,
      onChanged: () {},
      onVerdictReport: reports.add,
      schedule: (delay, callback) {
        deadlines.add((delay, callback));
        return Timer(const Duration(days: 1), () {});
      },
    );
    preview = LivePreviewController(
      engine: FakeLivePreviewEngine(),
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
    );
    admission.preview = preview;
  });
  tearDown(() => preview.dispose());

  test('a socket that did not declare local preview streams every frame at once', () {
    admission.socketPublished(declared: false, send: send);
    route(1, declared: false);
    route(2, declared: false);
    expect(sent, [1, 2]);
  });

  test('refusal: held frames reach the socket in order before any newer frame', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    route(2);
    route(3);
    expect(sent, isEmpty);
    expect(admission.heldFramesForTesting, 3);
    final admitted = admission.verdict(granted: false, socketDeclared: true, send: send);
    expect(admitted, false);
    expect(sent, [1, 2, 3], reason: 'flushed by the verdict itself');
    route(4);
    expect(sent, [1, 2, 3, 4]);
    expect(admission.heldFramesForTesting, 0);
  });

  test('a grant to a socket that did not ask, or with no preview, is a refusal too', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    admission.preview = null;
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), false);
    expect(sent, [1]);
  });

  test('grant: the memory copy is dropped and nothing reaches the socket', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    route(2);
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), true);
    expect(admission.heldFramesForTesting, 0);
    expect(sent, isEmpty);
    expect(admission.admitted, true);
    expect(preview.phase, isNot(LivePreviewPhase.inactive));
  });

  test('overflow stops holding: flush in order, then stream', () {
    admission.socketPublished(declared: true, send: send);
    for (var i = 0; i < LocalPreviewAdmission.maxHeldFrames; i++) {
      route(i);
    }
    expect(sent, isEmpty);
    route(LocalPreviewAdmission.maxHeldFrames);
    expect(sent, List.generate(LocalPreviewAdmission.maxHeldFrames + 1, (i) => i));
    route(9999);
    expect(sent.last, 9999);
    expect(admission.heldFramesForTesting, 0);
    // A late grant after the release only admits; nothing more to drop or send.
    final before = sent.length;
    admission.verdict(granted: true, socketDeclared: true, send: send);
    expect(sent.length, before);
  });

  test('a verdict that never arrives is a refusal after the hold window', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    clock = clock.add(LocalPreviewAdmission.verdictHold);
    route(2);
    expect(sent, [1, 2]);
  });

  test('socket close before the verdict: held frames carry over to the replacement socket', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    route(2);
    admission.revoke(); // closed before any verdict
    expect(admission.heldFramesForTesting, 2);
    admission.socketPublished(declared: true, send: send);
    route(3);
    expect(sent, isEmpty);
    admission.verdict(granted: false, socketDeclared: true, send: send);
    expect(sent, [1, 2, 3], reason: 'resolved against the replacement socket, oldest first');
  });

  test('a replacement socket that did not ask is a refusal: held frames go to it first', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    admission.revoke();
    admission.socketPublished(declared: false, send: send);
    expect(sent, [1]);
    route(2, declared: false);
    expect(sent, [1, 2]);
  });

  test('a grant on the replacement socket drops the carried copy; capture end always does', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    admission.revoke();
    admission.socketPublished(declared: true, send: send);
    admission.verdict(granted: true, socketDeclared: true, send: send);
    expect(admission.heldFramesForTesting, 0);
    expect(sent, isEmpty);
    admission.socketPublished(declared: true, send: send);
    route(2);
    admission.end();
    expect(admission.heldFramesForTesting, 0);
    admission.socketPublished(declared: false, send: send);
    expect(sent, isEmpty);
  });

  test('journal warm-up never suppresses: a refused-by-journal frame reaches even an admitted socket', () {
    admission.socketPublished(declared: true, send: send);
    admission.verdict(granted: true, socketDeclared: true, send: send);
    route(1); // the router only sees frames the journal refused (warm-up, transient)
    expect(sent, [1]);
  });

  test('a timed-out or overflowed hold is a refusal latched for that socket', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    clock = clock.add(LocalPreviewAdmission.verdictHold);
    route(2);
    expect(sent, [1, 2], reason: 'already streamed to the cloud');
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), false,
        reason: 'a late grant must not make this session look admitted');
    expect(admission.admitted, false);

    sent.clear();
    admission.socketPublished(declared: true, send: send);
    for (var i = 0; i <= LocalPreviewAdmission.maxHeldFrames; i++) {
      route(i);
    }
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), false);

    admission.socketPublished(declared: true, send: send);
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), true,
        reason: 'the latch is per socket; a replacement starts clean');
  });

  test('a mid-session client refusal hides the preview and blocks re-grants on that socket', () {
    admission.socketPublished(declared: true, send: send);
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), true);
    expect(admission.refuseForSocket(send: send), true);
    expect(admission.admitted, false);
    expect(preview.phase, LivePreviewPhase.inactive);
    expect(admission.verdict(granted: true, socketDeclared: true, send: send), false);
    route(7);
    expect(sent, [7], reason: 'streams like any other socket');
  });

  group('client gates mirror the batch route', () {
    LocalPreviewClientRefusal? gate({
      bool omiPendant = true,
      bool opusCodec = true,
      bool autoSync = true,
      bool batchMode = false,
      bool customStt = false,
      bool keptOnPhone = false,
      bool onboarding = false,
      bool journal = true,
    }) =>
        localPreviewClientRefusal(
          omiPendant: omiPendant,
          opusCodec: opusCodec,
          autoSyncOfflineRecordings: autoSync,
          batchModeEnabled: batchMode,
          customStt: customStt,
          keptOnPhone: keptOnPhone,
          onboarding: onboarding,
          journalInstalled: journal,
        );

    test('every per-session refusal has its own closed reason', () {
      expect(gate(), isNull);
      expect(gate(omiPendant: false), LocalPreviewClientRefusal.deviceUnsupported);
      expect(gate(opusCodec: false), LocalPreviewClientRefusal.codecUnsupported);
      expect(gate(autoSync: false), LocalPreviewClientRefusal.autoSyncOff);
      expect(gate(batchMode: true), LocalPreviewClientRefusal.transcribeLater);
      expect(gate(customStt: true), LocalPreviewClientRefusal.customStt);
      expect(gate(keptOnPhone: true), LocalPreviewClientRefusal.keptOnPhone);
      expect(gate(onboarding: true), LocalPreviewClientRefusal.onboarding);
      expect(gate(journal: false), LocalPreviewClientRefusal.noJournal);
    });

    test('reasons match the registered telemetry enum', () {
      expect(LocalPreviewClientRefusal.values.map((r) => r.wireName),
          LivePreviewNotRequestedReason.values.map((r) => r.wireName));
    });
  });

  group('verdict telemetry (observational)', () {
    List<Object> row(LocalPreviewVerdictReport r) =>
        [r.outcome, r.verdictLatencyMs, r.holdDurationMs, r.heldFrames, r.holdTimeoutReplayed];

    test('granted: latency from the request, hold time and frames, once per socket', () {
      admission.socketPublished(declared: true, send: send);
      clock = clock.add(const Duration(milliseconds: 300));
      route(1);
      route(2);
      clock = clock.add(const Duration(milliseconds: 900));
      admission.verdict(granted: true, socketDeclared: true, send: send);
      // Renewals (mobile_batch_admission every 60 s) never emit again.
      admission.verdict(granted: true, socketDeclared: true, send: send);
      expect(reports.map(row), [
        [LocalPreviewVerdictOutcome.granted, 1200, 900, 2, false]
      ]);
    });

    test('refused, with no frames held', () {
      admission.socketPublished(declared: true, send: send);
      clock = clock.add(const Duration(milliseconds: 450));
      admission.verdict(granted: false, socketDeclared: true, send: send);
      expect(reports.map(row), [
        [LocalPreviewVerdictOutcome.refused, 450, 0, 0, false]
      ]);
    });

    test('timeout forces a replay and is reported once; a late grant adds nothing', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      clock = clock.add(LocalPreviewAdmission.verdictHold);
      route(2);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      expect(reports.map(row), [
        [LocalPreviewVerdictOutcome.timeout, 10000, 10000, 1, true]
      ]);
    });

    test('overflow forces a replay', () {
      admission.socketPublished(declared: true, send: send);
      for (var i = 0; i <= LocalPreviewAdmission.maxHeldFrames; i++) {
        route(i);
      }
      expect(reports.map(row), [
        [LocalPreviewVerdictOutcome.overflow, 0, 0, LocalPreviewAdmission.maxHeldFrames, true]
      ]);
    });

    test('socket replacement reports each socket; close before a verdict is socket_closed', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      clock = clock.add(const Duration(seconds: 2));
      admission.revoke();
      admission.socketPublished(declared: true, send: send);
      clock = clock.add(const Duration(milliseconds: 700));
      admission.verdict(granted: false, socketDeclared: true, send: send);
      expect(reports.map(row), [
        [LocalPreviewVerdictOutcome.socketClosed, 2000, 2000, 1, false],
        [LocalPreviewVerdictOutcome.refused, 700, 0, 0, false],
      ]);
      // A replacement published without a close still settles its predecessor.
      admission.socketPublished(declared: true, send: send);
      admission.socketPublished(declared: true, send: send);
      admission.end();
      expect(reports.map((r) => r.outcome).skip(2),
          [LocalPreviewVerdictOutcome.socketClosed, LocalPreviewVerdictOutcome.socketClosed]);
    });

    test('a socket that did not declare local preview reports nothing', () {
      admission.socketPublished(declared: false, send: send);
      admission.verdict(granted: true, socketDeclared: false, send: send);
      admission.revoke();
      expect(reports, isEmpty);
    });

    test('verdict outcomes match the registered telemetry enum', () {
      expect(LocalPreviewVerdictOutcome.values.map((v) => v.wireName),
          LivePreviewVerdictVerdict.values.map((v) => v.wireName));
    });
  });

  group('custody-confirmed routing', () {
    test('a frame the WAL refused is never held: held frames first, then it, in order', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      route(2);
      route(3, walAccepted: false);
      expect(sent, [1, 2, 3]);
      expect(admission.heldFramesForTesting, 0);
    });

    test('a grant drops only WAL-accepted held frames; anything else still reaches the socket', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      route(2);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      expect(sent, isEmpty, reason: 'every held frame was WAL-accepted');
    });
  });

  test('capture end sends held frames to a still-open, ungranted socket first', () {
    admission.socketPublished(declared: true, send: send);
    route(1);
    route(2);
    admission.end(send: send);
    expect(sent, [1, 2]);
    expect(admission.heldFramesForTesting, 0);

    sent.clear();
    admission.socketPublished(declared: true, send: send);
    route(4);
    admission.end();
    expect(sent, isEmpty, reason: 'no open socket and no account change: the WAL finalizes them');
  });

  group('granted frames stay recoverable until the WAL makes them durable', () {
    test('copies are kept after a grant and sent to the open socket at end, even when admitted', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      route(2);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      expect(sent, isEmpty);
      expect(admission.notYetDurableForTesting, 2);
      admission.end(send: send);
      expect(sent, [1, 2]);
      expect(admission.notYetDurableForTesting, 0);
    });

    test('copies are released, oldest first, once the WAL reports them durable', () {
      final volatile = <int>{1, 2};
      admission.mayBeVolatile = (frame) => volatile.contains(frame.payload.single);
      admission.socketPublished(declared: true, send: send);
      route(1);
      route(2);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      volatile.remove(1);
      clock = clock.add(const Duration(seconds: 6));
      route(3, declared: false); // any routing pass prunes (at most every 5 s)
      expect(admission.notYetDurableForTesting, 1);
      volatile.clear();
      admission.end(send: send);
      expect(sent, [3], reason: 'durable copies are not resent');
    });

    test('account change with no socket preserves the copies and any held frames for the old owner', () {
      final preserved = <List<int>>[];
      admission.socketPublished(declared: true, send: send);
      route(1);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      admission.revoke(); // socket closed
      admission.socketPublished(declared: true, send: send);
      route(2); // held on the replacement socket, which then closes
      admission.revoke();
      admission.end(preserveForAccountChange: (frames) {
        preserved.addAll(frames.map((frame) => frame.payload));
        return true;
      });
      expect(preserved, [
        [1],
        [2]
      ]);
      expect(sent, isEmpty);
    });

    test('a plain stop with no socket does not preserve (the WAL finalizes its tail)', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      admission.revoke();
      admission.end();
      expect(sent, isEmpty);
      expect(admission.notYetDurableForTesting, 0);
    });
  });

  group('verdict deadline is latched by a timer', () {
    test('a quiet interval: the deadline fires, replays held frames, and a later grant is a refusal', () {
      admission.socketPublished(declared: true, send: send);
      expect(deadlines.single.$1, LocalPreviewAdmission.verdictHold);
      route(1);
      route(2);
      clock = clock.add(LocalPreviewAdmission.verdictHold);
      deadlines.single.$2(); // no frame arrives; the timer fires
      expect(sent, [1, 2], reason: 'held frames replayed at the deadline');
      expect(admission.verdict(granted: true, socketDeclared: true, send: send), false);
      expect(admission.admitted, false);
      expect(reports.single.outcome, LocalPreviewVerdictOutcome.timeout);
      expect(reports.single.holdTimeoutReplayed, true);
    });

    test('a grant after the deadline with the timer not yet run is a refusal too', () {
      admission.socketPublished(declared: true, send: send);
      route(1);
      clock = clock.add(const Duration(seconds: 11));
      expect(admission.verdict(granted: true, socketDeclared: true, send: send), false);
      expect(sent, [1]);
      expect(reports.single.outcome, LocalPreviewVerdictOutcome.timeout);
      deadlines.single.$2(); // a late timer callback changes nothing
      expect(sent, [1]);
      expect(reports, hasLength(1));
    });

    test('an in-time grant cancels the deadline', () {
      admission.socketPublished(declared: true, send: send);
      clock = clock.add(const Duration(seconds: 3));
      expect(admission.verdict(granted: true, socketDeclared: true, send: send), true);
      deadlines.single.$2();
      expect(admission.admitted, true);
      expect(reports.single.outcome, LocalPreviewVerdictOutcome.granted);
    });
  });

  group('durability copies under pressure', () {
    test('the cap never evicts a non-durable copy; new suppression stops instead', () {
      final capped = LocalPreviewAdmission(now: () => clock, onChanged: () {}, copyCap: 3)..preview = preview;
      final durable = <int>{};
      capped.mayBeVolatile = (frame) => !durable.contains(frame.payload.single);
      void routeCapped(int value) => capped.routePendant(frame(value), socketDeclared: true, send: send);

      capped.socketPublished(declared: true, send: send);
      routeCapped(1);
      routeCapped(2);
      capped.verdict(granted: true, socketDeclared: true, send: send);
      expect(capped.notYetDurableForTesting, 2);

      capped.revoke();
      capped.socketPublished(declared: true, send: send);
      routeCapped(3); // 2 copies + 1 held reaches the cap of 3
      routeCapped(4); // at the cap: holding stops, everything streams in order
      expect(sent, [3, 4]);
      expect(capped.notYetDurableForTesting, 2, reason: 'no non-durable copy was dropped');
      expect(capped.verdict(granted: true, socketDeclared: true, send: send), false,
          reason: 'a capped hold is latched as refused like an overflow');

      durable.addAll([1, 2]);
      clock = clock.add(const Duration(seconds: 6));
      routeCapped(5);
      expect(capped.notYetDurableForTesting, 0, reason: 'released only once strictly durable');
      capped.end();
    });

    test('a flush in progress (written, index not saved) is not durable: the copy is preserved at account change', () {
      // The probe is LocalWalSyncImpl.isFrameDurable, which is false until the
      // index save of the current generation completes (unit-tested there).
      var indexSaved = false;
      admission.mayBeVolatile = (frame) => !indexSaved;
      admission.socketPublished(declared: true, send: send);
      route(1);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      admission.revoke();
      clock = clock.add(const Duration(seconds: 6));
      final preserved = <List<int>>[];
      admission.end(preserveForAccountChange: (frames) {
        preserved.addAll(frames.map((f) => f.payload));
        return true;
      });
      expect(preserved, [
        [1]
      ]);
      expect(indexSaved, isFalse);
    });

    test('account change preserves only copies the strict probe says are not durable', () {
      final durable = <int>{1};
      admission.mayBeVolatile = (frame) => !durable.contains(frame.payload.single);
      admission.socketPublished(declared: true, send: send);
      route(1);
      route(2);
      admission.verdict(granted: true, socketDeclared: true, send: send);
      admission.revoke();
      final preserved = <List<int>>[];
      admission.end(preserveForAccountChange: (frames) {
        preserved.addAll(frames.map((f) => f.payload));
        return true;
      });
      expect(preserved, [
        [2]
      ]);
    });
  });
}
