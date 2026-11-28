import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/experiments/on_device_runner_gate.dart';
import 'package:omi/services/on_device/on_device_engine.dart';
import 'package:omi/services/on_device/on_device_runner.dart';
import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import '../support/on_device_fakes.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

/// Drained pendant audio as `persistDeviceChunk(phoneOnly: true)` stamps it.
Wal drained(String file, int timerStart) => Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.pcm16,
    seconds: 1,
    status: WalStatus.miss,
    storage: WalStorage.disk,
    filePath: file,
    device: 'omi',
    originalStorage: WalStorage.sdcard,
    onDeviceOnly: true,
    capturedOnDeviceOnly: true);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi-pendant-drain-test-');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => directory.path);
  });
  tearDown(() async {
    AnalyticsManager.resetForTesting();
    OnDeviceRunnerGate.debugReset();
    await directory.delete(recursive: true);
  });

  void recording(String name) {
    final builder = BytesBuilder();
    for (var i = 0; i < 100; i++) {
      builder.add((ByteData(4)..setUint32(0, 320, Endian.little)).buffer.asUint8List());
      builder.add(Uint8List(320));
    }
    File('${directory.path}/$name').writeAsBytesSync(builder.takeBytes());
  }

  Future<void> selectOnDevice() =>
      SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.onDeviceWhisper));

  test('on-device STT is the only custom provider that counts as on-device selection', () async {
    expect(SharedPreferencesUtil().onDeviceSttSelected, isFalse);
    await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.deepgram));
    expect(SharedPreferencesUtil().onDeviceSttSelected, isFalse);
    await selectOnDevice();
    expect(SharedPreferencesUtil().onDeviceSttSelected, isTrue);
  });

  test('drained pendant audio keeps phone-only custody through save, load and legacy repair', () {
    final wal = drained('a.bin', 1700000000);
    final restored = Wal.fromJson(jsonDecode(jsonEncode(wal.toJson())) as Map<String, dynamic>)
      ..repairLegacyImportedCustody();
    expect(restored.onDeviceOnly, isTrue);
    expect(restored.capturedOnDeviceOnly, isTrue);
    expect(isAutoUploadEligible(restored), isFalse);
  });

  test('the allowance-held date survives save and load and is absent when not held', () {
    final wal = drained('a.bin', 1700000000)..allowanceHeldUntil = 1764547200;
    final restored = Wal.fromJson(jsonDecode(jsonEncode(wal.toJson())) as Map<String, dynamic>);
    expect(restored.allowanceHeldUntil, 1764547200);
    expect(drained('b.bin', 1).toJson().containsKey('allowance_held_until'), isFalse);
  });

  test('on-device selection transcribes drained audio newest first and releases it after confirmation', () async {
    await selectOnDevice();
    recording('old.bin');
    recording('new.bin');
    final older = drained('old.bin', 1700000000);
    final newer = drained('new.bin', 1700003600);
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {})..testWals = [older, newer];
    // The overflow setting stays off: choosing on-device STT is the consent for drained audio.
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
      ..debugActivate(settings: const OnDeviceSettings(enabled: false));
    final order = <String>[];
    var call = 0;
    final runner = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: (_) {},
        cloudBaseUrl: 'http://127.0.0.1:1/',
        transcribeChunk: (_, __) async {
          order.add(call++ == 0 ? 'first' : 'second');
          return const OnDeviceBatchResult(
              engine: 'synthetic', text: 'A synthetic test.', words: [OnDeviceWord('A synthetic test.', 0, 1)]);
        },
        send: (request) async {
          if (request.method == 'POST') {
            final body = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(jsonEncode({'id': 'cloud-${body['client_session_id']}'}), 200);
          }
          final id = Uri.parse(request.url.toString()).pathSegments.last;
          return http.Response(
              jsonEncode(
                  ServerConversation(id: id, createdAt: DateTime.utc(2026), structured: Structured('t', 'o')).toJson()),
              200);
        });
    await runner.run(transcribeNow: true);
    expect(order, ['first', 'second']);
    expect(newer.onDeviceConversation?['id'], isNotNull);
    expect(older.onDeviceConversation?['id'], isNotNull);
    // Ordering: the newer recording's conversation was published first.
    expect(newer.onDeviceConversation!['id'], contains(newer.id));
    for (final wal in [older, newer]) {
      expect(wal.status, WalStatus.synced, reason: 'server-confirmed audio enters synced retention');
      expect(wal.syncedAt, greaterThan(0));
      expect(wal.onDeviceOnly, isTrue, reason: 'custody never becomes cloud-uploadable');
    }
    runner.dispose();
    controller.dispose();
  });

  test('without on-device selection or the overflow setting nothing runs', () async {
    recording('a.bin');
    final wal = drained('a.bin', 1700000000);
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {})..testWals = [wal];
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
      ..debugActivate(settings: const OnDeviceSettings(enabled: false));
    var calls = 0;
    final runner = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: (_) {},
        transcribeChunk: (_, __) async {
          calls++;
          return const OnDeviceBatchResult(engine: 'synthetic', text: '', words: []);
        });
    await runner.run(transcribeNow: true);
    expect(calls, 0);
    expect(wal.status, WalStatus.miss);
    runner.dispose();
    controller.dispose();
  });

  test('a confirmed manual Sync releases only drained device audio still waiting', () async {
    final waiting = drained('a.bin', 1700000000);
    final transcribed = drained('b.bin', 1700000100)..onDeviceConversation = {'id': 'done'};
    final overflow = Wal(
        timerStart: 1700000200,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        filePath: 'c.bin',
        device: 'phone',
        onDeviceOnly: true,
        capturedOnDeviceOnly: true);
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {})..testWals = [waiting, transcribed, overflow];
    expect(await sync.releaseDrainedDeviceAudioForUpload(), 1);
    expect(waiting.onDeviceOnly, isFalse);
    expect(isAutoUploadEligible(waiting), isTrue);
    expect(transcribed.onDeviceOnly, isTrue);
    expect(overflow.onDeviceOnly, isTrue);
  });

  test('foreground runs drained audio on battery above the floor, whatever the schedule', () {
    const policy = OnDeviceSchedulePolicy();
    OnDeviceRunDecision decide({int? battery, bool foreground = true}) => policy.decide(OnDeviceRunInputs(
        schedule: OnDeviceSchedule.whileCharging,
        isCharging: false,
        batteryPercent: battery,
        pendingAudio: const Duration(minutes: 5),
        now: DateTime.utc(2026, 11, 28),
        isForeground: foreground));
    expect(decide(battery: 80), const OnDeviceRunDecision.run(OnDeviceRunReason.foreground));
    expect(decide(battery: 5), const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow));
    expect(decide(battery: 80, foreground: false), const OnDeviceRunDecision.wait(OnDeviceRunReason.waitingForCharger));
  });

  test('the runner kill switch is on when absent or unreadable and off only when set', () async {
    final now = DateTime.utc(2026, 11, 28);
    Future<bool> reload() async => true;
    expect(await OnDeviceRunnerGate.enabled(readFlag: (_) async => false, reloadFlags: reload, now: () => now), isTrue);
    expect(await OnDeviceRunnerGate.enabled(readFlag: (_) async => true, reloadFlags: reload, now: () => now), isFalse);
    // An unreadable flag keeps the last answer this phone saw (the kill stays in force offline).
    expect(
        await OnDeviceRunnerGate.enabled(readFlag: (_) async => throw StateError('offline'), now: () => now), isFalse);
    OnDeviceRunnerGate.debugReset();
    expect(
        await OnDeviceRunnerGate.enabled(readFlag: (_) async => throw StateError('offline'), now: () => now), isTrue);
  });
}
