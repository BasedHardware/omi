import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/services.dart';

/// Mic double that reproduces [ArbitratedMic]'s contention contract: starting a
/// chat voice memo while a conversation holds the mic throws a [StateError].
class _ContendedMic implements IMicRecorderService {
  bool failStart = true;
  int startCalls = 0;
  int stopCalls = 0;
  Function()? _onStop;

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {
    startCalls++;
    if (failStart) {
      throw StateError('Microphone is busy (held by conversation)');
    }
    _onStop = onStop;
  }

  @override
  Future<void> startBatch({
    Function()? onStop,
    Function(bool began)? onInterruption,
    Function()? onBatchStalled,
    Function(String code, String message)? onError,
  }) async {
    throw UnsupportedError('batch capture is not used by the voice recorder');
  }

  @override
  void stop() {
    stopCalls++;
    _onStop?.call();
    _onStop = null;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  const permissionsChannel = MethodChannel('flutter.baseflow.com/permissions/methods');

  late Directory tempDir;

  Directory recordingsDir() => Directory('${tempDir.path}/voice_recordings');

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = Directory.systemTemp.createTempSync('voice_recorder_contention_');

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(pathProviderChannel, (
      MethodCall call,
    ) async {
      if (call.method == 'getApplicationSupportDirectory') return tempDir.path;
      if (call.method == 'getTemporaryDirectory') return tempDir.path;
      return null;
    });
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(permissionsChannel, (
      MethodCall call,
    ) async {
      if (call.method == 'checkPermissionStatus') return 1;
      if (call.method == 'requestPermissions') {
        return {for (final permission in call.arguments as List<dynamic>) permission: 1};
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      null,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      permissionsChannel,
      null,
    );
    if (tempDir.existsSync()) {
      tempDir.deleteSync(recursive: true);
    }
  });

  group('VoiceRecorderProvider mic contention', () {
    test('a busy mic unwinds the half-armed session instead of escaping', () async {
      final mic = _ContendedMic();
      final provider = VoiceRecorderProvider(mic: mic);
      final observed = <VoiceRecorderState>[];
      provider.addListener(() => observed.add(provider.state));

      // Must not throw: startRecording() is called fire-and-forget from a tap
      // handler, so an escaping StateError is an unhandled async crash.
      await provider.startRecording();

      expect(mic.startCalls, 1);
      expect(provider.state, VoiceRecorderState.idle);
      expect(provider.isRecording, isFalse);
      expect(provider.isActive, isFalse);

      // The session was armed, then unwound — and listeners saw both.
      expect(observed, contains(VoiceRecorderState.recording));
      expect(observed.last, VoiceRecorderState.idle);

      // The PCM file opened before the failed start is deleted.
      expect(recordingsDir().listSync(), isEmpty);
    });

    test('the provider is not wedged — a later start records normally', () async {
      final mic = _ContendedMic();
      final provider = VoiceRecorderProvider(mic: mic);

      await provider.startRecording();
      expect(provider.state, VoiceRecorderState.idle);

      mic.failStart = false;
      await provider.startRecording();

      expect(mic.startCalls, 2);
      expect(provider.state, VoiceRecorderState.recording);
      expect(provider.isRecording, isTrue);
      expect(recordingsDir().listSync().length, 1);

      provider.close();
      expect(mic.stopCalls, 1);
      expect(provider.state, VoiceRecorderState.idle);
    });
  });
}
