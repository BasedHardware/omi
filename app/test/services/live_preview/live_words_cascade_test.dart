import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_coverage.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/live_tail.dart';
import 'package:omi/services/live_preview/live_words_coordinator.dart';
import 'package:omi/services/live_preview/live_words_cut.dart';
import 'package:omi/services/live_preview/live_words_merge.dart';
import 'package:omi/services/live_preview/own_draft_language.dart';
import 'package:omi/services/live_preview/speech_after_end.dart';
import 'package:omi/services/live_preview/vendor_live_words.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/reliability_experiments.dart';

import '../../support/live_preview_fakes.dart';
import 'live_words_coordinator_test.dart' show FakeCapture;
import 'vendor_live_words_test.dart' show FakeSocket, pendantPacket;

// Reliability experiment live_words_cascade (needs vendor_recognizer_on_opened_app).
// A. The merged live words put the vendor first: its words where it has them, the phone's own
//    recogniser's only where it has none; no draft for a language the phone's recogniser cannot do.
// B. An End cuts the live words at the End instant, per word, for every screen, and tells the display
//    connection.
// C. The End request carries the words shown for the conversation being ended.
// Off, every one of these is what it was.

class _TestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.example.test/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

final t0 = DateTime.utc(2026, 11, 26, 21);
DateTime at(double seconds) => t0.add(Duration(milliseconds: (seconds * 1000).round()));

/// A line with one span per word, the words evenly spread over [start]..[end] seconds.
LivePreviewLine line(String id, String text, double start, double end, {bool isFinal = true}) {
  final words = text.split(' ');
  final step = (end - start) / words.length;
  return LivePreviewLine(
    id: id,
    text: text,
    isFinal: isFinal,
    startedAt: at(start),
    endedAt: at(end),
    firstSeenAt: at(end),
    spans: [
      for (var i = 0; i < words.length; i++)
        LivePreviewSpan(text: words[i], startedAt: at(start + i * step), endedAt: at(start + (i + 1) * step - 0.05)),
    ],
  );
}

List<String> textsOf(Iterable<LivePreviewLine> lines) => [for (final line in lines) line.text];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('A: the merge with the roles reversed', () {
    test('the vendor\'s words replace the phone\'s recogniser\'s words for the same audio, word by word', () {
      final own = [line('a1', 'i scream for the bored meeting on monday', 0, 8)];
      final vendor = [line('v1', 'Ice cream for the board', 0, 4.4)];
      final merged = LiveWordsMerge.cascade(own, vendor);
      // The vendor's line whole; of the draft only the words the vendor has nothing for (1 s tolerance).
      expect(textsOf(merged), ['Ice cream for the board', 'on monday']);
      expect(merged.last.id, 'a1#0');
      expect(merged.last.startedAt, at(6));
      expect(merged.last.spans, hasLength(2));
    });

    test('where the vendor has nothing yet the phone\'s recogniser\'s words are the draft', () {
      final own = [line('a1', 'first sentence', 0, 2), line('a2', 'the newest words', 10, 13, isFinal: false)];
      final vendor = [line('v1', 'First sentence.', 0, 2)];
      final merged = LiveWordsMerge.cascade(own, vendor);
      expect(textsOf(merged), ['First sentence.', 'the newest words']);
      expect(merged.last.id, 'a2');
      expect(merged.last.isFinal, isFalse);
      expect(merged.last.startedAt, at(10));
    });

    test('a draft line the vendor covers in the middle becomes two', () {
      final own = [line('a1', 'one two three four five six seven eight nine ten', 0, 10)];
      final vendor = [line('v1', 'Four five', 4, 5.5)];
      final merged = LiveWordsMerge.cascade(own, vendor);
      expect(textsOf(merged), ['one two three', 'Four five', 'eight nine ten']);
      expect([for (final l in merged) l.id], ['a1#0', 'v1', 'a1#1']);
    });

    test('with no vendor words the list is the phone\'s recogniser\'s own, and the reverse', () {
      final own = [line('a1', 'only me', 0, 1)];
      final vendor = [line('v1', 'Only it.', 5, 6)];
      expect(identical(LiveWordsMerge.cascade(own, const []), own), isTrue);
      expect(identical(LiveWordsMerge.cascade(const [], vendor), vendor), isTrue);
    });

    test('a draft line without word times is taken or dropped whole', () {
      LivePreviewLine plain(String id, double start, double end) => LivePreviewLine(
          id: id, text: 'plain $id', isFinal: true, startedAt: at(start), endedAt: at(end), firstSeenAt: at(end));
      final merged =
          LiveWordsMerge.cascade([plain('a1', 0, 2), plain('a2', 9, 11)], [line('v1', 'Covered.', 0.5, 1.5)]);
      expect(textsOf(merged), ['Covered.', 'plain a2']);
    });

    test('the baseline merge is untouched: the phone\'s recogniser first, the vendor in its holes', () {
      final own = [line('a1', 'i scream for the bored', 0, 4.4)];
      final vendor = [line('v1', 'Ice cream for the board meeting on Monday', 0, 8)];
      expect(textsOf(LiveWordsMerge.merge(own, vendor)), ['i scream for the bored', 'on Monday']);
    });
  });

  group('A: the draft reads as one paragraph, at the same left edge', () {
    /// A phrase as the phone's recogniser returns it: every word piece carries its own leading space.
    LivePreviewLine phrase(String id, String text, double start, double end, {bool isFinal = true}) {
      final plain = line(id, text, start, end, isFinal: isFinal);
      return LivePreviewLine(
        id: id,
        text: text,
        isFinal: isFinal,
        startedAt: plain.startedAt,
        endedAt: plain.endedAt,
        firstSeenAt: plain.firstSeenAt,
        spans: [
          for (final span in plain.spans)
            LivePreviewSpan(text: ' ${span.text}', startedAt: span.startedAt, endedAt: span.endedAt),
        ],
      );
    }

    test('text rebuilt from word pieces has no space at its start and single spaces inside', () {
      expect(LivePreviewLine.textOf(phrase('a', 'where are we', 0, 3).spans), 'where are we');
      // The vendor's words carry no spaces of their own.
      expect(LivePreviewLine.textOf(line('v', 'Where are we', 0, 3).spans), 'Where are we');
      // A piece without a leading space is glued on, as the recogniser meant it (punctuation).
      expect(
          LivePreviewLine.textOf([
            LivePreviewSpan(text: ' wait', startedAt: at(0), endedAt: at(1)),
            LivePreviewSpan(text: ',', startedAt: at(1), endedAt: at(1)),
            LivePreviewSpan(text: ' what', startedAt: at(1), endedAt: at(2)),
          ]),
          'wait, what');
    });

    test('a draft line the vendor covers in part does not start with a space', () {
      final merged = LiveWordsMerge.cascade([phrase('a1', 'i scream for the bored meeting on monday', 0, 8)],
          [line('v1', 'Ice cream for the board', 0, 4.4)]);
      expect(textsOf(merged), ['Ice cream for the board', 'on monday']);
      // Cut at an End, and cut by stored text: the same.
      expect(textsOf(LiveWordsCut.after([phrase('a1', 'one two three four', 0, 4)], at(2))), ['three four']);
    });

    test('the phone\'s recogniser\'s phrases are one paragraph, not one each', () {
      final own = [
        phrase('a1', 'so I think', 0, 1.2),
        phrase('a2', 'we should ship', 1.4, 2.6),
        phrase('a3', 'on friday', 2.8, 3.6, isFinal: false),
      ];
      final merged = LiveWordsMerge.cascade(own, const []);
      expect(textsOf(merged), ['so I think we should ship on friday']);
      expect(merged.single.id, 'p:a1');
      expect(merged.single.spans, hasLength(8));
      expect(merged.single.startedAt, at(0));
      // Still being revised while its newest phrase is.
      expect(merged.single.isFinal, isFalse);
      // The paragraph keeps its id as it grows, so it keeps its place on screen.
      final grown = LiveWordsMerge.cascade([...own, phrase('a4', 'at the latest', 3.8, 5)], const []);
      expect(grown.single.id, 'p:a1');
    });

    test('a pause of three seconds starts a new paragraph, as it does in the vendor\'s lines', () {
      final merged = LiveWordsMerge.cascade(
          [phrase('a1', 'first thought', 0, 1), phrase('a2', 'goes on', 1.5, 2.5), phrase('a3', 'much later', 9, 10)],
          const []);
      expect(textsOf(merged), ['first thought goes on', 'much later']);
    });

    test('the vendor\'s lines are never joined, and the draft after them is its own paragraph', () {
      final vendor = [line('v1', 'First sentence.', 0, 2), line('v2', 'Second sentence.', 2.2, 4)];
      final own = [
        phrase('a1', 'first sentence', 0, 2),
        phrase('a2', 'second sentence', 2.2, 4),
        phrase('a3', 'and now', 6, 7),
        phrase('a4', 'the newest words', 7.2, 8.5),
      ];
      final merged = LiveWordsMerge.cascade(own, vendor);
      expect(textsOf(merged), ['First sentence.', 'Second sentence.', 'and now the newest words']);
      expect(identical(merged[0], vendor[0]) && identical(merged[1], vendor[1]), isTrue);
    });

    test('a very long stretch is broken like a vendor line, and a phrase without word times stands alone', () {
      final long = [for (var i = 0; i < 40; i++) phrase('a$i', 'twenty five characters ok', i * 2.0, i * 2.0 + 1.8)];
      final merged = LiveWordsMerge.cascade(long, const []);
      expect(merged.length, greaterThan(1));
      expect(merged.every((l) => l.text.length <= LiveWordsMerge.paragraphMaxChars), isTrue);
      final untimed = LivePreviewLine(id: 'u', text: 'no word times', isFinal: true, startedAt: at(1), endedAt: at(2));
      expect(
          textsOf(
              LiveWordsMerge.cascade([phrase('a1', 'one', 0, 0.5), untimed, phrase('a2', 'two', 2.5, 3)], const [])),
          ['one', 'no word times', 'two']);
    });
  });

  group('A: no draft where the phone\'s recogniser cannot do the language', () {
    test('multi-language and languages outside the list get no draft on an iPhone', () {
      for (final language in ['multi', '', 'ru', 'ru-RU', 'uk', 'pl', 'hi']) {
        expect(OwnDraftLanguage.allowed(language, LivePreviewPlatform.ios), isFalse, reason: language);
      }
      for (final language in ['en', 'en-US', 'EN_gb', 'de', 'es', 'fr', 'it', 'ja', 'ko', 'pt-BR', 'zh', 'yue']) {
        expect(OwnDraftLanguage.allowed(language, LivePreviewPlatform.ios), isTrue, reason: language);
      }
    });

    test('elsewhere only multi-language is refused: one recogniser, one language', () {
      expect(OwnDraftLanguage.allowed('multi', LivePreviewPlatform.android), isFalse);
      expect(OwnDraftLanguage.allowed('ru', LivePreviewPlatform.android), isTrue);
    });
  });

  group('inside the controller', () {
    late FakeLivePreviewEngine engine;
    late LivePreviewController preview;
    late List<(String, Map<String, Object?>)> logged;
    var clock = t0;
    var cascade = true;

    LivePreviewController build({LivePreviewPlatform platform = LivePreviewPlatform.ios}) => LivePreviewController(
          engine: engine,
          telemetry: LivePreviewTelemetry(emit: (_) {}),
          platform: platform,
          osMajor: 26,
          now: () => clock,
          decodeOpus: (opus) => Int16List.fromList(List.filled(opus.length * 4, opus.first)),
          ownResultsMuted: () => false,
          retimeOwnResults: () => false,
          cascade: () => cascade,
          liveWordsLog: (event, fields) => logged.add((event, fields)),
        );

    /// One result of the phone's recogniser with a span per word.
    void own(String id, String text, double start, double end, {bool isFinal = true}) {
      final l = line(id, text, start, end);
      engine.emit(id, text, isFinal, startedAt: l.startedAt, endedAt: l.endedAt, spans: l.spans);
    }

    Future<void> startIn(String language) async {
      preview.setFrontCapture(true, language: language);
      await pumpEventQueue();
    }

    setUp(() {
      engine = FakeLivePreviewEngine();
      logged = [];
      clock = t0;
      cascade = true;
      preview = build();
    });
    tearDown(() {
      preview.dispose();
      ReliabilityExperiments.overrideForTesting(null);
    });

    test('the switch needs both experiments, and is off by default', () {
      expect(LivePreviewController.cascadeEnabled(), isFalse);
      ReliabilityExperiments.overrideForTesting({'live_words_cascade'});
      expect(LivePreviewController.cascadeEnabled(), isFalse);
      ReliabilityExperiments.overrideForTesting({'vendor_recognizer_on_opened_app'});
      expect(LivePreviewController.cascadeEnabled(), isFalse);
      ReliabilityExperiments.overrideForTesting({'live_words_cascade', 'vendor_recognizer_on_opened_app'});
      expect(LivePreviewController.cascadeEnabled(), isTrue);
    });

    test('the draft shows at once and the vendor\'s words take its place when they arrive', () async {
      await startIn('en');
      own('a1', 'i scream for the bored', 0, 4.4, isFinal: false);
      clock = at(5);
      expect(textsOf(preview.lines), ['i scream for the bored']);
      preview.onVendorLines([line('v1', 'Ice cream for the board', 0, 4.4)]);
      expect(textsOf(preview.lines), ['Ice cream for the board']);
      expect(preview.vendorReplacedWords, 5);
      // The next words are again the draft until the vendor answers them.
      own('a2', 'next thing', 9, 10, isFinal: false);
      expect(textsOf(preview.lines), ['Ice cream for the board', 'next thing']);
      // A longer version of the same vendor line counts only the words it newly covers.
      preview.onVendorLines([line('v2', 'Next thing', 9, 10)]);
      expect(preview.vendorReplacedWords, 7);
      preview.onVendorLines([line('v2', 'Next thing', 9, 10)]);
      expect(preview.vendorReplacedWords, 7);
    });

    test('off, the same words keep today\'s order and none of the new counters move', () async {
      cascade = false;
      await startIn('en');
      own('a1', 'i scream for the bored', 0, 4.4);
      clock = at(5);
      preview.onVendorLines([line('v1', 'Ice cream for the board', 0, 4.4)]);
      expect(textsOf(preview.lines), ['i scream for the bored']);
      preview.noteAudioSent(at(0), 5000);
      clock = at(60);
      preview.settleCascadeCounters();
      expect([preview.vendorReplacedWords, preview.ownOnlyWords, preview.neitherMs], [0, 0, 0]);
    });

    test('for a multi-language account the phone\'s recogniser is not started; the vendor\'s words show', () async {
      await startIn('multi');
      expect(engine.startedLanguages, isEmpty);
      expect(preview.phase, LivePreviewPhase.unavailable);
      expect(preview.selected?.reason, LivePreviewReason.localeUnsupported);
      clock = at(3);
      preview.onVendorLines([line('v1', 'Только вендор', 0, 2)]);
      expect(textsOf(preview.lines), ['Только вендор']);
      // No recogniser, so nothing for the watchdog to restart.
      clock = at(60);
      preview.onVendorLines([line('v2', 'ещё много слов подряд здесь', 40, 45)]);
      expect(preview.watchdogRestarts, 0);
    });

    test('the same account without the experiment starts the recogniser as before', () async {
      cascade = false;
      await startIn('multi');
      expect(engine.startedLanguages, ['multi']);
      expect(preview.phase, LivePreviewPhase.streaming);
    });

    test('the stalled-recogniser watchdog still works with the vendor first', () async {
      await startIn('en');
      own('a1', 'it worked once', 0, 1);
      clock = at(5);
      preview.onVendorLines([line('v1', 'four words nobody answered', 20, 24)]);
      expect(preview.watchdogRestarts, 0);
      clock = at(31);
      preview.onVendorLines([line('v1', 'four words nobody answered at all', 20, 26)]);
      expect(preview.watchdogRestarts, 1);
      expect(logged.map((entry) => entry.$1), contains('own_recogniser_restart'));
    });

    test('counters: words only the phone\'s recogniser had, and seconds with neither', () async {
      await startIn('en');
      // 30 s of audio went to the vendor.
      preview.noteAudioSent(at(0), 10000);
      preview.noteAudioSent(at(10), 10000);
      preview.noteAudioSent(at(20), 10000);
      own('a1', 'both heard this', 0, 3);
      own('a2', 'only the phone', 12, 15);
      clock = at(4);
      preview.onVendorLines([line('v1', 'Both heard this', 0, 3)]);
      expect(preview.vendorReplacedWords, 3);
      // Nothing is counted before the audio is old enough for the vendor to have answered.
      clock = at(19);
      preview.settleCascadeCounters();
      expect(preview.ownOnlyWords, 0);
      clock = at(51);
      preview.settleCascadeCounters();
      expect(preview.ownOnlyWords, 3);
      // 30 s sent; words (with 1 s either side) cover 0..4 and 11..16 of it.
      expect(preview.neitherMs, closeTo(30000 - 4000 - 5000, 60));
      // Counted once.
      clock = at(90);
      preview.settleCascadeCounters();
      expect(preview.ownOnlyWords, 3);
    });

    group('grey words stay until stored text replaces them', () {
      test('a silence as long as a conversation restarts the current stretch and keeps the earlier words', () async {
        await startIn('en');
        clock = at(6); // A result arrives after the words it carries were spoken.
        own('a1', 'words before the long silence', 0, 5);
        expect(textsOf(preview.lines), ['words before the long silence']);
        final generation = preview.sessionGeneration;
        // More than the conversation timeout (2 minutes by default) with nothing heard.
        clock = at(200);
        own('a2', 'a new stretch', 198, 200);
        // Home's Listening row and the Listening page start again, as they always did.
        expect(textsOf(preview.lines), ['a new stretch']);
        expect(preview.sessionGeneration, generation + 1);
        // The earlier words are still there for the conversation they belong to.
        expect(textsOf(preview.wordsFor(startedAt: at(0))), ['words before the long silence', 'a new stretch']);
        expect(textsOf(preview.wordsFor(startedAt: at(0), until: at(30))), ['words before the long silence']);
      });

      test('off, the same silence wipes the list as before', () async {
        cascade = false;
        await startIn('en');
        clock = at(6);
        own('a1', 'words before the long silence', 0, 5);
        clock = at(200);
        own('a2', 'a new stretch', 198, 200);
        expect(textsOf(preview.lines), ['a new stretch']);
        expect(textsOf(preview.wordsFor(startedAt: at(0))), ['a new stretch']);
      });

      test('a conversation owns the words of its own time range, ended or open', () async {
        await startIn('en');
        own('a1', 'first conversation ends here', 0, 4);
        preview.cutAtEnd(at(5));
        own('a2', 'second one keeps going', 6, 10);
        preview.cutAtEnd(at(11));
        own('a3', 'third is open', 12, 15);
        // First: ended at the first End. Second: between the two Ends, although it began within the lead
        // of the first End. Third: after the second End, open.
        expect(textsOf(preview.wordsFor(startedAt: at(0), until: at(5))), ['first conversation ends here']);
        expect(textsOf(preview.wordsFor(startedAt: at(6.5))), ['second one keeps going']);
        expect(textsOf(preview.wordsFor(startedAt: at(6.5), until: at(11))), ['second one keeps going']);
        expect(textsOf(preview.wordsFor(startedAt: at(12.3))), ['third is open']);
        // An End the page has not heard of yet still bounds a conversation that began before it.
        expect(textsOf(preview.wordsFor(startedAt: at(0))), ['first conversation ends here']);
      });
    });

    group('B: an End cuts the live words', () {
      test('every screen\'s list holds only words spoken after the End, split per word', () async {
        await startIn('en');
        own('a1', 'before the end and after it', 0, 6);
        clock = at(7);
        preview.onVendorLines([line('v1', 'Vendor words also before then after', 8, 14)]);
        var notified = 0;
        preview.addListener(() => notified++);
        // The End falls inside the vendor's line, between "before" (11 s) and "then" (12 s).
        preview.cutAtEnd(at(11.5));
        expect(notified, 1);
        expect(preview.cutAt, at(11.5));
        expect(textsOf(preview.lines), ['then after']);
        expect(preview.lines.single.id, 'v1');
        expect(preview.lines.single.startedAt, at(12));
        expect(preview.latestLine, 'then after');
        // Words keep arriving: only those after the cut show, whichever recogniser has them.
        own('a2', 'draft of the next conversation', 20, 24, isFinal: false);
        expect(textsOf(preview.lines), ['then after', 'draft of the next conversation']);
      });

      test('the three screens read that list: Home\'s row, the Listening page, the open conversation', () async {
        await startIn('en');
        own('a1', 'old conversation words here', 0, 4);
        own('a2', 'straddling the end instant now', 8, 13);
        preview.cutAtEnd(at(10));
        // Home's Listening row and the Listening page: the list less what stored text covers. On the
        // phone-file route the listening connection has no stored lines, so nothing is covered.
        final shown = LivePreviewCoverage.forFinals(const [], null).excludeCovered(preview.lines);
        expect(textsOf(shown), ['end instant now']);
        // Home brings the Listening row back on words spoken after the End: only those are left.
        expect(SpeechAfterEnd.firstHeard(preview.lines, at(10)), at(10));
        // The open conversation's grey lines: the new conversation's first stored line starts a moment
        // after its first live word, and that word still belongs to it; nothing from before the End does.
        expect(textsOf(preview.wordsFor(startedAt: at(10.4))), ['end instant now']);
        // The conversation that End closed keeps its own words, up to the End, for its page.
        expect(textsOf(preview.wordsFor(startedAt: at(0))), ['old conversation words here', 'straddling the']);
        expect(textsOf(preview.wordsFor(startedAt: at(0), until: at(10))),
            ['old conversation words here', 'straddling the']);
      });

      test('words before the cut stay available for the End request, from the previous End on', () async {
        await startIn('en');
        own('a1', 'first conversation', 0, 2);
        expect(textsOf(preview.wordsUntil(at(3))), ['first conversation']);
        preview.cutAtEnd(at(3));
        own('a2', 'second conversation talk', 5, 8);
        clock = at(9);
        preview.onVendorLines([line('v1', 'Second conversation', 5, 7)]);
        own('a3', 'and the third', 12, 14);
        // The second End: its conversation's words only, by the cascade's priority, cut per word.
        expect(textsOf(preview.wordsUntil(at(12.5))), ['Second conversation', 'and']);
        preview.cutAtEnd(at(12.5));
        expect(textsOf(preview.lines), ['the third']);
        // An earlier instant never moves the cut back.
        preview.cutAtEnd(at(1));
        expect(preview.cutAt, at(12.5));
      });

      test('a cut with no words left shows an empty list, and the capture ending clears the cut', () async {
        await startIn('en');
        own('a1', 'everything before', 0, 2);
        preview.cutAtEnd(at(5));
        expect(preview.lines, isEmpty);
        expect(preview.latestLine, isNull);
        preview.endCapture();
        expect(preview.cutAt, isNull);
      });

      test('off, without a cut the list is untouched, and the same object as before', () async {
        cascade = false;
        await startIn('en');
        final before = preview.lines;
        own('a1', 'hello there', 0, 1);
        own('a2', 'second phrase', 1.2, 2);
        expect(identical(preview.lines, before), isTrue);
        // One line per phrase of the phone's recogniser, as always.
        expect(textsOf(preview.lines), ['hello there', 'second phrase']);
      });
    });
  });

  group('B: cutting lines per word', () {
    test('a word belongs to the side its start falls on', () {
      final lines = [line('l1', 'a b c d', 0, 4), line('l2', 'e f', 6, 8)];
      expect(textsOf(LiveWordsCut.after(lines, at(2))), ['c d', 'e f']);
      expect(textsOf(LiveWordsCut.within(lines, before: at(2))), ['a b']);
      expect(textsOf(LiveWordsCut.within(lines, from: at(1), before: at(7))), ['b c d', 'e']);
      // Nothing cut away: the same list, no copy.
      expect(identical(LiveWordsCut.after(lines, at(0)), lines), isTrue);
      expect(LiveWordsCut.after(lines, at(100)), isEmpty);
    });

    test('a line without word times goes whole, by its start', () {
      final plain = LivePreviewLine(id: 'p', text: 'no word times', isFinal: true, startedAt: at(5), endedAt: at(9));
      expect(LiveWordsCut.after([plain], at(6)), isEmpty);
      expect(LiveWordsCut.after([plain], at(5)), [plain]);
    });
  });

  group('C: the End request\'s tail', () {
    test('words with their times in seconds since the epoch, in order', () {
      final tail =
          LiveTail.payload([line('v1', 'we ship on Friday', 50, 52), line('a1', 'agreed', 55, 55.5)], endedAt: at(60))!;
      expect(tail['v'], 1);
      expect(tail['ended_at'], at(60).millisecondsSinceEpoch / 1000);
      final lines = tail['lines'] as List;
      expect(lines, hasLength(2));
      expect([for (final entry in lines[0] as List) (entry as List)[0]], ['we', 'ship', 'on', 'Friday']);
      expect((lines[0] as List).first,
          ['we', at(50).millisecondsSinceEpoch / 1000, at(50.45).millisecondsSinceEpoch / 1000]);
      expect(LiveTail.wordCount(tail), 5);
      // It is what the request sends: plain JSON.
      expect(jsonDecode(jsonEncode(tail)), isA<Map<String, dynamic>>());
    });

    test('no words, no field', () {
      expect(LiveTail.payload(const [], endedAt: at(1)), isNull);
      expect(LiveTail.payload([line('v1', ' ', 0, 1)], endedAt: at(1)), isNull);
      expect(LiveTail.wordCount(null), 0);
    });

    test('bounded: the newest words are kept', () {
      final many = [
        for (var i = 0; i < 100; i++)
          line('l$i', List.generate(10, (w) => 'w${i}x$w').join(' '), i * 10.0, i * 10.0 + 9),
      ];
      final tail = LiveTail.payload(many, endedAt: at(2000))!;
      expect(LiveTail.wordCount(tail), LiveTail.maxWords);
      final lines = tail['lines'] as List;
      expect(((lines.last as List).last as List)[0], 'w99x9');
      expect(((lines.first as List).first as List)[0], 'w40x0');
      final long = [for (var i = 0; i < 400; i++) line('l$i', 'x' * 40, i.toDouble(), i + 0.5)];
      final chars = [
        for (final l in LiveTail.payload(long, endedAt: at(500))!['lines'] as List)
          for (final entry in l as List) ((entry as List)[0] as String).length,
      ].fold(0, (sum, length) => sum + length);
      expect(chars, lessThanOrEqualTo(LiveTail.maxChars));
    });

    test('plain text only', () {
      final odd = LivePreviewLine(id: 'o', text: 'x', isFinal: true, startedAt: at(0), endedAt: at(1), spans: [
        LivePreviewSpan(text: 'tab\tnew\nline\u0000', startedAt: at(0), endedAt: at(1)),
        LivePreviewSpan(text: 'y' * 200, startedAt: at(1), endedAt: at(2)),
      ]);
      final entries = (LiveTail.payload([odd], endedAt: at(3))!['lines'] as List).single as List;
      expect((entries[0] as List)[0], 'tab new line');
      expect(((entries[1] as List)[0] as String).length, LiveTail.maxWordChars);
    });

    test('the End request carries the tail only when there is one', () async {
      Env.init(_TestEnv());
      final bodies = <Object?>[];
      Future<http.Response?> send(dynamic request) async {
        bodies.add(jsonDecode(request.body as String));
        return http.Response('{}', 404);
      }

      final tail = LiveTail.payload([line('v1', 'last words', 1, 2)], endedAt: at(3));
      await processInProgressConversationOutcome(
          liveConversationId: 'live-1', endedAt: at(3), liveTail: tail, sendRequest: send);
      await processInProgressConversationOutcome(liveConversationId: 'live-1', endedAt: at(3), sendRequest: send);
      expect(bodies[0], {'live_conversation_id': 'live-1', 'live_tail': jsonDecode(jsonEncode(tail))});
      expect(bodies[1], {'live_conversation_id': 'live-1'});
    });
  });

  group('the End, through the coordinator and the display connection', () {
    late FakeCapture capture;
    late FakeLivePreviewEngine engine;
    late LivePreviewController preview;
    late VendorLiveWords vendor;
    late List<FakeSocket> sockets;
    late List<(String, Map<String, Object?>)> logged;
    late LiveWordsCoordinator coordinator;
    var cascade = true;
    var failEndRecord = false;
    var clock = t0;

    void speak(int frames) {
      for (var i = 0; i < frames; i++) {
        clock = clock.add(const Duration(milliseconds: 20));
        vendor.onPendantPacket(pendantPacket(i % 256), BleAudioCodec.opusFS320);
      }
    }

    List<Object?> texts(FakeSocket socket) => [
          for (final message in socket.sent)
            if (message is String) jsonDecode(message),
        ];

    setUp(() {
      cascade = true;
      clock = t0;
      capture = FakeCapture();
      engine = FakeLivePreviewEngine();
      sockets = [];
      logged = [];
      preview = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        now: () => clock,
        ownResultsMuted: () => false,
        retimeOwnResults: () => false,
        cascade: () => cascade,
      );
      vendor = VendorLiveWords(
        onLines: preview.onVendorLines,
        onAudioSent: preview.noteAudioSent,
        connect: (url) {
          final socket = FakeSocket(url);
          sockets.add(socket);
          return socket;
        },
        now: () => clock,
        baseUrl: () => 'ws://server/',
        uid: () => 'owner',
      );
      coordinator = LiveWordsCoordinator(
        capture: capture,
        preview: preview,
        vendor: vendor,
        enabled: () => true,
        cascade: () => cascade,
        language: () => 'en',
        lifecycleState: () => AppLifecycleState.resumed,
        log: (event, fields) {
          if (failEndRecord && event == 'end_cut') throw StateError('record unavailable');
          logged.add((event, fields));
        },
      )..start();
    });
    tearDown(() {
      failEndRecord = false;
      coordinator.dispose();
      preview.dispose();
    });

    test('an End returns the tail, cuts the list and tells the server between two frames', () async {
      capture.set(state: RecordingState.deviceRecord);
      await pumpEventQueue();
      speak(50);
      await pumpEventQueue();
      final socket = sockets.single;
      final before = socket.sent.length;
      engine.emit('a1', 'said before the end', true,
          startedAt: t0, endedAt: clock, spans: line('a1', 'said before the end', 0, 1).spans);
      final endedAt = clock;
      final tail = coordinator.onEnd(endedAt);
      expect(LiveTail.wordCount(tail), 4);
      expect(preview.cutAt, endedAt);
      expect(preview.lines, isEmpty);
      // The message sits in the audio's own order: after every frame captured before the End.
      expect(socket.sent.length, before + 1);
      expect(texts(socket), [
        {'type': 'end'}
      ]);
      speak(5);
      expect(socket.sent.last, isA<Uint8List>());
      expect(socket.sent[before], isA<String>());
      // The local record holds counts, never a word.
      final entry = logged.lastWhere((entry) => entry.$1 == 'end_cut').$2;
      expect(entry, {'tail_words': 4, 'tail_lines': 1, 'vendor_connected': true});
    });

    test('a fault in the live-words layer never stops the End: it goes without a tail', () async {
      capture.set(state: RecordingState.deviceRecord);
      await pumpEventQueue();
      speak(50);
      await pumpEventQueue();
      failEndRecord = true;
      expect(coordinator.onEnd(clock), isNull);
      expect(logged.map((entry) => entry.$1), contains('end_cut_failed'));
    });

    test('off, an End returns nothing, cuts nothing and sends nothing', () async {
      cascade = false;
      capture.set(state: RecordingState.deviceRecord);
      await pumpEventQueue();
      speak(50);
      await pumpEventQueue();
      engine.emit('a1', 'said before the end', true, startedAt: t0, endedAt: clock);
      expect(coordinator.onEnd(clock), isNull);
      expect(preview.cutAt, isNull);
      expect(textsOf(preview.lines), ['said before the end']);
      expect(texts(sockets.single), isEmpty);
      expect(logged.map((entry) => entry.$1), isNot(contains('end_cut')));
    });

    test('an End while no connection is open is told to the next one, where it falls in the lead-in', () async {
      // Capture is active but the app is not in front: audio is kept for the lead-in, nothing dials.
      vendor.setState(capturing: true, inFront: false, language: 'en');
      speak(100); // 2 s kept
      final endedAt = clock;
      vendor.markEnd(endedAt);
      speak(50); // 1 s after the End
      expect(sockets, isEmpty);
      vendor.setState(capturing: true, inFront: true, language: 'en');
      speak(1);
      await pumpEventQueue();
      final sent = sockets.single.sent;
      final index = sent.indexWhere((message) => message is String);
      expect(jsonDecode(sent[index] as String), {'type': 'end'});
      // The 3 s lead-in is the newest 150 frames: 99 from before the End, then the message, then the rest.
      expect(index, 99);
      expect(sent.whereType<String>(), hasLength(1));
      expect(vendor.endsSentForTesting, 1);
    });

    test('the counters report says what the cascade did instead of "filled"', () async {
      capture.set(state: RecordingState.deviceRecord);
      await pumpEventQueue();
      speak(50);
      capture.set(state: RecordingState.stop);
      final report = logged.lastWhere((entry) => entry.$1 == 'counters').$2;
      expect(report.keys, containsAll(['cascade', 'own_draft', 'replaced_words', 'own_only_words', 'neither_s']));
      expect(report.keys, isNot(contains('filled_words')));
      cascade = false;
      capture.set(state: RecordingState.deviceRecord);
      capture.set(state: RecordingState.stop);
      final baseline = logged.lastWhere((entry) => entry.$1 == 'counters').$2;
      expect(baseline.keys, containsAll(['filled_words', 'filled_speech_ms']));
      expect(baseline.keys, isNot(contains('replaced_words')));
    });
  });

  group('stored text, else live words, with a five-minute limit', () {
    final now = at(600);
    TranscriptSegment stored(String text, double start, double end) => TranscriptSegment(
        id: 's$start',
        text: text,
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: start,
        end: end,
        translations: []);
    LivePreviewCoverage coverage(List<TranscriptSegment> finals, {bool cascade = true}) =>
        LivePreviewCoverage.forFinals(finals, t0, cascade: cascade, now: () => now);

    test('a word leaves when a stored line covers its moment of audio, not before', () {
      final lines = [line('l1', 'one two three four', 500, 504), line('l2', 'five six seven eight', 520, 524)];
      // Stored text has reached 502 s: the words inside it (and within 2 s of it) are replaced.
      expect(textsOf(coverage([stored('One two.', 499.5, 501.0)]).excludeCovered(lines)),
          ['four', 'five six seven eight']);
      // The stored line for the later words arrives: they go too.
      expect(
          coverage([stored('One two three four.', 499.5, 504.2), stored('Five six seven eight.', 519.8, 524.1)])
              .excludeCovered(lines),
          isEmpty);
    });

    test('words in a hole of the stored text stay, where the old rule dropped them at once', () {
      final lines = [line('l1', 'missed by the transcript', 400, 403), line('l2', 'newest words', 590, 592)];
      final finals = [stored('Before.', 380, 385), stored('Much later.', 560, 565)];
      // Cascade: nothing stored within 2 s of 400-403 s, and the words are 3 minutes old: they stay.
      expect(textsOf(coverage(finals).excludeCovered(lines)), ['missed by the transcript', 'newest words']);
      // Baseline: everything older than the last stored line minus 10 s is dropped, covered or not.
      expect(textsOf(coverage(finals, cascade: false).excludeCovered(lines)), ['newest words']);
    });

    test('a word nothing replaced within five minutes is dropped', () {
      final lines = [line('l1', 'too old now', 290, 293), line('l2', 'still waiting', 310, 313)];
      final finals = [stored('Something else.', 100, 105)];
      // now = 600 s: the first line is over five minutes old, the second is not.
      expect(textsOf(coverage(finals).excludeCovered(lines)), ['still waiting']);
    });

    test('with no stored text at all there is nothing to wait for and nothing is dropped', () {
      final lines = [line('l1', 'very old words', 10, 13), line('l2', 'new words', 590, 592)];
      expect(textsOf(coverage(const []).excludeCovered(lines)), ['very old words', 'new words']);
      // No origin (the listening connection has no start yet): untouched, as before.
      expect(LivePreviewCoverage.forFinals(const [], null, cascade: true).excludeCovered(lines), hasLength(2));
    });

    test('a line without word times is judged whole, by its own times', () {
      LivePreviewLine plain(String id, double start, double end) => LivePreviewLine(
          id: id, text: 'plain $id', isFinal: true, startedAt: at(start), endedAt: at(end), firstSeenAt: at(end));
      final finals = [stored('Covered.', 500, 504)];
      expect(
          textsOf(coverage(finals).excludeCovered([plain('a', 501, 503), plain('b', 520, 523), plain('c', 100, 103)])),
          ['plain b']);
    });

    test('off by default: the rule is today\'s', () {
      final lines = [line('l1', 'missed by the transcript', 400, 403)];
      final finals = [stored('Before.', 380, 385), stored('Much later.', 560, 565)];
      expect(LivePreviewCoverage.forFinals(finals, t0).excludeCovered(lines), isEmpty);
    });
  });
}
