import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/whisper_window_preview_engine.dart';

import '../../support/live_preview_fakes.dart';

void main() {
  group('Whisper windowed pseudo-stream', () {
    test('each full window is one settled line; one transcription at a time; WAV framed', () async {
      final windows = <Uint8List>[];
      final gate = <Completer<String?>>[];
      final engine = WhisperWindowPreviewEngine(
        windowBytes: 64,
        maxBufferedBytes: 256,
        transcribe: (wav, language) {
          windows.add(wav);
          final done = Completer<String?>();
          gate.add(done);
          return done.future;
        },
      );
      final results = <LivePreviewResult>[];
      engine.results.listen(results.add);
      final start = await engine.start('en');
      expect([start.engine, start.reason, start.bundledInstalled],
          [LivePreviewEngineKind.whisper, LivePreviewReason.ok, true]);
      expect(await engine.feedPcm16(Uint8List(40)), true);
      expect(windows, isEmpty);
      await engine.feedPcm16(Uint8List(40)); // 80 bytes: one window starts
      await engine.feedPcm16(Uint8List(100)); // busy: buffered
      expect(windows, hasLength(1));
      expect(windows.single.length, 44 + 64, reason: 'canonical WAV header + one window');
      gate.single.complete('  hello there ');
      await pumpEventQueue();
      expect(results.single.text, 'hello there');
      expect(results.single.isFinal, true);
      expect(windows, hasLength(2), reason: 'the next window starts when the previous finished');
      gate.last.complete(null);
      await pumpEventQueue();
      expect(results, hasLength(1), reason: 'silence emits nothing');
      await engine.stop();
    });

    test('the rolling buffer is bounded: overflow drops the oldest preview audio', () async {
      final never = Completer<String?>();
      final engine = WhisperWindowPreviewEngine(
          windowBytes: 64, maxBufferedBytes: 128, transcribe: (wav, language) => never.future);
      await engine.start('en');
      await engine.feedPcm16(Uint8List(64)); // starts a window (busy forever)
      expect(await engine.feedPcm16(Uint8List(100)), true);
      expect(await engine.feedPcm16(Uint8List(100)), false, reason: 'over the bound: reported as dropped');
      await engine.stop();
    });

    test('window audio times do not move to a late transcription result', () async {
      final clock = DateTime.utc(2026, 10, 27);
      final done = Completer<String?>();
      final engine =
          WhisperWindowPreviewEngine(windowBytes: 32000, now: () => clock, transcribe: (_, __) => done.future);
      final results = <LivePreviewResult>[];
      engine.results.listen(results.add);
      await engine.start('en');
      await engine.feedPcm16(Uint8List(32000));
      done.complete('words');
      await pumpEventQueue();
      expect(results.single.startedAt, clock.subtract(const Duration(seconds: 1)));
      expect(results.single.endedAt, clock);
      await engine.stop();
    });

    test('a model crash is a typed runtime failure; excluded after it', () async {
      final engine =
          WhisperWindowPreviewEngine(windowBytes: 8, transcribe: (wav, language) async => throw StateError('x'));
      final errors = <Object>[];
      engine.results.listen((_) {}, onError: errors.add);
      await engine.start('en');
      await engine.feedPcm16(Uint8List(8));
      await pumpEventQueue();
      expect((errors.single as LivePreviewRuntimeFailure).engine, LivePreviewEngineKind.whisper);
      final again = await engine.start('en', exclude: {LivePreviewEngineKind.whisper});
      expect(again.running, false);
    });
  });

  group('OS engine first, downloaded Whisper second, never cloud', () {
    test('the OS engine wins when it runs', () async {
      final native = FakeLivePreviewEngine()
        ..nextStart = const LivePreviewStart(LivePreviewEngineKind.androidOnDevice, LivePreviewReason.ok);
      var probed = false;
      final engine = FallbackLivePreviewEngine(
          primary: native,
          fallback: () async {
            probed = true;
            return null;
          });
      final start = await engine.start('en');
      expect(start.engine, LivePreviewEngineKind.androidOnDevice);
      expect(probed, false);
      final seen = <String>[];
      engine.results.listen((result) => seen.add(result.text));
      native.emit('g0', 'from the os', false);
      await pumpEventQueue();
      expect(seen, ['from the os']);
    });

    test('no OS engine: the downloaded model runs; failures are forwarded', () async {
      final native = FakeLivePreviewEngine()..nextStart = const LivePreviewStart.none(LivePreviewReason.osTooOld);
      final whisper = FakeLivePreviewEngine()
        ..nextStart =
            const LivePreviewStart(LivePreviewEngineKind.whisper, LivePreviewReason.ok, bundledInstalled: true);
      final engine = FallbackLivePreviewEngine(primary: native, fallback: () async => whisper);
      final start = await engine.start('en');
      expect(start.engine, LivePreviewEngineKind.whisper);
      expect(start.bundledInstalled, true);
      final errors = <Object>[];
      engine.results.listen((_) {}, onError: errors.add);
      expect(await engine.feedPcm16(Uint8List(4)), true);
      expect(whisper.fed, hasLength(1));
      expect(native.fed, isEmpty);
      whisper.fail(LivePreviewEngineKind.whisper);
      await pumpEventQueue();
      expect(errors.single, isA<LivePreviewRuntimeFailure>());
      await engine.stop();
      expect(whisper.stops, 1);
    });

    test('no OS engine and no model: none with the OS reason', () async {
      final native = FakeLivePreviewEngine()
        ..nextStart = const LivePreviewStart.none(LivePreviewReason.localeAssetMissing);
      final engine = FallbackLivePreviewEngine(primary: native, fallback: () async => null);
      final start = await engine.start('en');
      expect([start.engine, start.reason, start.bundledInstalled],
          [LivePreviewEngineKind.none, LivePreviewReason.localeAssetMissing, false]);
      expect(await engine.feedPcm16(Uint8List(4)), false);
    });

    test('exclusions reach both tiers: a failed model is not retried', () async {
      final native = FakeLivePreviewEngine()..nextStart = const LivePreviewStart.none(LivePreviewReason.engineError);
      var probed = false;
      final engine = FallbackLivePreviewEngine(
          primary: native,
          fallback: () async {
            probed = true;
            return FakeLivePreviewEngine();
          });
      final start =
          await engine.start('en', exclude: {LivePreviewEngineKind.androidOnDevice, LivePreviewEngineKind.whisper});
      expect(start.running, false);
      expect(native.startExclusions.single, {LivePreviewEngineKind.androidOnDevice, LivePreviewEngineKind.whisper});
      expect(probed, false);
    });
  });
}
