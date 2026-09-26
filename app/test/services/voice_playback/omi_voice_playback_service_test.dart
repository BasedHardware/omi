import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/tts.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter;

const _firstSentence = 'This is the first sentence for playback testing.';

/// Two synthesis chunks. The chunker keeps the last terminator inside the first
/// ideal window, so the only period before that window's end is [_firstSentence].
const _twoChunkReply =
    '$_firstSentence And then the reply continues with additional words until the chunker is past the first ideal window.';
final _mp3 = Uint8List.fromList(const [1, 2, 3]);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late OmiVoicePlaybackService service;
  late RecordingAdapter adapter;
  late List<Completer<void>> delays;
  late List<Uint8List> plays;
  late List<String> spoken;
  var now = DateTime.utc(2026, 9, 26);
  var probed = false;

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.543',
      buildNumber: '992',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    service = OmiVoicePlaybackService.instance;
    service.debugReset();
    adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    delays = [];
    plays = [];
    spoken = [];
    now = DateTime.utc(2026, 9, 26);
    probed = false;
  });

  tearDown(() {
    service.debugReset();
    AnalyticsManager.resetForTesting();
  });

  Future<void> install({
    required Future<Uint8List?> Function(String text) synthesize,
    Future<void> Function(Uint8List bytes)? play,
    VoicePlaybackOutputSnapshot output = const VoicePlaybackOutputSnapshot(
      headphonesConnected: true,
      checkFailed: false,
      route: VoiceReplyPlaybackOutputRoute.bluetooth,
    ),
  }) async {
    service.debugHooks = VoicePlaybackDebugHooks(
      synthesize: ({required String text}) => synthesize(text),
      play: play ?? (bytes) async => plays.add(bytes),
      stopPlayback: () async {},
      speak: (text) async => spoken.add(text),
      stopSpeak: () async {},
      probeOutput: () async {
        probed = true;
        return output;
      },
      now: () => now,
      delay: (duration) {
        expect(duration, const Duration(milliseconds: 500));
        final completer = Completer<void>();
        delays.add(completer);
        return completer.future;
      },
    );
  }

  Future<void> releaseDelays() async {
    for (var i = 0; i < 5 && delays.isNotEmpty; i++) {
      final pending = List<Completer<void>>.of(delays);
      delays.clear();
      for (final completer in pending) {
        if (!completer.isCompleted) completer.complete();
      }
      await pumpEventQueue();
    }
  }

  Future<void> flush() async {
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
  }

  List<Map<String, Object>> playbackEvents() =>
      adapter.events.where((event) => event.$1 == 'Voice Reply Playback').map((event) => event.$2).toList();

  void expectFields(Map<String, Object> event, Map<String, Object> expected) {
    for (final entry in expected.entries) {
      expect(event[entry.key], entry.value, reason: entry.key);
    }
    expect(event.values.any((value) => '$value'.contains('sentence')), isFalse);
  }

  Future<void> finishPlayback() async {
    await pumpEventQueue();
    service.debugNotifyPlaybackCompleted();
    await pumpEventQueue();
    await releaseDelays();
    await flush();
  }

  test('mode off emits skipped once and does not probe output', () async {
    SharedPreferencesUtil().voiceResponseMode = 0;
    await service.beginResponse(messageId: 'off');
    await flush();

    expect(probed, isFalse);
    expect(playbackEvents(), hasLength(1));
    expectFields(playbackEvents().single, {
      'outcome': 'skipped',
      'skip_reason': 'mode_off',
      'mode': 'off',
      'output_route': 'unknown',
      'chunks_requested': 0,
      'chunks_played': 0,
      'chunks_dropped': 0,
      'fallback_reason': 'none',
      'first_audio_latency_ms': -1,
      'interrupt_source': 'none',
    });

    await service.interrupt(source: VoiceReplyPlaybackInterruptSource.userTyped);
    await flush();
    expect(playbackEvents(), hasLength(1));
  });

  test('no headphones emits skipped and does not synthesize', () async {
    SharedPreferencesUtil().voiceResponseMode = 1;
    var synthesized = false;
    await install(
      output: const VoicePlaybackOutputSnapshot(
        headphonesConnected: false,
        checkFailed: false,
        route: VoiceReplyPlaybackOutputRoute.speaker,
      ),
      synthesize: (text) async {
        synthesized = true;
        return _mp3;
      },
    );

    await service.beginResponse(messageId: 'quiet');
    await flush();

    expect(probed, isTrue);
    expect(synthesized, isFalse);
    expect(plays, isEmpty);
    expect(playbackEvents().single['outcome'], 'skipped');
    expect(playbackEvents().single['skip_reason'], 'no_headphones');
    expect(playbackEvents().single['mode'], 'headphones_only');
    expect(playbackEvents().single['output_route'], 'speaker');
    expect(playbackEvents().single['first_audio_latency_ms'], -1);
  });

  test('headphone check failure is its own skip reason', () async {
    SharedPreferencesUtil().voiceResponseMode = 1;
    await install(
      output: const VoicePlaybackOutputSnapshot(
        headphonesConnected: false,
        checkFailed: true,
        route: VoiceReplyPlaybackOutputRoute.unknown,
      ),
      synthesize: (_) async => _mp3,
    );

    await service.beginResponse(messageId: 'probe-failed');
    await flush();

    expect(playbackEvents().single['outcome'], 'skipped');
    expect(playbackEvents().single['skip_reason'], 'headphone_check_failed');
    expect(playbackEvents().single['output_route'], 'unknown');
  });

  test('played reports chunk counts, route, and latency to first play', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    await install(synthesize: (_) async => _mp3);

    await service.beginResponse(messageId: 'played');
    now = now.add(const Duration(milliseconds: 320));
    service.updateStreamingResponse(messageId: 'played', fullText: _firstSentence, isFinal: true);
    await finishPlayback();

    expect(plays, [_mp3]);
    expect(spoken, isEmpty);
    final event = playbackEvents().single;
    expect(event['outcome'], 'played');
    expect(event['skip_reason'], 'none');
    expect(event['mode'], 'always');
    expect(event['output_route'], 'bluetooth');
    expect(event['chunks_requested'], 1);
    expect(event['chunks_played'], 1);
    expect(event['chunks_dropped'], 0);
    expect(event['fallback_reason'], 'none');
    expect(event['first_audio_latency_ms'], 320);
    expect(event['interrupt_source'], 'none');
  });

  test('a synthesis error drops that chunk and still plays the next', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    var calls = 0;
    await install(synthesize: (text) async {
      calls++;
      if (calls == 1) throw Exception('synth failed');
      return _mp3;
    });

    await service.beginResponse(messageId: 'drop');
    service.updateStreamingResponse(
      messageId: 'drop',
      fullText: _twoChunkReply,
      isFinal: true,
    );
    await finishPlayback();

    expect(calls, 2);
    expect(plays, hasLength(1));
    final event = playbackEvents().single;
    expect(event['outcome'], 'played');
    expect(event['chunks_requested'], 2);
    expect(event['chunks_played'], 1);
    expect(event['chunks_dropped'], 1);
    expect(event['fallback_reason'], 'none');
  });

  test('429 falls back to on-device speech and emits fallback_only', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    await install(synthesize: (_) async => throw TtsUnavailableException(429));

    await service.beginResponse(messageId: 'limited');
    now = now.add(const Duration(milliseconds: 80));
    service.updateStreamingResponse(messageId: 'limited', fullText: _firstSentence, isFinal: true);
    await pumpEventQueue();
    await releaseDelays();
    await flush();

    expect(plays, isEmpty);
    expect(spoken, [_firstSentence]);
    final event = playbackEvents().single;
    expect(event['outcome'], 'fallback_only');
    expect(event['chunks_requested'], 1);
    expect(event['chunks_played'], 0);
    expect(event['chunks_dropped'], 0);
    expect(event['fallback_reason'], 'rate_limited_429');
    expect(event['first_audio_latency_ms'], 80);
    expect(event['interrupt_source'], 'none');
  });

  test('interrupt mid-play records the caller source', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    await install(synthesize: (_) async => _mp3);

    await service.beginResponse(messageId: 'cut');
    service.updateStreamingResponse(messageId: 'cut', fullText: _firstSentence, isFinal: true);
    await pumpEventQueue();
    expect(plays, hasLength(1));

    await service.interrupt(source: VoiceReplyPlaybackInterruptSource.userTyped);
    await flush();

    final event = playbackEvents().single;
    expect(event['outcome'], 'interrupted');
    expect(event['interrupt_source'], 'user_typed');
    expect(event['chunks_played'], 1);
    expect(event['chunks_requested'], 1);
  });

  test('a lifecycle emits exactly once across finish, interrupt, and a rapid double-call', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    await install(synthesize: (_) async => _mp3);

    await service.beginResponse(messageId: 'once');
    service.updateStreamingResponse(messageId: 'once', fullText: _firstSentence, isFinal: true);
    await pumpEventQueue();
    expect(service.isSpeaking, isTrue);
    await service.beginResponse(messageId: 'once');
    await finishPlayback();
    expect(playbackEvents(), hasLength(1));
    expect(playbackEvents().single['outcome'], 'played');

    await service.interrupt(source: VoiceReplyPlaybackInterruptSource.newVoiceQuery);
    service.debugNotifyPlaybackCompleted();
    await releaseDelays();
    await flush();
    expect(playbackEvents(), hasLength(1));

    await service.beginResponse(messageId: 'again');
    service.updateStreamingResponse(messageId: 'again', fullText: _firstSentence, isFinal: true);
    await pumpEventQueue();
    await service.beginResponse(messageId: 'again');
    service.debugNotifyPlaybackCompleted();
    service.debugNotifyPlaybackCompleted();
    await releaseDelays();
    await flush();
    expect(playbackEvents(), hasLength(2));
    expect(playbackEvents().last['outcome'], 'played');
  });

  test('idle before isFinal stays open and counts the later chunk', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    await install(synthesize: (_) async => _mp3);

    await service.beginResponse(messageId: 'slow');
    service.updateStreamingResponse(messageId: 'slow', fullText: _firstSentence, isFinal: false);
    await pumpEventQueue();
    service.debugNotifyPlaybackCompleted();
    await pumpEventQueue();
    await releaseDelays();
    await flush();

    expect(plays, hasLength(1));
    expect(playbackEvents(), isEmpty);

    service.updateStreamingResponse(messageId: 'slow', fullText: _twoChunkReply, isFinal: true);
    await pumpEventQueue();
    service.debugNotifyPlaybackCompleted();
    await pumpEventQueue();
    await releaseDelays();
    await flush();

    expect(plays, hasLength(2));
    expect(playbackEvents(), hasLength(1));
    expect(playbackEvents().single['outcome'], 'played');
    expect(playbackEvents().single['chunks_played'], 2);
  });

  test('interrupt during the first chunk keeps first-audio latency', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    final playing = Completer<void>();
    await install(
      synthesize: (_) async => _mp3,
      play: (bytes) {
        plays.add(bytes);
        return playing.future;
      },
    );

    await service.beginResponse(messageId: 'mid-chunk');
    now = now.add(const Duration(milliseconds: 40));
    service.updateStreamingResponse(messageId: 'mid-chunk', fullText: _firstSentence, isFinal: true);
    await pumpEventQueue();
    expect(plays, hasLength(1));

    await service.interrupt(source: VoiceReplyPlaybackInterruptSource.userTyped);
    if (!playing.isCompleted) playing.complete();
    await pumpEventQueue();
    await flush();

    expect(playbackEvents(), hasLength(1));
    final event = playbackEvents().single;
    expect(event['outcome'], 'interrupted');
    expect(event['interrupt_source'], 'user_typed');
    expect(event['chunks_played'], 0);
    expect(event['first_audio_latency_ms'], greaterThanOrEqualTo(0));
    expect(event['first_audio_latency_ms'], 40);
  });
}
