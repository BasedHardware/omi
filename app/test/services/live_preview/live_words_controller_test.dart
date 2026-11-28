import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/speech_after_end.dart';
import 'package:omi/utils/reliability_experiments.dart';

import '../../support/live_preview_fakes.dart';

// Reliability experiment vendor_recognizer_on_opened_app, inside the live-preview controller: one
// merged list behind `lines`, the phone's recogniser running without the server's grant, the test-only
// mute, the stalled-recogniser watchdog and the local counters.

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeLivePreviewEngine engine;
  late LivePreviewController preview;
  late List<String> logged;
  var clock = DateTime.utc(2026, 11, 25, 12);
  var muted = false;

  DateTime at(double seconds) => DateTime.utc(2026, 11, 25, 12).add(Duration(milliseconds: (seconds * 1000).round()));

  LivePreviewLine vendor(String id, String text, double start, double end) {
    final words = text.split(' ');
    final step = (end - start) / words.length;
    return LivePreviewLine(
      id: id,
      text: text,
      isFinal: true,
      startedAt: at(start),
      endedAt: at(end),
      firstSeenAt: clock,
      spans: [
        for (var i = 0; i < words.length; i++)
          LivePreviewSpan(text: words[i], startedAt: at(start + i * step), endedAt: at(start + (i + 1) * step - 0.05)),
      ],
    );
  }

  List<String> texts() => [for (final line in preview.lines) line.text];

  setUp(() {
    engine = FakeLivePreviewEngine();
    logged = [];
    muted = false;
    clock = DateTime.utc(2026, 11, 25, 12);
    preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
      now: () => clock,
      decodeOpus: (opus) => Int16List.fromList(List.filled(opus.length * 4, opus.first)),
      ownResultsMuted: () => muted,
      liveWordsLog: (event, fields) => logged.add(event),
    );
  });
  tearDown(() {
    preview.dispose();
    ReliabilityExperiments.overrideForTesting(null);
  });

  group('one merged list', () {
    test('without vendor lines `lines` is the same list object as before', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      final before = preview.lines;
      engine.emit('s1', 'hello', true, startedAt: at(0), endedAt: at(1));
      await pumpEventQueue();
      expect(identical(preview.lines, before), isTrue);
      expect(texts(), ['hello']);
    });

    test('vendor lines are ignored while the preview is not running', () {
      preview.onVendorLines([vendor('v1', 'nobody is looking', 0, 2)]);
      expect(preview.lines, isEmpty);
      expect(preview.vendorWordsSeen, 0);
    });

    test('vendor words show only where the phone\'s recogniser returned nothing, and notify', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('s1', 'good morning', true, startedAt: at(0), endedAt: at(2));
      await pumpEventQueue();
      var notified = 0;
      preview.addListener(() => notified++);
      clock = at(18);
      preview.onVendorLines([vendor('v1', 'Good morning.', 0, 2), vendor('v2', 'nobody heard this', 10, 13)]);
      expect(texts(), ['good morning', 'nobody heard this']);
      expect(preview.latestLine, 'nobody heard this');
      expect(notified, 1);
      // The same line grows under its id.
      preview.onVendorLines([vendor('v2', 'nobody heard this at all', 10, 15)]);
      expect(texts(), ['good morning', 'nobody heard this at all']);
      expect(preview.vendorLinesForTesting, hasLength(2));
    });

    test('the phone\'s recogniser filling the stretch later drops the vendor words', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      clock = at(15);
      preview.onVendorLines([vendor('v1', 'late but there', 9, 12)]);
      expect(texts(), ['late but there']);
      engine.emit('s9', 'late but there', false, startedAt: at(9), endedAt: at(12));
      await pumpEventQueue();
      expect(texts(), ['late but there']);
      expect(preview.lines.single.id, 's9');
    });

    test('counters: vendor words seen, and those that filled a stretch the phone had nothing for', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('s1', 'one two', true, startedAt: at(0), endedAt: at(2));
      await pumpEventQueue();
      clock = at(20);
      preview.onVendorLines([vendor('v1', 'One two.', 0, 2), vendor('v2', 'three four five', 10, 13)]);
      expect(preview.vendorWordsSeen, 5);
      expect(preview.vendorFilledWords, 3);
      expect(preview.vendorFilledSpeechMs, closeTo(2850, 5));
      // A longer version of the same line counts only its new words.
      preview.onVendorLines([vendor('v2', 'three four five six seven eight', 10, 16)]);
      expect(preview.vendorWordsSeen, 8);
      expect(preview.vendorFilledWords, 6);
      // Words heard count towards "something was said since the last End".
      expect(preview.totalWordsSeen, 2 + 8);
    });

    test('a capture end clears both sources; a conversation-long silence starts a new session', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      clock = at(5);
      preview.onVendorLines([vendor('v1', 'first conversation', 0, 2)]);
      final session = preview.sessionGeneration;
      clock = at(5 + 121);
      preview.onVendorLines([vendor('v2', 'second conversation', 122, 124)]);
      expect(texts(), ['second conversation']);
      expect(preview.sessionGeneration, session + 1);
      preview.endCapture();
      expect(preview.lines, isEmpty);
      expect(preview.vendorLinesForTesting, isEmpty);
    });

    test('the after-End rule reads the merged words: only a word spoken at or after the End counts', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('s1', 'before the end', true, startedAt: at(0), endedAt: at(3));
      await pumpEventQueue();
      final end = at(10);
      clock = at(14);
      // A vendor line that began before the End and has not reached it yet.
      preview.onVendorLines([vendor('v1', 'still before', 8, 9.5)]);
      expect(SpeechAfterEnd.heard(preview.lines, end), isFalse);
      clock = at(17);
      // The same line runs on past the End: its later words were spoken after it.
      preview.onVendorLines([vendor('v1', 'still before and now after it', 8, 14)]);
      expect(SpeechAfterEnd.heard(preview.lines, end), isTrue);
      // Six words spread over 8..14 s: the first one that starts at or after 10 s starts at 10 s.
      expect(SpeechAfterEnd.firstHeard(preview.lines, end), at(10));
      expect(SpeechAfterEnd.firstHeard(preview.lines, at(60)), isNull);
    });
  });

  group('the phone\'s recogniser without the server\'s grant', () {
    test('capture in front starts it; leaving the front stops it', () async {
      preview.setFrontCapture(true, language: 'de');
      expect(preview.phase, LivePreviewPhase.starting);
      await pumpEventQueue();
      expect(engine.startedLanguages, ['de']);
      expect(preview.phase, LivePreviewPhase.streaming);
      expect(preview.frontAdmitted, isTrue);
      engine.emit('s1', 'guten tag', true, startedAt: at(0), endedAt: at(1));
      await pumpEventQueue();
      expect(texts(), ['guten tag']);
      preview.setFrontCapture(false, language: 'de');
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.inactive);
      expect(engine.stops, 1);
      // Lines are kept for a quick return, as after a revoked grant.
      expect(texts(), ['guten tag']);
    });

    test('a grant on top changes nothing; the grant ending keeps it while capture is in front', () async {
      preview.setFrontCapture(true, language: 'en');
      await pumpEventQueue();
      preview.admit(language: 'en');
      await pumpEventQueue();
      expect(engine.startedLanguages, hasLength(1));
      preview.revoke();
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.streaming);
      expect(engine.stops, 0);
      preview.setFrontCapture(false, language: 'en');
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.inactive);
    });

    test('a granted session keeps its recogniser when the app leaves the front', () async {
      preview.admit(language: 'en');
      preview.setFrontCapture(true, language: 'en');
      await pumpEventQueue();
      preview.setFrontCapture(false, language: 'en');
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.streaming);
      expect(engine.stops, 0);
      preview.revoke();
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.inactive);
    });

    test('without the experiment\'s call a grant and its end behave as before', () async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      expect(preview.frontAdmitted, isFalse);
      preview.revoke();
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.inactive);
      expect(engine.stops, 1);
    });

    test('a capture end forgets both reasons', () async {
      preview.setFrontCapture(true, language: 'en');
      await pumpEventQueue();
      preview.endCapture();
      expect(preview.frontAdmitted, isFalse);
      expect(preview.phase, LivePreviewPhase.inactive);
      preview.setFrontCapture(true, language: 'en');
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.streaming);
    });
  });

  group('test-only mute', () {
    test('muted, the recogniser runs and is fed but its results never show; vendor lines all show', () async {
      muted = true;
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('s1', 'the phone heard this', true, startedAt: at(0), endedAt: at(2));
      await pumpEventQueue();
      expect(preview.lines, isEmpty);
      expect(preview.ownResultsHeard, 1);
      clock = at(7);
      preview.onVendorLines([vendor('v1', 'The phone heard this.', 0, 2)]);
      expect(texts(), ['The phone heard this.']);
      // A muted recogniser that still reports is not stalled.
      expect(preview.watchdogRestarts, 0);
    });

    test('the registered experiment name is what mutes by default', () async {
      final plain = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        now: () => clock,
      );
      addTearDown(plain.dispose);
      plain.admit(language: 'en');
      await pumpEventQueue();
      ReliabilityExperiments.overrideForTesting({LivePreviewController.muteExperiment});
      engine.emit('s1', 'muted', true);
      await pumpEventQueue();
      expect(plain.lines, isEmpty);
      ReliabilityExperiments.overrideForTesting(null);
      engine.emit('s2', 'shown', true);
      await pumpEventQueue();
      expect(plain.lines.single.text, 'shown');
    });
  });

  group('stalled-recogniser watchdog', () {
    Future<void> streaming() async {
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('s1', 'it worked at first', true, startedAt: at(0), endedAt: at(2));
      await pumpEventQueue();
      clock = at(2);
    }

    test('vendor speech for 10 s with no result from a streaming recogniser restarts it once', () async {
      await streaming();
      clock = at(11);
      preview.onVendorLines([vendor('v1', 'the phone is silent now', 6, 9)]);
      expect(preview.watchdogRestarts, 0); // Only 5 s since the unanswered speech began.
      clock = at(17);
      preview.onVendorLines([vendor('v1', 'the phone is silent now and still nothing', 6, 14)]);
      expect(preview.watchdogRestarts, 1);
      expect(preview.phase, LivePreviewPhase.starting);
      await pumpEventQueue();
      expect(engine.stops, 1);
      expect(engine.startedLanguages, ['en', 'en']);
      expect(preview.phase, LivePreviewPhase.streaming);
      expect(logged, contains('own_recogniser_restart'));
      // Shown lines survive the restart, and the restarted recogniser's results show.
      expect(texts().first, 'it worked at first');
      engine.emit('s2', 'back again', true, startedAt: at(18), endedAt: at(19));
      await pumpEventQueue();
      expect(texts().last, 'back again');
    });

    test('it restarts at most once in three minutes', () async {
      await streaming();
      clock = at(17);
      preview.onVendorLines([vendor('v1', 'a b c d e f', 6, 14)]);
      await pumpEventQueue();
      expect(preview.watchdogRestarts, 1);
      clock = at(60);
      preview.onVendorLines([vendor('v2', 'g h i j k l', 40, 55)]);
      expect(preview.watchdogRestarts, 1);
      clock = at(17 + 181);
      preview.onVendorLines([vendor('v3', 'm n o p q r', 180, 190)]);
      expect(preview.watchdogRestarts, 2);
    });

    test('a recogniser that keeps reporting is never restarted', () async {
      await streaming();
      for (var second = 4; second < 60; second += 4) {
        clock = at(second.toDouble());
        engine.emit('s$second', 'words', true, startedAt: at(second - 1), endedAt: at(second.toDouble()));
        await pumpEventQueue();
        preview.onVendorLines([vendor('v$second', 'same words here too', second - 7, second - 5)]);
      }
      expect(preview.watchdogRestarts, 0);
      expect(engine.stops, 0);
    });

    test('a few stray vendor words are not a stall', () async {
      await streaming();
      clock = at(30);
      preview.onVendorLines([vendor('v1', 'mm hm', 10, 11)]);
      expect(preview.watchdogRestarts, 0);
    });

    test('a recogniser that is not running is not restarted', () async {
      engine.nextStart = const LivePreviewStart.none(LivePreviewReason.localeUnsupported);
      preview.setFrontCapture(true, language: 'xx');
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.unavailable);
      clock = at(30);
      preview.onVendorLines([vendor('v1', 'only the vendor hears this speech', 5, 20)]);
      expect(preview.watchdogRestarts, 0);
      expect(texts(), ['only the vendor hears this speech']);
      expect(engine.startedLanguages, hasLength(1));
    });
  });
}
