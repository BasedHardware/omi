import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

class _RecordingCaptureExternalActions extends NoopCaptureExternalActions {
  int sendCount = 0;

  @override
  Future<void> sendVoiceMessageStreamToServer(
    List<List<int>> data, {
    required void Function() onFirstChunkRecived,
    required BleAudioCodec codec,
    required bool playResponseAudio,
  }) async {
    sendCount++;
  }
}

BtDevice _device(DeviceType type) => BtDevice(name: 'test-device', id: 'test-id', type: type, rssi: -40);

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('disabled Omi actions still deliver tutorial button events', () {
    final onboarding = DeviceOnboardingProvider()..startOnboarding();
    onboarding.advanceStep();
    final provider = CaptureProvider(speakerHaptic: (_, __) async => true);
    provider.deviceOnboardingProvider = onboarding;
    provider.updateRecordingDevice(_device(DeviceType.omi));
    SharedPreferencesUtil().omiButtonActionsEnabled = false;

    provider.handleButtonEventForTesting('test-id', 1);
    expect(onboarding.voiceSessionActive, isTrue);
    expect(provider.hasVoiceCommandSessionForTesting, isTrue);

    provider.handleButtonEventForTesting('test-id', 1);
    expect(onboarding.questionSent, isTrue);
    expect(onboarding.voiceSessionActive, isFalse);

    provider.dispose();
    onboarding.dispose();
  });

  test('disabled Omi actions still deliver tutorial double-press events', () {
    final onboarding = DeviceOnboardingProvider()..startOnboarding();
    onboarding.advanceStep();
    onboarding.advanceStep();
    onboarding.advanceStep();
    onboarding.selectDoubleTapAction(1);
    final provider = CaptureProvider();
    provider.deviceOnboardingProvider = onboarding;
    provider.updateRecordingDevice(_device(DeviceType.omi));
    SharedPreferencesUtil().omiButtonActionsEnabled = false;

    provider.handleButtonEventForTesting('test-id', 2);

    expect(onboarding.doublePressCount, 1);
    provider.dispose();
    onboarding.dispose();
  });

  test('capability-normalized OpenGlass identity bypasses the Omi-only gate', () async {
    final actions = _RecordingCaptureExternalActions();
    final provider = CaptureProvider(externalActions: actions, audioCodecLoader: (_) async => BleAudioCodec.opus);
    provider.updateRecordingDevice(_device(DeviceType.openglass));
    SharedPreferencesUtil().omiButtonActionsEnabled = false;

    await provider.processVoiceCommandBytesForTesting('test-id', [
      <int>[1],
    ]);

    expect(actions.sendCount, 1);
    provider.dispose();
  });

  test('disabling actions cancels an active voice session', () {
    final provider = CaptureProvider(speakerHaptic: (_, __) async => true);
    provider.updateRecordingDevice(_device(DeviceType.omi));

    provider.handleButtonEventForTesting('test-id', 1);
    expect(provider.hasVoiceCommandSessionForTesting, isTrue);

    provider.cancelActiveVoiceSession();

    expect(provider.hasVoiceCommandSessionForTesting, isFalse);
    provider.dispose();
  });

  test('disabling actions during codec lookup prevents voice submission', () async {
    final codecRequested = Completer<void>();
    final codec = Completer<BleAudioCodec>();
    final actions = _RecordingCaptureExternalActions();
    final provider = CaptureProvider(
      externalActions: actions,
      audioCodecLoader: (_) {
        codecRequested.complete();
        return codec.future;
      },
    );
    provider.updateRecordingDevice(_device(DeviceType.omi));
    SharedPreferencesUtil().omiButtonActionsEnabled = true;

    final processing = provider.processVoiceCommandBytesForTesting('test-id', [
      <int>[1],
    ]);
    await codecRequested.future;
    provider.cancelActiveVoiceSession();
    codec.complete(BleAudioCodec.opus);
    await processing;

    expect(actions.sendCount, 0);
    provider.dispose();
  });
}
