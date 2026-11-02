import 'package:flutter/foundation.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/services/sockets/apple_speech_readiness.dart';
import 'package:omi/services/sockets/on_device_whisper_provider.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/services/sockets/pure_polling.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/audio/whisper_pcm.dart';

class Listener implements IPureSocketListener {
  final errors = <Object>[];
  final messages = <dynamic>[];
  @override
  void onConnected() {}
  @override
  void onClosed([int? code]) {}
  @override
  void onError(Object err, StackTrace trace) {
    errors.add(err);
  }

  @override
  void onMessage(dynamic message) {
    messages.add(message);
  }
}

class SpeechThenSilence extends OnDeviceWhisperProvider {
  SpeechThenSilence() : super(modelPath: '/unused');
  final offsets = <double>[];
  @override
  Future<SttTranscriptionResult?> transcribeChunk(Uint8List bytes,
      {double audioOffsetSeconds = 0, String? language}) async {
    offsets.add(audioOffsetSeconds);
    return offsets.length == 1
        ? SttTranscriptionResult(
            segments: [SttSegment(text: 'speech', start: audioOffsetSeconds, end: audioOffsetSeconds + 30)])
        : null;
  }
}

class PausedSpeech implements ISttProvider, RecoverableLocalSttProvider {
  bool ready = false;
  final offsets = <double>[];
  @override
  Future<bool> isReadyToRetry() async => ready;
  @override
  Future<SttTranscriptionResult?> transcribe(Uint8List bytes, {double audioOffsetSeconds = 0}) async {
    if (!ready) throw const LocalSttFailure('permission_denied', canProbeRecovery: true);
    offsets.add(audioOffsetSeconds);
    final seconds = PassThroughTranscoder().sourceSeconds(bytes);
    return SttTranscriptionResult(
        audioEndSeconds: audioOffsetSeconds + seconds,
        segments: [SttSegment(text: 'recovered', start: audioOffsetSeconds, end: audioOffsetSeconds + seconds)]);
  }

  @override
  void dispose() {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  test('Apple runtime asset failure pauses retry, preserves saved audio and resumes the retained frames', () async {
    final temp = await Directory.systemTemp.createTemp('speech-runtime-assets');
    final recognitionTemp = await Directory('${temp.path}/recognition').create();
    final savedAudio = File('${temp.path}/saved-recording.bin');
    final pcm = Uint8List(32000);
    for (var i = 0; i < pcm.length; i += 2) {
      ByteData.sublistView(pcm).setInt16(i, i % 4 == 0 ? 9000 : -9000, Endian.little);
    }
    await savedAudio.writeAsBytes(pcm);
    const pathChannel = MethodChannel('plugins.flutter.io/path_provider');
    const speechChannel = MethodChannel('com.omi.ios/speech');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var ready = true;
    final submittedPcm = <List<int>>[];
    messenger.setMockMethodCallHandler(pathChannel, (_) async => recognitionTemp.path);
    messenger.setMockMethodCallHandler(speechChannel, (call) async {
      if (call.method == 'readiness') return {'engine': 'sfspeech', 'status': ready ? 'ready' : 'unavailable'};
      expect(call.method, 'transcribe');
      final args = call.arguments as Map;
      expect(args['useSpeechAnalyzer'], isFalse);
      final wav = await File(args['filePath'] as String).readAsBytes();
      submittedPcm.add(wav.sublist(44));
      if (submittedPcm.length == 1) {
        ready = false; // The real request fails after the initial ready probe.
        throw PlatformException(code: 'UNAVAILABLE', details: {
          'engine': 'sfspeech',
          'status': 'unavailable',
          'nativeErrorDomain': 'kLSRErrorDomain',
          'nativeErrorCode': 102,
        });
      }
      return 'Local speech is working again.';
    });
    final provider = OnDeviceAppleProvider(useSpeechAnalyzer: () async => false);
    final socket = PurePollingSocket(
        config: AudioPollingConfig(minBufferSizeBytes: 1, transcoder: PcmToWavTranscoder()), sttProvider: provider);
    final listener = Listener();
    socket.setListener(listener);
    CustomSttLogService.instance.clear();
    try {
      expect(await provider.isReadyToRetry(), isTrue);
      await socket.connect();
      socket.send(pcm);
      await socket.flushNow();
      expect(socket.localFailure!.code, 'unavailable');
      expect(socket.status, PureSocketStatus.connected);
      expect(socket.bufferedBytes, pcm.length);
      expect(socket.audioOffset, 0);
      expect(listener.messages, isEmpty);
      expect(listener.errors.single, isA<LocalSttFailure>());
      expect(CustomSttLogService.instance.logsAsText, contains('kLSRErrorDomain'));
      expect(CustomSttLogService.instance.logsAsText, contains('102'));
      expect(await recognitionTemp.list().toList(), isEmpty);
      socket.send(pcm);
      await socket.retryLocalTranscription();
      expect(submittedPcm, hasLength(1), reason: 'unavailable recognizer is probed, not repeatedly allocated');
      expect(socket.bufferedBytes, pcm.length * 2);
      ready = true;
      await socket.retryLocalTranscription();
      expect(submittedPcm, [
        pcm,
        [...pcm, ...pcm]
      ]);
      expect(socket.localFailure, isNull);
      expect(socket.bufferedBytes, 0);
      expect(socket.audioOffset, 2);
      expect(listener.messages, hasLength(1));
      expect(await recognitionTemp.list().toList(), isEmpty);
      expect(await savedAudio.readAsBytes(), pcm, reason: 'only disposable recognition WAVs may be deleted');
    } finally {
      await socket.stop();
      messenger.setMockMethodCallHandler(pathChannel, null);
      messenger.setMockMethodCallHandler(speechChannel, null);
      await temp.delete(recursive: true);
    }
  });
  test('real polling consumes speech then 35 seconds silence, then more silence', () async {
    final provider = SpeechThenSilence();
    final socket = PurePollingSocket(config: const AudioPollingConfig(minBufferSizeBytes: 1), sttProvider: provider);
    await socket.connect();
    socket.send(WavBytes.fromPcm(Uint8List(32000 * 65), sampleRate: 16000, numChannels: 1).asBytes());
    await socket.flushNow();
    expect(socket.audioOffset, 65);
    socket.send(WavBytes.fromPcm(Uint8List(32000 * 5), sampleRate: 16000, numChannels: 1).asBytes());
    await socket.flushNow();
    expect(provider.offsets, [0, 30, 60, 65]);
    expect(socket.audioOffset, 70);
    socket.stop();
  });
  for (final rate in [8000, 16000]) {
    test('real polling overflow advances source clock before recovery at $rate Hz', () async {
      final provider = PausedSpeech();
      final listener = Listener();
      final socket = PurePollingSocket(
          config: AudioPollingConfig(
              minBufferSizeBytes: 1, maxBufferBytes: rate * 2 * 2, transcoder: PcmToWavTranscoder(sampleRate: rate)),
          sttProvider: provider);
      socket.setListener(listener);
      await socket.connect();
      socket.setAudioOffset(10);
      socket.send(Uint8List(rate * 2));
      await socket.flushNow(); // Actual failure retains the first second.
      socket.send(Uint8List(rate * 2));
      socket.send(Uint8List(rate * 2)); // Drop exactly the oldest source second.
      expect(socket.audioOffset, 11);
      expect(socket.bufferedBytes, rate * 4);
      provider.ready = true;
      await socket.retryLocalTranscription();
      expect(provider.offsets, [11]);
      expect(listener.messages.single, contains('"start":11'));
      expect(socket.audioOffset, 13);
      await socket.stop();
    });
  }
  test('Opus source clock counts TOC duration, not compressed byte size', () {
    expect(opusPacketSeconds(Uint8List.fromList([0x98, 0])), 0.02);
    expect(opusPacketSeconds(Uint8List.fromList([0x99, 0, 0, 0])), 0.04);
    expect(opusPacketSeconds(Uint8List.fromList([0x9b, 3, 0])), 0.06);
  });
  for (final configuredSupported in [true, false]) {
    test('explicit language readiness overrides primary in both directions: $configuredSupported', () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final configured = configuredSupported ? 'en' : 'zz';
      SharedPreferencesUtil().userPrimaryLanguage = configuredSupported ? 'zz' : 'en';
      final config = CustomSttConfig(provider: SttProvider.onDeviceWhisper, language: configured);
      await SharedPreferencesUtil().saveCustomSttConfig(config);
      final probed = <String>[];
      final service = FreemiumTranscriptionService.testing(
          iosOverride: true,
          appleReadinessReader: (language) async {
            probed.add(language);
            return AppleSpeechReadiness('speech_analyzer', language == 'en' ? 'ready' : 'unavailable');
          });
      final resolver = SttModeResolver(flagReader: () => false, readinessReader: service.checkReadiness);
      final decision = await resolver.decide(persistedCustomStt: config, codec: BleAudioCodec.pcm16);
      expect(probed, [configured]);
      expect(decision.blockSocket, !configuredSupported);
      // Default readiness/preparation callers use the same configured language.
      await service.checkReadiness();
      expect(probed.last, configured);
      expect(FreemiumTranscriptionService.effectiveLanguage(), configured);
    });
  }
  test('pcm8 and stereo normalize before native entry without changing duration', () {
    for (final rate in [8000, 16000, 44100, 48000]) {
      for (final channels in [1, 2]) {
        final pcm = Uint8List(rate * channels * 2);
        for (var i = 0; i < pcm.length; i += 2) {
          ByteData.sublistView(pcm).setInt16(i, 12000, Endian.little);
        }
        final result = WhisperPcm.normalize(WavBytes.fromPcm(pcm, sampleRate: rate, numChannels: channels).asBytes());
        final header = ByteData.sublistView(result.wav);
        expect(header.getUint32(24, Endian.little), 16000);
        expect(header.getUint16(22, Endian.little), 1);
        expect(result.duration, 1);
        expect(result.wav.length, 32044);
        expect(header.getInt16(44, Endian.little), 12000);
      }
    }
  });
  test('actual malformed-input provider path pauses polling and retains frames', () async {
    final socket = PurePollingSocket(
        config: const AudioPollingConfig(minBufferSizeBytes: 1),
        sttProvider: OnDeviceWhisperProvider(modelPath: '/unused'));
    final listener = Listener();
    socket.setListener(listener);
    await socket.connect();
    socket.send(Uint8List.fromList([1, 2, 3]));
    await socket.flushNow();
    expect(socket.localFailure!.code, 'invalid_audio');
    expect(socket.bufferedBytes, 3);
    expect(socket.status, PureSocketStatus.connected);
    await socket.flushNow();
    await socket.flushNow();
    expect(listener.errors.length, 1, reason: 'permanent bad input never loops through native allocation');
    socket.stop();
  });
  for (final denied in ['permission_denied', 'unavailable']) {
    test('actual Apple provider rollback $denied preserves audio and recovers without reconnect', () async {
      final temp = await Directory.systemTemp.createTemp('speech-recovery');
      const pathChannel = MethodChannel('plugins.flutter.io/path_provider');
      const speechChannel = MethodChannel('com.omi.ios/speech');
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      var rollback = false;
      var calls = 0;
      messenger.setMockMethodCallHandler(pathChannel, (_) async => temp.path);
      messenger.setMockMethodCallHandler(speechChannel, (call) async {
        if (call.method == 'readiness') {
          return {'engine': rollback ? 'sfspeech' : 'speech_analyzer', 'status': rollback ? denied : 'ready'};
        }
        calls++;
        if (rollback) {
          throw PlatformException(
              code: denied == 'permission_denied' ? 'UNAUTHORIZED' : 'UNAVAILABLE', details: {'status': denied});
        }
        return 'We are testing local speech today.';
      });
      final provider = OnDeviceAppleProvider(useSpeechAnalyzer: () async => !rollback);
      final service = FreemiumTranscriptionService.testing(
          iosOverride: true,
          appleReadinessReader: (lang) =>
              OnDeviceAppleProvider.readiness(lang, useSpeechAnalyzer: () async => !rollback));
      final socket = PurePollingSocket(
          config: AudioPollingConfig(minBufferSizeBytes: 1, transcoder: PcmToWavTranscoder()), sttProvider: provider);
      final listener = Listener();
      socket.setListener(listener);
      try {
        expect(await service.checkReadiness(), FreemiumReadiness.ready);
        await socket.connect();
        rollback = true;
        expect(await service.checkReadiness(), FreemiumReadiness.requiresSetup);
        expect(service.getFreemiumConfig(), isNull);
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final resolver = SttModeResolver(flagReader: () => false, readinessReader: service.checkReadiness);
        final decision = await resolver.decide(
            persistedCustomStt: const CustomSttConfig(provider: SttProvider.onDeviceWhisper),
            codec: BleAudioCodec.pcm16);
        expect(decision.blockSocket, isTrue,
            reason: 'today’s persisted free fallback checks readiness even with plan flag off');
        expect(decision.allowanceOnDevice, isTrue);
        debugDefaultTargetPlatformOverride = null;
        final pcm = Uint8List(32000);
        for (var i = 0; i < pcm.length; i += 2) {
          ByteData.sublistView(pcm).setInt16(i, i % 4 == 0 ? 9000 : -9000, Endian.little);
        }
        socket.send(pcm);
        await socket.flushNow();
        expect(socket.localFailure!.code, denied);
        expect(socket.bufferedBytes, pcm.length);
        expect(listener.errors.single, isA<LocalSttFailure>());
        await socket.flushNow();
        expect(calls, 1);
        socket.send(pcm);
        expect(socket.bufferedBytes, pcm.length * 2);
        rollback = false;
        await socket.retryLocalTranscription();
        expect(socket.localFailure, isNull);
        expect(socket.bufferedBytes, 0);
        expect(listener.messages, hasLength(1));
        expect(calls, 2);
      } finally {
        debugDefaultTargetPlatformOverride = null;
        socket.stop();
        messenger.setMockMethodCallHandler(pathChannel, null);
        messenger.setMockMethodCallHandler(speechChannel, null);
        await temp.delete(recursive: true);
      }
    });
  }
}
