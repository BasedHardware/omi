import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_end.dart';

DateTime at(int seconds) => DateTime.fromMillisecondsSinceEpoch(seconds * 1000, isUtc: true);

void main() {
  group('CaptureEndDetector', () {
    test('silence end fires once, at last speech plus the timer, only while packets arrive', () {
      final detector = CaptureEndDetector()..silenceSeconds = 120;
      detector.speech('s', at(1000));
      expect(detector.packet('s', at(1119)), isNull);
      final end = detector.packet('s', at(1125))!;
      expect(end.type, CaptureEndType.silenceBackstop);
      expect(end.lastSpeechAt, at(1000));
      expect(end.decidedAt, at(1120));
      expect(detector.packet('s', at(1300)), isNull, reason: 'one end per silence');
    });

    test('the chunk seal does not matter: only speech moves the clock', () {
      final detector = CaptureEndDetector()..silenceSeconds = 120;
      detector.speech('s', at(1000));
      detector.speech('s', at(1050));
      detector.speech('s', at(1040));
      expect(detector.lastSpeechAt, at(1050));
      expect(detector.packet('s', at(1125)), isNull);
      expect(detector.packet('s', at(1170))!.decidedAt, at(1170));
    });

    test('speech after a silence end re-opens the recording with a later end', () {
      final detector = CaptureEndDetector()..silenceSeconds = 60;
      detector.speech('s', at(1000));
      expect(detector.packet('s', at(1061)), isNotNull);
      detector.speech('s', at(1100));
      final second = detector.packet('s', at(1165))!;
      expect(second.lastSpeechAt, at(1100));
      expect(second.decidedAt, at(1160));
    });

    test('no timer from the server means no silence end', () {
      final detector = CaptureEndDetector();
      detector.speech('s', at(1000));
      expect(detector.packet('s', at(9000)), isNull);
      detector.silenceSeconds = 0;
      expect(detector.silenceSeconds, isNull);
      expect(detector.packet('s', at(9000)), isNull);
    });

    test('an explicit stop and a lost pendant are typed differently', () {
      final detector = CaptureEndDetector()..silenceSeconds = 120;
      detector.speech('s', at(1000));
      final stop = detector.stopped('s', CaptureEndType.userInitiated, at(1010))!;
      expect(stop.type.wire, 'user_initiated');
      expect(stop.lastSpeechAt, at(1000));
      expect(stop.decidedAt, at(1010));
      detector.speech('t', at(2000));
      expect(detector.stopped('t', CaptureEndType.disconnect, at(2003))!.type.wire, 'disconnect');
    });

    test('a stop with no speech is still reported, with no speech time', () {
      final detector = CaptureEndDetector()..silenceSeconds = 120;
      expect(detector.stopped('s', CaptureEndType.userInitiated, at(10)), isNull,
          reason: 'the lane never journaled a packet of this recording');
      expect(detector.packet('s', at(1000)), isNull);
      expect(detector.packet('s', at(9000)), isNull, reason: 'no speech, so no silence end');
      final stop = detector.stopped('s', CaptureEndType.disconnect, at(9001))!;
      expect(stop.lastSpeechAt, isNull);
      expect(stop.decidedAt, at(9001));
      expect(detector.stopped('s', CaptureEndType.disconnect, at(9002)), isNull, reason: 'one end per stop');
    });

    test('another recording, or no recording, has no end', () {
      final detector = CaptureEndDetector()..silenceSeconds = 120;
      detector.speech('s', at(1000));
      expect(detector.stopped('other', CaptureEndType.userInitiated, at(1010)), isNull);
      detector.speech(null, at(1));
      detector.speech('', at(1));
      expect(detector.packet(null, at(5000)), isNull);
      expect(detector.lastSpeechAt, at(1000));
      expect(detector.stopped('s', CaptureEndType.userInitiated, at(1010)), isNotNull);
    });

    test('a new recording starts with a clean clock', () {
      final detector = CaptureEndDetector()..silenceSeconds = 60;
      detector.speech('s', at(1000));
      detector.speech('t', at(5000));
      expect(detector.packet('t', at(5061))!.recordingSessionId, 't');
      // Packets of a new recording reset the clock: the old speech time is gone.
      expect(detector.packet('u', at(9000)), isNull);
      expect(detector.lastSpeechAt, isNull);
    });
  });

  group('CaptureEndReporter', () {
    late List<(String, int)> sent;
    late Map<String, int> pending;
    late bool disabled;
    late bool accept;
    late int settled;
    late CaptureEndReporter reporter;

    CaptureEndSignal signal(String id, {int decided = 1010}) => CaptureEndSignal(
        recordingSessionId: id, type: CaptureEndType.userInitiated, lastSpeechAt: at(1000), decidedAt: at(decided));

    setUp(() {
      sent = [];
      pending = {};
      disabled = false;
      accept = true;
      settled = 0;
      reporter = CaptureEndReporter(
        post: (signal, {required pendingWals, required sentAt}) async {
          sent.add((signal.recordingSessionId, pendingWals));
          return accept;
        },
        pendingWals: (signal) => pending[signal.recordingSessionId] ?? 0,
        disabled: () async => disabled,
        settle: () async => settled++,
        now: () => at(2000),
      );
    });

    test('two calls for a long recording: at the end, and when the last file is accepted', () async {
      pending['s'] = 5;
      await reporter.report(signal('s'));
      for (final left in [4, 3, 2, 1]) {
        pending['s'] = left;
        await reporter.uploadAccepted('s');
      }
      expect(sent, [('s', 5)], reason: 'intermediate acceptances send nothing');
      pending['s'] = 0;
      await reporter.uploadAccepted('s');
      await reporter.uploadAccepted('s');
      expect(sent, [('s', 5), ('s', 0)]);
    });

    test('the open chunk is settled into a file before the first count, and only then', () async {
      // The count becomes visible only once the final chunk is registered.
      final late_ = CaptureEndReporter(
        post: (signal, {required pendingWals, required sentAt}) async {
          sent.add((signal.recordingSessionId, pendingWals));
          return true;
        },
        pendingWals: (signal) => pending[signal.recordingSessionId] ?? 0,
        disabled: () async => false,
        settle: () async {
          settled++;
          pending['s'] = 1; // the last sealed file appears in the index
        },
      );
      await late_.report(signal('s'));
      expect(sent, [('s', 1)], reason: 'never zero while the final file is still being published');
      pending['s'] = 0;
      await late_.uploadAccepted('s');
      expect(sent, [('s', 1), ('s', 0)]);
      expect(settled, 1, reason: 'resends do not seal again');
    });

    test('nothing pending at the end is one call', () async {
      await reporter.report(signal('s'));
      await reporter.uploadAccepted('s');
      expect(sent, [('s', 0)]);
    });

    test('a refused first report is retried on the next accepted file', () async {
      pending['s'] = 2;
      accept = false;
      await reporter.report(signal('s'));
      accept = true;
      pending['s'] = 1;
      await reporter.uploadAccepted('s');
      pending['s'] = 0;
      await reporter.uploadAccepted('s');
      expect(sent, [('s', 2), ('s', 1), ('s', 0)]);
    });

    test('uploads of a recording with no reported end send nothing', () async {
      await reporter.uploadAccepted('s');
      await reporter.uploadAccepted(null);
      expect(sent, isEmpty);
    });

    test('the kill switch sends nothing, seals nothing and forgets the end', () async {
      disabled = true;
      await reporter.report(signal('s'));
      disabled = false;
      await reporter.uploadAccepted('s');
      expect(sent, isEmpty);
      expect(settled, 0);
    });

    test('a later end of the same recording replaces the earlier one', () async {
      pending['s'] = 1;
      await reporter.report(signal('s'));
      await reporter.report(signal('s', decided: 1500));
      pending['s'] = 0;
      await reporter.uploadAccepted('s');
      expect(sent, [('s', 1), ('s', 1), ('s', 0)]);
    });

    test('a failing transport never surfaces and keeps the end for a retry', () async {
      final failing = CaptureEndReporter(
        post: (signal, {required pendingWals, required sentAt}) async => throw StateError('offline'),
        pendingWals: (_) => 0,
        disabled: () async => false,
      );
      await failing.report(signal('s'));
      await failing.uploadAccepted('s');
    });

    test('only a bounded number of open ends is tracked', () async {
      pending.addAll({for (var i = 0; i < 40; i++) 'r$i': 1});
      for (var i = 0; i < 40; i++) {
        await reporter.report(signal('r$i'));
      }
      sent.clear();
      pending['r0'] = 0;
      await reporter.uploadAccepted('r0');
      expect(sent, isEmpty, reason: 'the oldest open end was dropped');
      pending['r39'] = 0;
      await reporter.uploadAccepted('r39');
      expect(sent, [('r39', 0)]);
    });
  });
}
