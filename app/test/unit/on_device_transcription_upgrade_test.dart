import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/services/sockets/on_device_transcript_quality_gate.dart';

void main() {
  group('OnDeviceTranscriptQualityGate', () {
    test('drops repeated one-word no hallucinations', () {
      final gate = OnDeviceTranscriptQualityGate();

      expect(gate.filter('no', audioData: _loudPcmWav(), duration: const Duration(seconds: 3)), 'no');
      expect(gate.filter('No.', audioData: _loudPcmWav(), duration: const Duration(seconds: 3)), isNull);
      expect(gate.filter(' no ', audioData: _loudPcmWav(), duration: const Duration(seconds: 3)), isNull);
    });

    test('drops filler no on low-energy audio', () {
      final gate = OnDeviceTranscriptQualityGate();

      expect(gate.filter('no', audioData: _silentPcmWav(), duration: const Duration(seconds: 3)), isNull);
    });

    test('keeps real speech and resets duplicate gate', () {
      final gate = OnDeviceTranscriptQualityGate();

      expect(gate.filter('no', audioData: _loudPcmWav(), duration: const Duration(seconds: 3)), 'no');
      expect(gate.filter('no problem, start capture', audioData: _loudPcmWav(), duration: const Duration(seconds: 3)),
          'no problem, start capture');
      expect(gate.filter('no', audioData: _loudPcmWav(), duration: const Duration(seconds: 3)), 'no');
    });
  });

  test('iOS Apple on-device STT uses a multi-second polling window', () {
    final source = File('lib/services/sockets/transcription_service.dart').readAsStringSync();
    final appleBlock = RegExp(
      r'if \(Platform\.isIOS\) \{(?<block>[\s\S]*?)sttProvider: OnDeviceAppleProvider',
      multiLine: true,
    ).firstMatch(source)!.namedGroup('block')!;

    expect(appleBlock, contains('bufferDuration: const Duration(seconds: 3)'));
    expect(appleBlock, contains('minBufferSizeBytes: sampleRate * 2 * 2'));
  });

  test('native iOS speech fallback is tuned for dictation', () {
    final source = File('ios/Runner/AppDelegate.swift').readAsStringSync();

    expect(source, contains('request.taskHint = .dictation'));
    expect(source, contains('request.addsPunctuation = true'));
  });

  test('Apple on-device STT drops low-energy filler transcripts', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final tempDir = await Directory.systemTemp.createTemp('on-device-apple-provider-');
    const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
    const speechChannel = MethodChannel('com.omi.ios/speech');

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      (call) async => call.method == 'getTemporaryDirectory' ? tempDir.path : null,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      speechChannel,
      (call) async => 'no',
    );

    try {
      final provider = OnDeviceAppleProvider();

      final result = await provider.transcribe(_silentPcmWav());

      expect(result, isNull);
    } finally {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        pathProviderChannel,
        null,
      );
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        speechChannel,
        null,
      );
      if (await tempDir.exists()) await tempDir.delete(recursive: true);
    }
  });
}

Uint8List _silentPcmWav() => _pcmWav(List<int>.filled(1600, 0));

Uint8List _loudPcmWav() => _pcmWav(List<int>.generate(1600, (i) => i.isEven ? 9000 : -9000));

Uint8List _pcmWav(List<int> samples) {
  final dataSize = samples.length * 2;
  final out = BytesBuilder();
  void ascii(String value) => out.add(value.codeUnits);
  void u16(int value) => out.add([value & 0xff, (value >> 8) & 0xff]);
  void u32(int value) => out.add([value & 0xff, (value >> 8) & 0xff, (value >> 16) & 0xff, (value >> 24) & 0xff]);
  ascii('RIFF');
  u32(36 + dataSize);
  ascii('WAVEfmt ');
  u32(16);
  u16(1);
  u16(1);
  u32(16000);
  u32(32000);
  u16(2);
  u16(16);
  ascii('data');
  u32(dataSize);
  for (final sample in samples) {
    final value = sample < 0 ? 0x10000 + sample : sample;
    u16(value);
  }
  return out.toBytes();
}
