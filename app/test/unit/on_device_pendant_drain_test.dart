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
import 'package:omi/services/wals/sync_job_poller.dart';
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
Wal drained(String file, int timerStart, {int seconds = 1, String device = 'omi'}) => Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.pcm16,
    seconds: seconds,
    status: WalStatus.miss,
    storage: WalStorage.disk,
    filePath: file,
    device: device,
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
    DrainedAudioCustody.debugReset();
    SyncJobPoller.instance.resetForTesting();
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
    final runner = OnDeviceRunner(
        sync: sync,
        controller: controller,
        publish: (row) => order.add(row.id),
        cloudBaseUrl: 'http://127.0.0.1:1/',
        transcribeChunk: (_, __) async {
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
    // An hour apart, so two conversations; the newer recording's is published first.
    expect(order, ['cloud-ondevice-${newer.id}', 'cloud-ondevice-${older.id}']);
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

  test('the runner kill switch changes only on an authoritative answer and persists a kill', () async {
    final now = DateTime.utc(2026, 11, 28);
    Future<bool> reload() async => true;
    Future<bool> read(bool? answer) =>
        OnDeviceRunnerGate.enabled(readFlag: (_) async => answer, reloadFlags: reload, now: () => now);
    expect(await read(false), isTrue);
    expect(await read(true), isFalse);
    // No settled identity, tracking off or offline: the kill this phone saw stays in force.
    expect(await read(null), isFalse);
    expect(
        await OnDeviceRunnerGate.enabled(readFlag: (_) async => throw StateError('offline'), now: () => now), isFalse);
    // A new process (the Android background worker) starts from the persisted kill.
    OnDeviceRunnerGate.debugReset();
    expect(await read(null), isFalse);
    expect(await read(false), isTrue);
    OnDeviceRunnerGate.debugReset();
    expect(await read(null), isTrue);
  });

  test('contiguous drained chunks form one conversation, split by gaps, span and device', () {
    Wal chunk(String file, int start, {String device = 'omi'}) => drained(file, start, seconds: 60, device: device);
    final a = chunk('a', 1000), b = chunk('b', 1060), c = chunk('c', 1150);
    final far = chunk('d', 5000);
    final other = chunk('e', 1210, device: 'other');
    final phone = Wal(
        timerStart: 900,
        codec: BleAudioCodec.pcm16,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'phone',
        onDeviceOnly: true);
    final groups = groupOnDeviceWork([far, c, phone, a, other, b]);
    expect(groups.map((g) => g.map((w) => w.filePath ?? 'phone').toList()).toList(), [
      ['d'],
      ['e'],
      ['a', 'b', 'c'],
      ['phone'],
    ]);
    final long = [for (var i = 0; i < 61; i++) chunk('l$i', 10000 + i * 60)];
    expect(groupOnDeviceWork(long).map((g) => g.length).toList()..sort(), [1, 60]);
  });

  OnDeviceRunner runnerFor(LocalWalSyncImpl sync, OnDeviceTranscriptionController controller,
          {required List<String> posts, int status = 200, Map<String, String> headers = const {}}) =>
      OnDeviceRunner(
          sync: sync,
          controller: controller,
          publish: (_) {},
          cloudBaseUrl: 'http://127.0.0.1:1/',
          transcribeChunk: (_, __) async => const OnDeviceBatchResult(
              engine: 'synthetic', text: 'A synthetic test.', words: [OnDeviceWord('A synthetic test.', 0, 1)]),
          send: (request) async {
            if (request.method == 'POST') {
              final body = jsonDecode(request.body) as Map<String, dynamic>;
              posts.add(body['client_session_id'] as String);
              if (status != 200) return http.Response('{}', status, headers: headers);
              return http.Response(jsonEncode({'id': 'cloud-${body['client_session_id']}'}), 200);
            }
            final id = Uri.parse(request.url.toString()).pathSegments.last;
            return http.Response(
                jsonEncode(ServerConversation(id: id, createdAt: DateTime.utc(2026), structured: Structured('t', 'o'))
                    .toJson()),
                200);
          });

  test('a drained backlog uploads one conversation per contiguous span, saved and released together', () async {
    await selectOnDevice();
    final wals = [
      for (var i = 0; i < 3; i++) drained('c$i.bin', 1700000000 + i * 60, seconds: 60),
    ];
    for (final wal in wals) {
      recording(wal.filePath!);
    }
    var saves = 0;
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async => saves++)..testWals = wals;
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
      ..debugActivate(settings: const OnDeviceSettings(enabled: false));
    final posts = <String>[];
    final runner = runnerFor(sync, controller, posts: posts);
    await runner.run(transcribeNow: true);
    expect(posts, ['ondevice-${wals.first.id}-n3']);
    final id = wals.first.onDeviceConversation!['id'];
    for (final wal in wals) {
      expect(wal.onDeviceConversation!['id'], id);
      expect(wal.status, WalStatus.synced, reason: 'transcript and retention land in one save');
    }
    expect(saves, 1);
    runner.dispose();
    controller.dispose();
  });

  test('a rate-limited upload keeps the audio and pauses the runner until Retry-After', () async {
    await selectOnDevice();
    recording('a.bin');
    final wal = drained('a.bin', 1700000000);
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {})..testWals = [wal];
    final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel(), power: FakePhonePowerSource())
      ..debugActivate(settings: const OnDeviceSettings(enabled: false));
    final posts = <String>[];
    var clock = DateTime.utc(2026, 11, 28, 12);
    final runner = runnerFor(sync, controller, posts: posts, status: 429, headers: {'retry-after': '600'})
      ..now = () => clock;
    await runner.run(transcribeNow: true);
    expect(runner.lastError, 'rate_limited');
    expect(wal.status, WalStatus.miss);
    expect(wal.onDeviceOnly, isTrue);
    await runner.run(transcribeNow: true);
    expect(posts, hasLength(1), reason: 'no retry inside the window');
    clock = clock.add(const Duration(minutes: 11));
    await runner.run(transcribeNow: true);
    expect(posts, hasLength(2));
    runner.dispose();
    controller.dispose();
  });

  test('a manual Sync never releases audio the runner has claimed', () async {
    final claimed = drained('a.bin', 1700000000);
    final free = drained('b.bin', 1700000100);
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (_) async {})..testWals = [claimed, free];
    sync.claimForOnDevice([claimed]);
    expect(await sync.releaseDrainedDeviceAudioForUpload(), 1);
    expect(claimed.onDeviceOnly, isTrue);
    expect(free.onDeviceOnly, isFalse);
    sync.unclaimForOnDevice([claimed]);
    expect(await sync.releaseDrainedDeviceAudioForUpload(), 1);
  });

  test('chunks drained soon after a confirmed cloud Sync are not phone-only', () async {
    await selectOnDevice();
    var clock = DateTime.utc(2026, 11, 28, 12);
    DrainedAudioCustody.now = () => clock;
    expect(DrainedAudioCustody.phoneOnlyAtPersist(), isTrue);
    DrainedAudioCustody.confirmCloudSync();
    expect(DrainedAudioCustody.phoneOnlyAtPersist(), isFalse);
    clock = clock.add(DrainedAudioCustody.cloudSyncWindow);
    expect(DrainedAudioCustody.phoneOnlyAtPersist(), isTrue);
  });

  test('an allowance-held reply records the renewal date and a later reply clears it', () async {
    var now = DateTime.utc(2026, 11, 28, 12);
    var status =
        SyncJobStatusResponse(jobId: 'job-1', status: 'queued', reasonCode: 'allowance_held', retryAfter: 147200);
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async => SyncJobFetch(SyncJobFetchOutcome.ok, status));
    recording('a.bin');
    final wal = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.pcm16,
        seconds: 60,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'a.bin')
      ..jobId = 'job-1';
    sync.testWals = [wal];
    SyncJobPoller.instance.resetForTesting(clock: () => now);
    await sync.reconcileUploadedWals();
    expect(wal.allowanceHeldUntil, now.millisecondsSinceEpoch ~/ 1000 + 147200);
    status = SyncJobStatusResponse(jobId: 'job-1', status: 'processing');
    now = now.add(const Duration(minutes: 30));
    await sync.reconcileUploadedWals();
    expect(wal.allowanceHeldUntil, 0);
    await sync.stop();
  });
}
