import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/connectors/limitless_realtime_health.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/capture/capture_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';
import '../../support/refactor_flag_adapter.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final hardwareMuteWrites = <bool>[];
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
  Future<void> connect() async {
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  }

  Future<void> elapse(Duration duration) async {
    await world.elapse(duration);
    await world.controller.pendingSourceSwitch;
    await world.settle();
  }

  // Historical state from #20837. New capture never creates this marker;
  // recovery must remain covered for users upgrading from that version.
  Future<void> legacySilencePause() async {
    await world.controller.pauseCapture();
    await SharedPreferencesUtil().saveBool('uplinkSilencePaused', true);
    await world.settle();
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('tiered_capture_');
    hardwareMuteWrites.clear();
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      pendantCodec: BleAudioCodec.opus,
      deviceMuteWriter: (id, muted) async => hardwareMuteWrites.add(muted),
    );
    await connect();
  });
  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  test('silence beyond the deadline keeps every packet flowing through BLE, socket and WAL', () async {
    world.uploads.failAll = true;
    final socket = world.socket!;
    final recording = world.controller.activeRecordingId;
    for (var second = 0; second < 300; second++) {
      world.deviceConnection!.emitAudio(value: second & 255);
      await elapse(const Duration(seconds: 1));
    }
    expect(world.controller.silencePaused, false);
    expect(world.controller.isPaused, false);
    expect(hardwareMuteWrites, isEmpty);
    expect(world.controller.activeRecordingId, recording);
    expect(socket.closeCalls, 0);
    expect(socket.sentBinary, hasLength(300));
    for (var i = 0; i < 300; i++) {
      expect(socket.sentBinary[i], List<int>.filled(80, i & 255));
    }
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
    expect(world.processCalls, 0);
    final retained = await world.wal.syncs.phone.getAllWals();
    expect(retained.fold<int>(0, (count, wal) => count + wal.totalFrames), 300);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    await connect();
    expect(world.controller.isPaused, false);
    expect(world.socket!.status, PureSocketStatus.connected);
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
  });

  test('Android Limitless watchdog keeps the admitted owner through metadata and unchanged settings refreshes',
      () async {
    await setRefactorFlags({'android-custom-live-audio-recovery-kill': false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    final admitted = connection.captureIsCurrent;
    final recording = world.controller.activeRecordingId;
    expect(recording, isNotNull);
    expect(admitted?.call(), isTrue);

    // Mirrors the second update in DeviceProvider._onDeviceConnected after
    // getDeviceInfo: same capture and physical link, fresh device metadata.
    world.controller.updateRecordingDevice(device.copyWith(firmwareRevision: '1.0.0'));
    await world.settle();

    expect(world.controller.activeRecordingId, recording);
    expect(connection.captureIsCurrent, same(admitted));
    expect(admitted?.call(), isTrue);

    await world.controller.onTranscriptionSettingsChanged();
    expect(world.controller.activeRecordingId, recording);
    expect(connection.captureIsCurrent, same(admitted));

    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://changed-stt.example.test'),
    );
    expect(admitted?.call(), isTrue);
    await world.controller.onTranscriptionSettingsChanged();
    expect(connection.captureIsCurrent, same(admitted));
    expect(connection.watchStarts, 1);

    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.custom, url: 'wss://other-stt.example.test'),
    );
    expect(admitted?.call(), isFalse);
    await world.controller.onTranscriptionSettingsChanged();
    expect(connection.captureIsCurrent, isNull);
    expect(connection.stopCalls, greaterThan(0));

    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://returned-stt.example.test'),
    );
    await world.controller.onTranscriptionSettingsChanged();
    final replacement = connection.captureIsCurrent;
    expect(replacement, isNot(same(admitted)));
    expect(replacement?.call(), isTrue);
    expect(connection.watchStarts, 2);

    SharedPreferencesUtil().uid = 'replaced-test-owner';
    expect(replacement?.call(), isFalse);
    await world.controller.onTranscriptionSettingsChanged();
    expect(connection.captureIsCurrent, isNull);
  });

  test('an identity settling during Custom Live capture refreshes the retained watch', () async {
    AnalyticsManager.resetForTesting();
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-identity', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.watchStarts, 1);

    await setRefactorFlags({'android-custom-live-audio-recovery-kill': false});
    await world.settle();
    expect(connection.watchStarts, 2);
    expect(connection.captureIsCurrent?.call(), isTrue);
  });

  test('a successful missing-flag lookup enables recovery without a delay', () async {
    AnalyticsManager.resetForTesting();
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-retry', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.watchStarts, 1);

    await setRefactorFlags({});
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(connection.watchStarts, 2);
  });

  test('a new Custom Live recording refreshes the kill switch for the same identity', () async {
    final adapter = await setRefactorFlags({'android-custom-live-audio-recovery-kill': false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-flag-refresh', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.watchStarts, 1);
    expect(connection.captureIsCurrent?.call(), isTrue);

    await world.controller.stopStreamDeviceRecording();
    await world.settle();
    adapter.flags['android-custom-live-audio-recovery-kill'] = true;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    expect(connection.captureIsCurrent, isNull);
    expect(connection.stopCalls, greaterThan(0));
  });

  test('a failed refresh cannot reuse a stale cached false kill switch', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-stale-flag', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);

    await world.controller.stopStreamDeviceRecording();
    await world.settle();
    adapter.flags[flag] = true;
    adapter.reloadFailuresRemaining = 1;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    expect(connection.captureIsCurrent, isNull, reason: 'a failed refresh cannot trust cached false');
    final readsBeforeRetry = adapter.reloadCount;
    await world.elapse(const Duration(seconds: 5));
    await world.settle();
    expect(connection.captureIsCurrent, isNull, reason: 'the successful retry observes the enabled kill switch');
    expect(adapter.reloadCount, greaterThan(readsBeforeRetry), reason: 'the bounded retry must actually fetch flags');
    expect(adapter.cachedFlags[flag], isTrue, reason: 'the retry must cache the enabled kill switch');
  });

  test('two failed kill-switch fetches restore the watch and a later gate pass retries', () async {
    AnalyticsManager.resetForTesting();
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-fetch-retry', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.watchStarts, 1);

    final adapter = await setRefactorFlags({}, reloadFailures: 2);
    await world.settle();
    expect(connection.captureIsCurrent, isNull, reason: 'a failed flag fetch keeps recovery gated');

    await world.elapse(const Duration(seconds: 5));
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue,
        reason: 'bounded fetch failures must not leave the watch torn down');
    expect(connection.watchStarts, 2);

    final readsBeforeGatePass = adapter.reloadCount;
    final watchStartsBeforeGatePass = connection.watchStarts;
    adapter.flags['android-custom-live-audio-recovery-kill'] = false;
    adapter.reloadFailuresRemaining = 1;
    connection.stopCustomLiveAudioWatch();
    await world.controller.onTranscriptionSettingsChanged();
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(adapter.reloadCount, readsBeforeGatePass + 1, reason: 'the later gate pass must retry the flag read');
    expect(connection.watchStarts, greaterThan(watchStartsBeforeGatePass),
        reason: 'the eligible gate pass restores the watch');
  });

  test('a periodic refresh applies the kill switch during a long capture', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-periodic-flag', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);

    await world.elapse(const Duration(minutes: 4, seconds: 59));
    adapter.flags[flag] = true;
    await world.elapse(const Duration(seconds: 1));
    await world.settle();

    expect(connection.captureIsCurrent, isNull);
    expect(connection.stopCalls, greaterThan(0));
  });

  test('tracking consent opt-out fails open and resumed consent keeps the kill cadence', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: true});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-consent-flag', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.captureIsCurrent, isNull, reason: 'the confirmed kill switch closes the watch');
    expect(adapter.reloadCount, 1);

    AnalyticsManager().optOutTracking();
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue, reason: 'without consent the flag context fails open');
    await world.elapse(const Duration(minutes: 5));
    expect(adapter.reloadCount, 1, reason: 'opt-out does not keep issuing authenticated flag reads');

    adapter.flags[flag] = false;
    AnalyticsManager().optInTracking();
    await world.settle();
    expect(adapter.reloadCount, 2);
    expect(connection.captureIsCurrent?.call(), isTrue);

    final readsBeforePeriodicRefresh = adapter.reloadCount;
    await world.elapse(const Duration(minutes: 4, seconds: 59));
    adapter.flags[flag] = true;
    await world.elapse(const Duration(seconds: 1));
    await world.settle();
    expect(adapter.reloadCount, greaterThan(readsBeforePeriodicRefresh),
        reason: 'the five-minute kill refresh resumes after consent returns');
    expect(connection.captureIsCurrent, isNull);
  });

  test('periodic kill refresh stays armed while Custom Live is temporarily paused', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device =
        BtDevice(id: 'limitless-paused-periodic-flag', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);

    await world.controller.pauseCapture();
    await world.settle();
    expect(connection.captureIsCurrent, isNull);
    await world.elapse(const Duration(minutes: 5));

    adapter.flags[flag] = true;
    await world.controller.resumeCapture();
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue, reason: 'the paused read still observes the prior safe value');

    await world.elapse(const Duration(minutes: 5));
    expect(connection.captureIsCurrent, isNull, reason: 'the next scheduled read applies the kill switch');
  });

  test('leaving Custom Live cancels periodic flag reads and returning re-arms them', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-provider-switch', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(adapter.reloadCount, 1);
    expect(connection.captureIsCurrent?.call(), isTrue);

    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.custom, url: 'wss://other-stt.example.test'),
    );
    await world.controller.onTranscriptionSettingsChanged();
    await world.settle();
    expect(connection.captureIsCurrent, isNull);

    await world.elapse(const Duration(minutes: 5, seconds: 1));
    expect(adapter.reloadCount, 1, reason: 'a non-Custom-Live provider must not keep refreshing the kill flag');

    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://returned-stt.example.test'),
    );
    await world.controller.onTranscriptionSettingsChanged();
    await world.settle();
    expect(adapter.reloadCount, 2, reason: 'returning to Custom Live reads the flag and restarts cadence');

    final readsBeforePeriodicRefresh = adapter.reloadCount;
    await world.elapse(const Duration(minutes: 4, seconds: 59));
    adapter.flags[flag] = true;
    await world.elapse(const Duration(seconds: 1));
    await world.settle();
    expect(adapter.reloadCount, greaterThan(readsBeforePeriodicRefresh));
    expect(connection.captureIsCurrent, isNull);
  });

  test('a missing kill stays enabled through failed periodic reads and a later kill is applied', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device =
        BtDevice(id: 'limitless-missing-periodic-flag', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(connection.watchStarts, 1);

    adapter.reloadFailuresRemaining = 1;
    await world.elapse(const Duration(minutes: 5, seconds: 1));
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(connection.watchStarts, 1, reason: 'a failed refresh keeps the admitted watch installed');

    adapter.flags[flag] = true;
    adapter.reloadFailuresRemaining = 2;
    await world.elapse(const Duration(minutes: 5));
    await world.elapse(const Duration(seconds: 1));
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(connection.watchStarts, 1, reason: 'two failed refreshes leave confirmed missing-key recovery active');

    await world.elapse(const Duration(minutes: 5));
    expect(connection.captureIsCurrent, isNull, reason: 'the bounded five-minute retry observes the kill switch');
  });

  test('a confirmed-disabled kill keeps recovery active through a failed periodic read', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(
      id: 'limitless-confirmed-disabled-periodic-flag',
      name: 'Limitless',
      type: DeviceType.limitless,
      rssi: -40,
    );
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(connection.watchStarts, 1);

    adapter.reloadFailuresRemaining = 1;
    await world.elapse(const Duration(minutes: 5, seconds: 1));
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue);
    expect(connection.watchStarts, 1, reason: 'a failed refresh preserves the healthy watch');

    adapter.flags[flag] = true;
    await world.elapse(const Duration(seconds: 1));
    await world.settle();
    expect(connection.captureIsCurrent, isNull, reason: 'the successful bounded retry applies the later kill');
  });

  test('a confirmed kill remains active through a failed periodic read', () async {
    const flag = 'android-custom-live-audio-recovery-kill';
    final adapter = await setRefactorFlags({flag: true});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(
        id: 'limitless-confirmed-kill-periodic-flag', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.watchStarts, 0);
    expect(connection.captureIsCurrent, isNull);

    adapter.reloadFailuresRemaining = 1;
    adapter.cachedFlags[flag] = false;
    await world.elapse(const Duration(minutes: 5));
    await world.settle();
    expect(connection.captureIsCurrent, isNull, reason: 'a failed refresh cannot clear the confirmed kill');

    adapter.flags[flag] = false;
    await world.elapse(const Duration(seconds: 1));
    await world.settle();
    expect(connection.captureIsCurrent?.call(), isTrue, reason: 'the successful bounded retry can clear the kill');
    expect(connection.watchStarts, 1);
  });

  test('a new capture restores recovery after two bounded flag-read failures', () async {
    await setRefactorFlags({}, reloadFailures: 2);
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device =
        BtDevice(id: 'limitless-first-read-retries', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    expect(connection.captureIsCurrent, isNull, reason: 'the unresolved release kill switch is fail-closed');
    await world.elapse(const Duration(seconds: 1));

    expect(connection.captureIsCurrent?.call(), isTrue, reason: 'the first-read retry chain restores recovery quickly');
    expect(connection.watchStarts, 1);
  });

  test('resolved kill switch prevents a Custom Live watch from being installed', () async {
    await setRefactorFlags({'android-custom-live-audio-recovery-kill': true});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-killed', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    expect(connection.captureIsCurrent, isNull);
    expect(connection.watchStarts, 0);
    expect(connection.stopCalls, greaterThan(0));
  });

  test('Limitless reactivation is gated while the transcription socket is disconnected', () async {
    await setRefactorFlags({'android-custom-live-audio-recovery-kill': false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-socket', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    expect(connection.reactivationIsCurrent?.call(), isTrue);
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    expect(connection.reactivationIsCurrent?.call(), isFalse);
  });

  test('Limitless recovery watch restarts when the socket connects after an initial outage', () async {
    await setRefactorFlags({'android-custom-live-audio-recovery-kill': false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    world.setConnected(false);
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-initial-outage', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();

    expect(world.controller.recordingState, RecordingState.deviceRecord);
    expect(connection.reactivationIsCurrent?.call(), isFalse);
    expect(connection.watchRestarts, isNot(contains(true)));
    final disconnectedReactivationCheck = connection.reactivationIsCurrent;

    world.setConnected(true);
    await world.controller.reconnectActiveCaptureForTesting();
    await world.settle();

    expect(connection.watchRestarts, contains(true));
    expect(connection.watchStarts, 2, reason: 'the restart replaces the existing recovery binding');
    expect(connection.reactivationIsCurrent, isNot(same(disconnectedReactivationCheck)));
    expect(connection.reactivationIsCurrent?.call(), isTrue);
  });

  test('Limitless recovery watch restarts after a socket error and actual reconnection', () async {
    await setRefactorFlags({'android-custom-live-audio-recovery-kill': false});
    addTearDown(AnalyticsManager.resetForTesting);
    world.controller.updateRecordingDevice(null);
    await world.settle();
    SharedPreferencesUtil().uid = 'capture-test-owner';
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.customLive, url: 'wss://local-stt.example.test'),
    );
    final device = BtDevice(id: 'limitless-socket-error', name: 'Limitless', type: DeviceType.limitless, rssi: -40);
    final connection = _WatchedLimitlessConnection();
    world.deviceConnection = connection;
    await world.controller.streamDeviceRecording(device: device);
    await world.settle();
    expect(connection.reactivationIsCurrent?.call(), isTrue);

    world.setConnected(false);
    world.socket!.emitError(StateError('scripted socket failure'));
    await world.settle();
    expect(connection.reactivationIsCurrent?.call(), isFalse);
    expect(connection.watchRestarts, isNot(contains(true)));

    world.setConnected(true);
    await world.elapse(const Duration(seconds: 2));
    await world.settle();
    expect(connection.watchRestarts, contains(true));
    expect(connection.watchStarts, 2);
    expect(connection.reactivationIsCurrent?.call(), isTrue);
  });

  test('queued silence event cannot change ownership or run pause effects', () {
    final state = CaptureCoordinatorState.idle().copyWith(phase: CapturePhase.pendantLive);
    final transition = transitionCapture(
        state,
        const UplinkSilenceElapsed(null),
        CaptureEnvironment(
            policyMuted: false,
            paused: false,
            batchModeEnabled: false,
            batchModeSuspendedForOnboarding: false,
            deviceSupportsTranscribeLater: false,
            networkConnected: true,
            signedIn: () => true,
            phoneMicSupportsBatch: false,
            transcriptReady: true,
            socketConnected: true,
            deviceServiceReady: true,
            callActive: false,
            deviceRecording: true,
            micCapturing: false,
            uplinkSilenceExpired: true));
    expect(transition.state, same(state));
    expect(transition.effects, isEmpty);
  });

  test('upgrade clears a persisted automatic pause, while explicit mute still survives restart', () async {
    await legacySilencePause();
    world.disposeController();
    await world.reconstructProcess();
    expect(world.controller.silencePaused, false);
    expect(world.controller.isPaused, false);
    await connect();
    expect(world.deviceConnection!.openAudioSubscriptions, 1);
    await world.controller.pauseCapture();
    world.disposeController();
    await world.reconstructProcess();
    expect(world.controller.isPaused, true);
    expect(world.controller.silencePaused, false);
  });

  test('shared WAL/socket payload owns bytes before the BLE producer reuses its buffer', () async {
    final raw = [1, 0, 0, ...List<int>.generate(80, (i) => i)];
    world.deviceConnection!.emitRawAudio(raw);
    final saved = world.wal.syncs.phone.testFrames.last;
    expect(identical(saved.payload, world.socket!.sentBinary.last), true);
    raw.fillRange(0, raw.length, 255);
    expect(saved.payload, List<int>.generate(80, (i) => i));
    expect(world.socket!.sentBinary.last, saved.payload);
    await world.wal.syncs.phone.finalizeCurrentSession();
    final wals = await world.wal.syncs.phone.getAllWals();
    final disk = wals.where((w) => w.storage == WalStorage.disk).single;
    final bytes = await File('${directory.path}/${disk.filePath}').readAsBytes();
    expect(bytes, [80, 0, 0, 0, ...List<int>.generate(80, (i) => i)]);
  });

  for (final foreground in [false, true]) {
    for (final control in ['resume', 'doubleTap', 'liveActivity']) {
      test('resume during reconnect drain restores uplink (foreground=$foreground, control=$control)', () async {
        await legacySilencePause();
        expect(world.controller.silencePaused, true);
        expect(world.controller.keepAliveScheduledForTesting, false);
        final socketCount = world.sockets.length;
        final draining = Completer<void>();
        final release = Completer<void>();
        final coordinator = RecordingTransferCoordinator(
          reconcile: () async {},
          discover: () async {},
          refreshPending: () async {},
          drain: () async {
            draining.complete();
            await release.future;
            return const RecordingTransferDrainResult.skipped();
          },
          autoUploadEnabled: () => true,
        )..setForeground(foreground);
        final wake = coordinator.wake(WakeTrigger.periodic);
        await draining.future;
        Future<void>? resume;
        try {
          expect(SyncWakeScope.syncOnly, true);
          if (control == 'doubleTap') {
            SharedPreferencesUtil().doubleTapAction = 1;
            world.controller.handleButtonEventForTesting(pendant.id, 2);
          } else if (control == 'liveActivity') {
            resume = world.controller.performSystemSurfaceAction(
              'resume',
              recordingId: world.controller.activeRecordingId!,
              conversationRevision: world.controller.systemSurfaceConversationRevision,
            );
          } else {
            resume = world.controller.resumeCapture();
          }
          await world.settle();
          expect(world.controller.silencePaused, true);
          expect(world.controller.isPaused, true);
          expect(world.controller.keepAliveScheduledForTesting, false);
          expect(world.sockets.length, socketCount);
          expect(world.deviceConnection!.openAudioSubscriptions, 0);
        } finally {
          release.complete();
          await wake;
          coordinator.dispose();
        }
        await resume;
        await world.settle();
        await world.controller.pendingSourceSwitch;
        expect(world.controller.silencePaused, false);
        expect(world.controller.isPaused, false);
        expect(world.sockets.length, socketCount + 1);
        expect(world.socket!.status, PureSocketStatus.connected);
        expect(world.deviceConnection!.openAudioSubscriptions, 1);
        expect(world.controller.keepAliveScheduledForTesting, true);
      });
    }
  }

  test('changing silence timeout and speech cannot arm an automatic pause', () async {
    SharedPreferencesUtil().conversationSilenceDuration = 300;
    await connect();
    await elapse(const Duration(seconds: 200));
    world.controller.onSegmentReceived([
      TranscriptSegment(
          id: 'speech',
          text: 'hello',
          speaker: 'SPEAKER_0',
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: []),
    ]);
    await world.settle();
    await elapse(const Duration(seconds: 200));
    expect(world.controller.isPaused, false);
    world.deviceConnection!.emitAudio();
    await elapse(const Duration(seconds: 100));
    expect(world.controller.silencePaused, false);
  });

  for (final charging in [false, true]) {
    test('${charging ? 'charging' : 'foreground'} resumes silence as a fresh session but respects manual mute',
        () async {
      await legacySilencePause();
      final recording = world.controller.activeRecordingId;
      final sockets = world.sockets.length;
      if (charging) {
        world.controller.onChargingStarted();
      } else {
        world.controller.onAppResumed();
      }
      await world.controller.pendingSourceSwitch;
      await world.settle();
      expect(world.controller.isPaused, false);
      expect(world.controller.silencePaused, false);
      expect(world.controller.activeRecordingId, isNot(recording));
      expect(world.sockets.length, sockets + 1);
      expect(world.deviceConnection!.openAudioSubscriptions, 1);
      await world.controller.pauseCapture();
      world.controller.onChargingStarted();
      world.controller.onAppResumed();
      await world.settle();
      expect(world.controller.isPaused, true);
      expect(world.sockets.length, sockets + 1);
    });
  }

  test('manual pause takes over silence reason and prevents auto resume', () async {
    await legacySilencePause();
    hardwareMuteWrites.clear();
    await world.controller.pauseCapture();
    expect(world.controller.silencePaused, false);
    expect(hardwareMuteWrites, [true]);
    await world.controller.resumeAfterSilence();
    expect(world.controller.isPaused, true);
  });

  test('late transcript delivery cannot reopen a manually paused capture', () async {
    await world.controller.pauseCapture();
    await world.controller.pendingSourceSwitch;
    world.controller.onSegmentReceived([
      TranscriptSegment(
          id: 'late',
          text: 'still speaking',
          speaker: null,
          isUser: false,
          personId: null,
          start: 0,
          end: 1,
          translations: []),
    ]);
    await world.settle();
    expect(world.controller.isPaused, true);
  });
}

class _WatchedLimitlessConnection extends ScriptedDeviceConnection implements LimitlessDeviceConnection {
  bool Function()? captureIsCurrent;
  bool Function()? reactivationIsCurrent;
  int watchStarts = 0;
  int stopCalls = 0;
  final List<bool> watchRestarts = [];

  @override
  bool get supportsCustomLiveRecovery => true;

  @override
  Future<Map<String, String>> getDeviceInfo() async => {};

  @override
  void watchCustomLiveAudio({
    required bool Function() captureIsCurrent,
    bool Function()? reactivationIsCurrent,
    required void Function() onEnabled,
    required void Function(LimitlessRealtimeHealthOutcome) report,
    bool restart = false,
  }) {
    watchRestarts.add(restart);
    if (!restart && (this.captureIsCurrent?.call() ?? false)) return;
    this.captureIsCurrent = captureIsCurrent;
    this.reactivationIsCurrent = reactivationIsCurrent;
    watchStarts++;
    onEnabled();
  }

  @override
  void stopCustomLiveAudioWatch() {
    stopCalls++;
    captureIsCurrent = null;
    reactivationIsCurrent = null;
  }
}
