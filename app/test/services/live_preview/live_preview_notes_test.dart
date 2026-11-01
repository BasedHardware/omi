import 'dart:async';

import 'package:characters/characters.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_notes.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';

import '../../support/live_preview_fakes.dart';

final _t0 = DateTime.utc(2026, 10, 22, 2, 18);

/// A scripted notes engine: records calls, can hang mid-run, can be unavailable.
class _ScriptedNotes {
  _ScriptedNotes([this.behavior]);

  final Future<List<String>?> Function(String text, String language)? behavior;

  final calls = <(String, String)>[];
  int inFlight = 0;
  Completer<List<String>?>? gate;

  Future<List<String>?> call(String text, String language) async {
    calls.add((text, language));
    inFlight++;
    if (gate != null) {
      final value = await gate!.future;
      inFlight--;
      return value;
    }
    inFlight--;
    return behavior?.call(text, language) ?? Future.value(const <String>['draft']);
  }
}

/// A preview controller with a running engine and the scripted notes engine,
/// a controllable clock, and the word emitter the recognizer results drive.
class _Harness {
  _Harness(this.notes) {
    controller = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
      notesEngine: notes.call,
      now: () => _clock,
    );
    controller.admit(language: 'en');
  }

  final _ScriptedNotes notes;
  final engine = FakeLivePreviewEngine();
  late final LivePreviewController controller;
  var _clock = _t0;
  var _segment = 0;

  /// Waits for the engine start the admission kicks off, so results are heard.
  Future<void> ready() => Future<void>.delayed(Duration.zero);

  void advance(Duration by) => _clock = _clock.add(by);

  void emit(int words) {
    engine.emit('a${_segment++}', List.generate(words, (i) => 'w$i').join(' '), true);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LivePreviewNotesPolicy', () {
    test('clamps to four bullets of twelve words', () {
      final clamped = LivePreviewNotesPolicy.clamp([
        for (var i = 0; i < 6; i++) List.generate(20, (w) => 'w$i-$w').join(' '),
        '   ',
      ]);
      expect(clamped, hasLength(4));
      for (final bullet in clamped) {
        expect(bullet.split(' '), hasLength(12));
      }
    });

    for (final unit in ['漢字', 'かな', 'カナ', '한글', 'ภาษา', 'ที่นี่', '𠀀𠀁']) {
      test('unspaced $unit shares the throttle, prompt and bullet budget', () {
        final long = List.filled(1601, unit).join();
        final units = LivePreviewNotesPolicy.wordCount(long);
        expect(units, greaterThanOrEqualTo(1601));
        final bullet = LivePreviewNotesPolicy.clamp([long]).single;
        expect(LivePreviewNotesPolicy.wordCount(bullet), 12);
        expect(long, startsWith(bullet));
        expect(bullet.characters.length, 24);
        final input = LivePreviewNotesPolicy.inputText([
          LivePreviewLine(id: 'a', text: long, isFinal: true),
        ]);
        expect(LivePreviewNotesPolicy.wordCount(input), 1500);
        expect(long, endsWith(input));
        expect(input.characters.length, 3000);
      });
    }

    test('mixed scripts cannot hide an unspaced run in a whitespace word', () {
      expect(LivePreviewNotesPolicy.wordCount('hello漢字かなworld ภาษา'), 6);
      final bullet = LivePreviewNotesPolicy.clamp(['hello${List.filled(30, '漢字').join()}world']).single;
      expect(LivePreviewNotesPolicy.wordCount(bullet), 12);
      expect(bullet, 'hello${List.filled(11, '漢字').join()}');
    });

    test('the input is the newest 1500 words', () {
      final lines = [
        for (var i = 0; i < 40; i++)
          LivePreviewLine(id: 'l$i', text: List.generate(50, (w) => 'l${i}w$w').join(' '), isFinal: true),
      ];
      final text = LivePreviewNotesPolicy.inputText(lines);
      expect(text.split(' '), hasLength(LivePreviewNotesPolicy.maxInputWords));
      expect(text, contains('l39w49'), reason: 'the newest words are kept');
      expect(text, isNot(contains('l0w0')), reason: 'the oldest words are dropped');
    });
  });

  group('LivePreviewNotes', () {
    test('drafts after 40 new words, then again only after 60s and 40 more words', () async {
      final notes = _ScriptedNotes();
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();

      harness.emit(39);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, isEmpty, reason: 'under 40 new words, no run');

      harness.emit(5);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, hasLength(1));
      expect(harness.controller.notes.bullets, ['draft']);

      // A few new words inside the 60s window: nothing yet.
      harness.advance(const Duration(seconds: 30));
      harness.emit(3);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, hasLength(1));

      // Past the window but still fewer than 40 new words: still nothing…
      harness.advance(const Duration(seconds: 31));
      harness.emit(2);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, hasLength(1));

      // …until 40 more words arrive after the window.
      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, hasLength(2));
    });

    for (final unit in ['漢字', 'かな', '한글', 'ที่นี่']) {
      test('one unspaced $unit segment reaches 40-word admission and refreshes', () async {
        final notes = _ScriptedNotes((text, language) async => [List.filled(40, unit).join()]);
        final harness = _Harness(notes);
        addTearDown(harness.controller.dispose);
        await harness.ready();
        harness.engine.emit('one', List.filled(39, unit).join(), false);
        await harness.ready();
        expect(notes.calls, isEmpty);
        // Growing the same segment adds only its new words.
        harness.engine.emit('one', List.filled(40, unit).join(), true);
        await harness.ready();
        expect(harness.controller.totalWordsSeen, 40);
        expect(notes.calls, hasLength(1));
        expect(harness.controller.notes.bullets.single.characters.length, 24);
        harness.advance(const Duration(seconds: 61));
        harness.engine.emit('two', List.filled(40, unit).join(), true);
        await harness.ready();
        expect(harness.controller.totalWordsSeen, 80);
        expect(notes.calls, hasLength(2));
      });
    }

    test('volatile revisions cannot count the same growing words repeatedly', () async {
      final notes = _ScriptedNotes();
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();
      for (var i = 0; i < 50; i++) {
        harness.engine.emit('volatile', 'one two three', false);
        harness.engine.emit('volatile', 'one', false);
      }
      await harness.ready();
      expect(harness.controller.totalWordsSeen, 3);
      expect(notes.calls, isEmpty);
      harness.engine.emit('volatile', List.generate(40, (i) => 'w$i').join(' '), true);
      await harness.ready();
      expect(harness.controller.totalWordsSeen, 40);
      expect(notes.calls, hasLength(1));
    });

    test('continues drafting past 1500 words and after bounded lines evict', () async {
      final notes = _ScriptedNotes();
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();
      harness.emit(1500);
      await harness.ready();
      harness.advance(const Duration(seconds: 61));
      harness.emit(40);
      await harness.ready();
      expect(notes.calls, hasLength(2));
      expect(notes.calls.last.$1.split(' '), hasLength(1500));
      for (var i = 0; i < 205; i++) {
        harness.emit(1);
      }
      harness.advance(const Duration(seconds: 61));
      harness.emit(40);
      await harness.ready();
      expect(harness.controller.lines, hasLength(200));
      expect(notes.calls, hasLength(3));
    });

    for (final failure in [false, true]) {
      test('old session ${failure ? 'error' : 'result'} cannot render after account clear and refill', () async {
        final notes = _ScriptedNotes()..gate = Completer<List<String>?>();
        final harness = _Harness(notes);
        addTearDown(harness.controller.dispose);
        await harness.ready();
        harness.emit(40);
        harness.controller.endCapture(); // account replacement uses this same boundary
        harness.controller.admit(language: 'en');
        await harness.ready();
        harness.emit(40);
        if (failure) {
          notes.gate!.completeError(StateError('old failure'));
        } else {
          notes.gate!.complete(['old private notes']);
        }
        await harness.ready();
        expect(harness.controller.notes.bullets, isEmpty);
        notes.gate = null;
        harness.advance(const Duration(seconds: 61));
        harness.emit(40);
        await harness.ready();
        expect(harness.controller.notes.bullets, ['draft']);
      });
    }

    test('silence clear and refill resets notes and fences a late draft', () async {
      final notes = _ScriptedNotes()..gate = Completer<List<String>?>();
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();
      harness.emit(40);
      final generation = harness.controller.sessionGeneration;
      harness.advance(const Duration(minutes: 3));
      harness.emit(1); // clear and refill happen in a single notification
      expect(harness.controller.sessionGeneration, greaterThan(generation));
      expect(harness.controller.totalWordsSeen, 1);
      notes.gate!.complete(['old']);
      await harness.ready();
      expect(harness.controller.notes.bullets, isEmpty);
      notes.gate = null;
      harness.emit(39);
      await harness.ready();
      expect(harness.controller.notes.bullets, ['draft']);
    });

    test('the input is capped to the newest words and carries the language', () async {
      final notes = _ScriptedNotes((text, language) async {
        expect(language, 'en');
        expect(text.split(' ').length, lessThanOrEqualTo(LivePreviewNotesPolicy.maxInputWords));
        return ['short'];
      });
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();
      harness.emit(2000);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, hasLength(1));
      expect(harness.controller.notes.bullets, ['short']);
    });

    test('clears with the preview lines and counts the next capture from zero', () async {
      final notes = _ScriptedNotes();
      final harness = _Harness(notes);
      final controller = harness.controller;
      addTearDown(controller.dispose);
      await harness.ready();

      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(controller.notes.bullets, ['draft']);

      controller.endCapture();
      expect(controller.notes.bullets, isEmpty, reason: 'capture stop clears the notes');
      expect(controller.lines, isEmpty);

      // A second capture starts fresh: the word counter begins at zero again.
      controller.admit(language: 'en');
      harness.emit(20);
      await Future<void>.delayed(Duration.zero);
      expect(notes.calls, hasLength(1), reason: 'no run until 40 new words of the new capture');
    });

    test('drops the run while the previous draft is still going', () async {
      final notes = _ScriptedNotes();
      notes.gate = Completer<List<String>?>();
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();

      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(notes.inFlight, 1);

      harness.advance(const Duration(seconds: 61));
      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(notes.inFlight, 1, reason: 'the busy run is dropped, not queued');

      notes.gate!.complete(['late']);
      await Future<void>.delayed(Duration.zero);
      expect(harness.controller.notes.bullets, ['late']);
    });

    test('an unavailable engine drafts nothing; a later available one does', () async {
      var unavailable = true;
      final notes = _ScriptedNotes((text, language) async => unavailable ? null : ['ok']);
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();

      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(harness.controller.notes.bullets, isEmpty);

      unavailable = false;
      harness.advance(const Duration(seconds: 61));
      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(harness.controller.notes.bullets, ['ok']);
    });

    test('an error hides the bullets', () async {
      var fail = false;
      final notes = _ScriptedNotes((text, language) async {
        if (fail) throw StateError('engine exploded');
        return ['first'];
      });
      final harness = _Harness(notes);
      addTearDown(harness.controller.dispose);
      await harness.ready();

      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(harness.controller.notes.bullets, ['first']);

      fail = true;
      harness.advance(const Duration(seconds: 61));
      harness.emit(40);
      await Future<void>.delayed(Duration.zero);
      expect(harness.controller.notes.bullets, isEmpty, reason: 'the quiet line, no cloud fallback');
    });

    test('telemetry reports the engine, outcome, latency and count, never text', () async {
      final events = <RegisteredNotesEvent>[];
      // ignore: avoid_unused_constructor_parameters
      final notes = _ScriptedNotes((text, language) async => ['a', 'b']);
      final engine = FakeLivePreviewEngine();
      final controller = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (event) {
          if (event.wireName == 'Live Preview Notes') {
            events.add(RegisteredNotesEvent(event.wireName, event.properties));
          }
        }),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        notesEngine: notes.call,
      );
      addTearDown(controller.dispose);
      controller.admit(language: 'en');
      await Future<void>.delayed(Duration.zero);
      engine.emit('a0', List.generate(40, (i) => 'w$i').join(' '), true);
      await Future<void>.delayed(Duration.zero);

      expect(events, hasLength(1));
      expect(events.single.properties['engine'], 'apple_foundation_models');
      expect(events.single.properties['outcome'], 'ok');
      expect(events.single.properties['bullet_count'], 2);
      expect(events.single.properties.containsKey('latency_ms'), isTrue);
      expect(events.single.properties.toString(), isNot(contains('w0')),
          reason: 'no preview text ever leaves the phone');
    });
  });

  group('methodChannelLivePreviewNotes contract', () {
    test('maps a successful reply to bullets', () async {
      const channel = MethodChannel('com.omi/live_preview_notes');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
        expect(call.method, 'summarize');
        expect((call.arguments as Map)['language'], 'en');
        return {
          'bullets': const ['one', 'two']
        };
      });
      addTearDown(() =>
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
      expect(await methodChannelLivePreviewNotes('text words here', 'en'), ['one', 'two']);
    });

    test('UNAVAILABLE maps to null, other errors rethrow', () async {
      const channel = MethodChannel('com.omi/live_preview_notes');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(code: 'UNAVAILABLE');
      });
      addTearDown(() =>
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
      expect(await methodChannelLivePreviewNotes('text', 'en'), isNull);

      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(code: 'NOTES_FAILED');
      });
      await expectLater(methodChannelLivePreviewNotes('text', 'en'), throwsA(isA<PlatformException>()));
    });
  });
}

class RegisteredNotesEvent {
  RegisteredNotesEvent(this.wireName, this.properties);

  final String wireName;
  final Map<String, Object> properties;
}
