import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/experiments/live_preview_gate.dart';
import 'package:omi/services/live_preview/live_preview_composition.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

import '../../support/live_preview_fakes.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('admission parse', () {
    test('local_preview counts only with mobile_standard_batch; absent is today', () {
      MessageServiceStatusEvent parse(Map<String, dynamic> json) =>
          MessageEvent.fromJson({'type': 'service_status', ...json}) as MessageServiceStatusEvent;
      expect(parse({'status': 'ready'}).localPreview, false);
      expect(parse({'status': 'ready', 'mobile_standard_batch': true}).localPreview, false);
      expect(parse({'status': 'ready', 'local_preview': true}).localPreview, false);
      final admitted =
          parse({'status': 'mobile_batch_admission', 'mobile_standard_batch': true, 'local_preview': true});
      expect(admitted.localPreview, true);
      expect(admitted.mobileStandardBatch, true);
      expect(parse({'status': 'ready', 'mobile_standard_batch': true, 'local_preview': 'true'}).localPreview, false);
    });
  });

  group('kill switch', () {
    test('absent/false/error/slow keep the request on; true stops it', () async {
      expect(await LivePreviewGate.requestAllowed(readFlag: (_) async => false), true);
      expect(await LivePreviewGate.requestAllowed(readFlag: (_) async => true), false);
      expect(await LivePreviewGate.requestAllowed(readFlag: (_) async => throw StateError('offline')), true);
      final keys = <String>[];
      await LivePreviewGate.requestAllowed(readFlag: (key) async {
        keys.add(key);
        return false;
      });
      expect(keys, ['mobile-local-preview-disabled']);
    });
  });

  group('engine selection and reason codes', () {
    late FakeLivePreviewEngine engine;
    late List<RegisteredEvent> events;
    late LivePreviewController preview;
    var clock = DateTime.utc(2026, 10, 26);

    setUp(() {
      engine = FakeLivePreviewEngine();
      events = [];
      clock = DateTime.utc(2026, 10, 26);
      preview = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: events.add),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        now: () => clock,
        decodeOpus: (opus) => Int16List.fromList(List.filled(opus.length * 4, opus.first)),
        feedChunkBytes: 640,
      );
    });
    tearDown(() => preview.dispose());

    test('a running engine streams; telemetry is closed enums and ints only', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      preview.admit(language: 'en');
      expect(preview.phase, LivePreviewPhase.starting);
      await pumpEventQueue();
      expect(engine.startedLanguages, ['en']);
      expect(preview.phase, LivePreviewPhase.streaming);
      final selected = events.single as LivePreviewEngineSelected;
      expect(selected.properties, {
        'engine': 'speech_transcriber',
        'reason': 'ok',
        'platform': 'ios',
        'os_major': 26,
        'bundled_installed': false,
      });
    });

    for (final reason in LivePreviewReason.values.where((reason) => reason != LivePreviewReason.ok)) {
      test('no engine ($reason) is the calm unavailable state, never a cloud fallback', () async {
        engine.nextStart = LivePreviewStart.none(reason);
        preview.admit(language: 'de');
        await pumpEventQueue();
        expect(preview.phase, LivePreviewPhase.unavailable);
        expect((events.single as LivePreviewEngineSelected).properties['reason'], reason.wireName);
        expect((events.single as LivePreviewEngineSelected).properties['engine'], 'none');
        preview.onPhonePcm(List.filled(640, 1));
        await pumpEventQueue();
        expect(engine.fed, isEmpty);
      });
    }

    test('wire parse keeps the closed sets and never reports ok without an engine', () {
      expect(LivePreviewStart.fromWire({'engine': 'sf_speech', 'reason': 'ok'}).engine, LivePreviewEngineKind.sfSpeech);
      expect(LivePreviewStart.fromWire({'engine': 'none', 'reason': 'ok'}).reason, LivePreviewReason.engineError);
      expect(LivePreviewStart.fromWire({'engine': 'cloud', 'reason': 'ok'}).engine, LivePreviewEngineKind.none);
      expect(LivePreviewStart.fromWire({'engine': 'none', 'reason': 'made_up'}).reason, LivePreviewReason.engineError);
      expect(LivePreviewStart.fromWire({'engine': 'none', 'reason': 'locale_asset_missing', 'bundledInstalled': true}),
          isA<LivePreviewStart>().having((s) => s.bundledInstalled, 'bundled', true));
      expect(LivePreviewStart.fromWire('nonsense').reason, LivePreviewReason.engineError);
      expect(LivePreviewResult.fromWire({'segmentId': '', 'text': 'x'}), isNull);
    });

    test('volatile hypotheses are replaced in place and finals settle', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.sfSpeech, LivePreviewReason.ok);
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('s1', 'hel', false);
      engine.emit('s1', 'hello wor', false);
      await pumpEventQueue();
      expect(preview.lines.single.text, 'hello wor');
      expect(preview.lines.single.isFinal, false);
      engine.emit('s1', 'Hello world.', true);
      engine.emit('s2', 'how', false);
      await pumpEventQueue();
      expect(preview.lines.map((line) => (line.text, line.isFinal)), [('Hello world.', true), ('how', false)]);
      expect(preview.latestLine, 'how');
      engine.emit('s2', '', false);
      await pumpEventQueue();
      expect(preview.lines.length, 1);
    });

    test('first-word latency is measured from the first fed audio', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      preview.admit(language: 'en');
      await pumpEventQueue();
      preview.onPhonePcm(List.filled(640, 1));
      await pumpEventQueue();
      expect(engine.fed.single.length, 640);
      clock = clock.add(const Duration(milliseconds: 850));
      engine.emit('a0', 'hi', false);
      engine.emit('a0', 'hi there', false);
      await pumpEventQueue();
      final firstWords = events.whereType<LivePreviewFirstWord>().toList();
      expect(firstWords.single.properties, {'engine': 'speech_transcriber', 'latency_ms': 850});
    });

    test('pendant packets: header stripped, a decoded COPY is fed, capture bytes untouched', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      preview.admit(language: 'en');
      await pumpEventQueue();
      final packet = [9, 9, 9, ...List.filled(80, 5)];
      final original = List<int>.of(packet);
      preview.onPendantPacket(packet, BleAudioCodec.opus);
      await pumpEventQueue();
      expect(packet, original);
      // 80 Opus bytes → 320 fake samples → 640 PCM bytes: one chunk, header gone.
      expect(engine.fed.single.length, 640);
      expect(engine.fed.single.buffer.asInt16List().toSet(), {5});
      preview.onPendantPacket([0, 0, 0, 1], BleAudioCodec.lc3FS1030);
      await pumpEventQueue();
      expect(engine.fed.length, 1);
    });

    test('overload drops preview audio only, never blocking the tap', () async {
      final slow = Completer<bool>();
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      engine.feedResult = () => slow.future;
      final bounded = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: events.add),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        maxQueuedPackets: 4,
        maxInFlightFeeds: 2,
        feedChunkBytes: 640,
      );
      addTearDown(bounded.dispose);
      bounded.admit(language: 'en');
      await pumpEventQueue();
      for (var i = 0; i < 10; i++) {
        bounded.onPhonePcm(List.filled(640, i));
      }
      // The tap only enqueued: four packets fit, six were dropped synchronously.
      expect(bounded.queuedPacketsForTesting, 4);
      expect(bounded.droppedPacketsForTesting, 6);
      await pumpEventQueue();
      expect(engine.fed.length, 2, reason: 'in-flight feeds are bounded; the rest are dropped');
      slow.complete(true);
      await pumpEventQueue();
      bounded.endCapture();
      final ended = events.whereType<LivePreviewSessionEnded>().single;
      expect(ended.properties['dropped_audio_ms'], 6 * 20 + 2 * 20);
    });

    test('runtime failure falls back to the next engine once, keeping the lines', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      engine.laterStarts.add(const LivePreviewStart(LivePreviewEngineKind.sfSpeech, LivePreviewReason.ok));
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('a0', 'before the failure', true);
      await pumpEventQueue();
      engine.fail(LivePreviewEngineKind.speechTranscriber);
      await pumpEventQueue();
      expect(engine.startExclusions.last, {LivePreviewEngineKind.speechTranscriber});
      expect(engine.stops, 1, reason: 'the dead engine is released before the next starts');
      expect(preview.phase, LivePreviewPhase.streaming);
      expect(preview.selected?.engine, LivePreviewEngineKind.sfSpeech);
      expect(preview.lines.single.text, 'before the failure');
      engine.emit('s1', 'after the fallback', true);
      await pumpEventQueue();
      expect(preview.lines.map((line) => line.text), ['before the failure', 'after the fallback']);
      // Each engine run is one selected + one ended event.
      expect(events.whereType<LivePreviewEngineSelected>().map((e) => e.properties['engine']),
          ['speech_transcriber', 'sf_speech']);
      expect(events.whereType<LivePreviewSessionEnded>().single.properties['engine'], 'speech_transcriber');
    });

    test('a second runtime failure, or no next engine, is the calm no-engine state', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      engine.laterStarts.add(const LivePreviewStart(LivePreviewEngineKind.sfSpeech, LivePreviewReason.ok));
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.fail(LivePreviewEngineKind.speechTranscriber);
      await pumpEventQueue();
      engine.fail(LivePreviewEngineKind.sfSpeech);
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.unavailable);
      expect(engine.startedLanguages.length, 2, reason: 'only one fallback per admitted session');
      final last = events.whereType<LivePreviewEngineSelected>().last.properties;
      expect([last['engine'], last['reason']], ['none', 'engine_error']);

      // A fresh admission starts clean.
      preview.revoke();
      engine.laterStarts.addAll(const [
        LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok),
        LivePreviewStart.none(LivePreviewReason.speechPermissionDenied),
      ]);
      preview.admit(language: 'en');
      await pumpEventQueue();
      expect(engine.startExclusions.last, isEmpty);
      expect(preview.phase, LivePreviewPhase.streaming);
      engine.fail(LivePreviewEngineKind.speechTranscriber);
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.unavailable, reason: 'the fallback had no engine');
    });

    test('native failure events and channel errors surface as typed runtime failures', () async {
      final failures = <Object>[];
      const events = EventChannel('test/live_preview/events');
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockStreamHandler(events, MockStreamHandler.inline(onListen: (args, sink) {
        sink.success({'segmentId': 'a0', 'text': 'hi', 'isFinal': false});
        sink.success({'failure': 'engine_error', 'engine': 'speech_transcriber'});
        sink.error(code: 'broken');
      }));
      addTearDown(() => messenger.setMockStreamHandler(events, null));
      final results = <String>[];
      final sub = MethodChannelLivePreviewEngine(events: events)
          .results
          .listen((result) => results.add(result.text), onError: failures.add);
      await pumpEventQueue();
      await sub.cancel();
      expect(results, ['hi']);
      expect(failures.map((f) => (f as LivePreviewRuntimeFailure).engine),
          [LivePreviewEngineKind.speechTranscriber, LivePreviewEngineKind.none]);
      expect((failures.first as LivePreviewRuntimeFailure).reason, LivePreviewReason.engineError);
    });

    test('a burst never delays capture callbacks: decode yields every few packets', () async {
      final decodes = <int>[];
      final sliced = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: events.add),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        maxPacketsPerTurn: 8,
        decodeOpus: (opus) {
          // A slow decoder: a busy-wait per packet.
          final watch = Stopwatch()..start();
          while (watch.elapsedMicroseconds < 2000) {}
          decodes.add(opus.first);
          return Int16List(320);
        },
      );
      addTearDown(sliced.dispose);
      sliced.admit(language: 'en');
      await pumpEventQueue();
      final enqueue = Stopwatch()..start();
      for (var i = 0; i < 40; i++) {
        sliced.onPendantPacket([0, 0, 0, i], BleAudioCodec.opus);
      }
      enqueue.stop();
      expect(decodes, isEmpty, reason: 'the tap only enqueues');
      expect(enqueue.elapsedMilliseconds, lessThan(20));
      // The next capture event (a zero timer queued after the burst) runs
      // after at most one bounded slice of decode work.
      final seenByNextCallback = Completer<int>();
      Timer.run(() => seenByNextCallback.complete(decodes.length));
      expect(await seenByNextCallback.future, lessThanOrEqualTo(8));
      await pumpEventQueue();
      expect(decodes, List.generate(40, (i) => i), reason: 'every packet still decoded, in order');
    });

    test('a conversation-length silence starts a fresh preview span', () async {
      final gapped = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: events.add),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
        now: () => clock,
        conversationGap: () => const Duration(minutes: 2),
      );
      addTearDown(gapped.dispose);
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      gapped.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('a0', 'first conversation', true);
      await pumpEventQueue();
      clock = clock.add(const Duration(minutes: 2));
      engine.emit('a1', 'second', false);
      await pumpEventQueue();
      expect(gapped.lines.map((line) => line.text), ['second']);
    });

    test('revoke keeps lines for a quick re-admission; endCapture drops them', () async {
      engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
      preview.admit(language: 'en');
      await pumpEventQueue();
      engine.emit('a0', 'kept', true);
      await pumpEventQueue();
      preview.revoke();
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.inactive);
      expect(engine.stops, 1);
      expect(preview.lines.single.text, 'kept');
      final ended = events.whereType<LivePreviewSessionEnded>().single;
      expect(ended.properties,
          {'engine': 'speech_transcriber', 'preview_words': 1, 'preview_audio_ms': 0, 'dropped_audio_ms': 0});
      preview.endCapture();
      expect(preview.lines, isEmpty);
      expect(preview.latestLine, isNull);
    });

    test('a revoke while the engine starts stops it and never streams', () async {
      final gate = Completer<LivePreviewStart>();
      engine.startGate = gate;
      preview.admit(language: 'en');
      await pumpEventQueue();
      expect(engine.startedLanguages, ['en'], reason: 'the native start is in flight');
      preview.revoke();
      gate.complete(const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok));
      await pumpEventQueue();
      expect(preview.phase, LivePreviewPhase.inactive);
      expect(engine.stops, 1);
      expect(events, isEmpty);
    });
  });

  group('native channel', () {
    const channel = MethodChannel('com.omi/live_preview');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    tearDown(() => messenger.setMockMethodCallHandler(channel, null));

    test('uses its own channel and maps a missing plugin to os_engine_unavailable', () async {
      expect(MethodChannelLivePreviewEngine.methodChannelName, isNot('com.omi/on_device'));
      final engine = MethodChannelLivePreviewEngine();
      final start = await engine.start('en');
      expect(start.engine, LivePreviewEngineKind.none);
      expect(start.reason, LivePreviewReason.osEngineUnavailable);
      expect(await engine.feedPcm16(Uint8List(4)), false);
    });

    test('queued preview PCM keeps capture time rather than decode delivery time', () async {
      var clock = DateTime.utc(2026, 10, 27);
      final capturedAt = clock;
      final native = FakeLivePreviewEngine();
      final preview = LivePreviewController(
          engine: native,
          now: () => clock,
          telemetry: LivePreviewTelemetry(emit: (_) {}),
          platform: LivePreviewPlatform.ios,
          osMajor: 26);
      addTearDown(preview.dispose);
      preview.admit(language: 'en');
      await pumpEventQueue();
      preview.onPhonePcm(List.filled(3200, 0));
      clock = clock.add(const Duration(seconds: 10));
      await pumpEventQueue();
      expect(native.fedStartedAt.single, capturedAt.subtract(const Duration(milliseconds: 100)));
    });

    test('start/feed/stop round-trip the native contract', () async {
      final calls = <MethodCall>[];
      messenger.setMockMethodCallHandler(channel, (call) async {
        calls.add(call);
        return switch (call.method) {
          'start' => {'engine': 'speech_transcriber', 'reason': 'ok', 'bundledInstalled': true},
          'feed' => true,
          _ => null,
        };
      });
      final engine = MethodChannelLivePreviewEngine();
      final start = await engine.start('en');
      expect(start.engine, LivePreviewEngineKind.speechTranscriber);
      expect(start.bundledInstalled, true);
      final capturedAt = DateTime.utc(2026, 10, 27);
      expect(await engine.feedPcm16(Uint8List.fromList([1, 2]), startedAt: capturedAt), true);
      expect((calls.last.arguments as Map)['startMs'], capturedAt.millisecondsSinceEpoch);
      expect((calls.last.arguments as Map)['pcm'], Uint8List.fromList([1, 2]));
      await engine.stop();
      expect(calls.map((call) => call.method), ['start', 'feed', 'stop']);
      expect(calls.first.arguments, {'language': 'en'});
    });

    test('OS major parse', () {
      expect(osMajorVersion('Version 26.1 (Build 23B85)'), 26);
      expect(osMajorVersion('18.6'), 18);
      expect(osMajorVersion(''), 0);
    });
  });
}
