import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/sockets/transcription_service.dart';

class _RecordingSocketCapture extends CaptureProvider {
  CustomSttConfig? lastConfig;
  int openCalls = 0;

  @override
  Future<TranscriptSegmentSocketService?> openConversationSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
  }) async {
    openCalls++;
    lastConfig = customSttConfig;
    return null;
  }
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().batchModeEnabled = false;
  });

  tearDown(SttModeResolver.debugResetInstance);

  Future<void> start(_RecordingSocketCapture capture, {BleAudioCodec codec = BleAudioCodec.opus}) {
    return capture.changeAudioRecordProfile(
      audioCodec: codec,
      sampleRate: 16000,
      source: ConversationSource.phone.name,
    );
  }

  test('entry: basic on_device + ready never opens a managed Omi socket', () async {
    SttModeResolver.instance = SttModeResolver(
      flagReader: () => true,
      allowanceReader: () => const TranscriptionAllowanceSnapshot(
        mode: 'on_device',
        reason: 'plan_allowance_exhausted',
      ),
      readinessReader: () async => FreemiumReadiness.ready,
      onDeviceConfigBuilder: () => const CustomSttConfig(
        provider: SttProvider.onDeviceWhisper,
        identity: SttModeResolver.freemiumOnDeviceId,
      ),
    );
    final capture = _RecordingSocketCapture();
    await start(capture);

    expect(capture.openCalls, 1);
    expect(capture.lastConfig, isNotNull);
    expect(capture.lastConfig!.sttConfigId, SttModeResolver.freemiumOnDeviceId);
    expect(capture.lastConfig!.isEnabled, isTrue);
  });

  test('entry: Android not-ready basic never reaches openConversationSocket', () async {
    SttModeResolver.instance = SttModeResolver(
      flagReader: () => true,
      allowanceReader: () => const TranscriptionAllowanceSnapshot(
        mode: 'on_device',
        reason: 'subscription_inactive',
      ),
      readinessReader: () async => FreemiumReadiness.requiresSetup,
      onDeviceConfigBuilder: () => const CustomSttConfig(provider: SttProvider.onDeviceWhisper),
    );
    final capture = _RecordingSocketCapture();
    await start(capture);

    expect(capture.openCalls, 0, reason: 'managed socket must be unreachable for Android-not-ready basic');
  });

  test('entry: unsupported codec + on_device never falls back to Omi', () async {
    SttModeResolver.instance = SttModeResolver(
      flagReader: () => true,
      allowanceReader: () => const TranscriptionAllowanceSnapshot(
        mode: 'on_device',
        reason: 'plan_allowance_exhausted',
      ),
      readinessReader: () async => FreemiumReadiness.ready,
      onDeviceConfigBuilder: () => const CustomSttConfig(
        provider: SttProvider.onDeviceWhisper,
        identity: SttModeResolver.freemiumOnDeviceId,
      ),
    );
    final capture = _RecordingSocketCapture();
    await start(capture, codec: BleAudioCodec.aac);

    expect(capture.openCalls, 0);
  });

  test('entry: flag off still opens today\'s managed socket for basic', () async {
    SttModeResolver.instance = SttModeResolver(
      flagReader: () => false,
      allowanceReader: () => const TranscriptionAllowanceSnapshot(
        mode: 'on_device',
        reason: 'plan_allowance_exhausted',
      ),
      readinessReader: () async => FreemiumReadiness.ready,
      onDeviceConfigBuilder: () => const CustomSttConfig(provider: SttProvider.onDeviceWhisper),
    );
    final capture = _RecordingSocketCapture();
    await start(capture);

    expect(capture.openCalls, 1);
    expect(capture.lastConfig, isNull, reason: 'flag off keeps the Omi default socket');
  });
}
