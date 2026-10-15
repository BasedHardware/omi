import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/apple_speech_analyzer_gate.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/utils/audio/wav_bytes.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.omi.ios/speech');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test('missing/false kill switch keeps improved engine on', () async {
    expect(
        await AppleSpeechAnalyzerGate.useNewEngine(readFlag: (key) async {
          expect(key, 'mobile-speech-analyzer-disabled');
          return false;
        }),
        isTrue);
  });
  test('true kill switch rolls back to SFSpeech', () async {
    expect(await AppleSpeechAnalyzerGate.useNewEngine(readFlag: (_) async => true), isFalse);
  });
  test('unavailable flag read retains new-engine default', () async {
    expect(await AppleSpeechAnalyzerGate.useNewEngine(readFlag: (_) async => throw Exception('offline')), isTrue);
  });
  for (final enabled in [true, false]) {
    test('availability passes engine choice $enabled to native', () async {
      messenger.setMockMethodCallHandler(channel, (call) async {
        expect(call.method, 'onDeviceAvailable');
        expect(call.arguments['useSpeechAnalyzer'], enabled);
        expect(call.arguments['language'], 'en');
        return true; // Either analyzer or legacy availability can satisfy this.
      });
      expect(await OnDeviceAppleProvider.isOnDeviceAvailable('en', isIOS: true, useSpeechAnalyzer: () async => enabled),
          isTrue);
    });
  }
  for (final available in [false, null]) {
    test('native unavailable or unsupported reports $available safely', () async {
      messenger.setMockMethodCallHandler(channel, (_) async => available);
      expect(await OnDeviceAppleProvider.isOnDeviceAvailable('zz', isIOS: true, useSpeechAnalyzer: () async => true),
          isFalse);
    });
  }
  test('availability channel failure and non-iOS are unavailable', () async {
    messenger.setMockMethodCallHandler(channel, (_) async => throw PlatformException(code: 'unavailable'));
    expect(await OnDeviceAppleProvider.isOnDeviceAvailable('en', isIOS: true), isFalse);
    expect(await OnDeviceAppleProvider.isOnDeviceAvailable('en', isIOS: false), isFalse);
  });
  for (final enabled in [true, false]) {
    test('transcription passes engine choice $enabled and cleans up audio', () async {
      final dir = await Directory.systemTemp.createTemp('speech-engine-choice-');
      const pathChannel = MethodChannel('plugins.flutter.io/path_provider');
      messenger.setMockMethodCallHandler(pathChannel, (_) async => dir.path);
      messenger.setMockMethodCallHandler(channel, (call) async {
        expect(call.arguments['useSpeechAnalyzer'], enabled);
        expect(File(call.arguments['filePath'] as String).existsSync(), isTrue);
        return 'We are testing speech recognition today.';
      });
      try {
        final pcm = Uint8List(32000);
        final samples = ByteData.sublistView(pcm);
        for (var i = 0; i < pcm.length; i += 2) {
          samples.setInt16(i, i % 4 == 0 ? 9000 : -9000, Endian.little);
        }
        final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();
        final result = await OnDeviceAppleProvider(useSpeechAnalyzer: () async => enabled).transcribe(wav);
        expect(result!.rawText, contains('testing speech'));
        expect(await dir.list().toList(), isEmpty);
      } finally {
        messenger.setMockMethodCallHandler(pathChannel, null);
        await dir.delete(recursive: true);
      }
    });
  }
}
