import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/capture/capture_replay_world.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('a stop followed by a late conversation produces no empty-recording message', () async {
    final dir = await Directory.systemTemp.createTemp('empty-recording-stop-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final actions = _ExplainingActions();
    final adapter = _RecordingAdapter();
    addTearDown(() async {
      await world.dispose();
      await dir.delete(recursive: true);
    });
    world.controller.updateExternalActions(actions);
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    await world.stopLiveCapture();
    await _flush();

    expect(actions.emptyExplanations, 0);
    expect(_produced(adapter), isEmpty);

    world.controller.onMessageEventReceived(
      ConversationEvent(memory: _conversation(id: 'late'), messages: const []),
    );
    await world.settle();
    await _flush();

    expect(actions.emptyExplanations, 0);
    expect(_produced(adapter), isEmpty);
  });

  test('a 404 after the conversation was finalized produces no message', () async {
    final dir = await Directory.systemTemp.createTemp('empty-recording-404-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final actions = _ExplainingActions();
    final adapter = _RecordingAdapter();
    addTearDown(() async {
      await world.dispose();
      await dir.delete(recursive: true);
    });
    world.controller.updateExternalActions(actions);
    world.processOutcome = () async => const InProgressProcessOutcome(absence: ProcessAbsence.notFound);
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    world.controller.onMessageEventReceived(
      ConversationEvent(memory: _conversation(id: 'finalized'), messages: const []),
    );
    await world.settle();

    final pending = world.controller.forceProcessingCurrentConversation();
    await world.settle();
    await pending;
    await world.elapse(Duration.zero);
    await _flush();

    expect(actions.emptyExplanations, 0);
    expect(_produced(adapter), isEmpty);
  });

  test('an Apple Watch session is counted as watch when the process body is empty', () async {
    final actions = _ExplainingActions();
    final adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final provider = _provider(
      actions: actions,
      outcome: () async => const InProgressProcessOutcome(absence: ProcessAbsence.emptyBody),
    );
    addTearDown(provider.dispose);

    provider.updateRecordingDevice(BtDevice(name: 'Watch', id: 'watch-1', type: DeviceType.appleWatch, rssi: -40));
    await _flush();
    final pending = provider.forceProcessingCurrentConversation();
    await pending;
    await _flush();

    expect(actions.emptyExplanations, 1);
    expect(_produced(adapter), [
      {'source': 'watch', 'reason': 'empty_deleted'},
    ]);
  });

  test('a discarded-only explanation that was already shown still emits once', () async {
    final actions = _ExplainingActions()..claimResult = DiscardedOnlyClaim.alreadyShown;
    final adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final provider = _provider(
      actions: actions,
      outcome: () async => const InProgressProcessOutcome(absence: ProcessAbsence.transport),
    );
    addTearDown(provider.dispose);

    provider.onMessageEventReceived(
      ConversationEvent(memory: _conversation(id: 'gone', discarded: true), messages: const []),
    );
    await _flush();

    expect(actions.emptyExplanations, 0);
    expect(actions.claims, [DiscardedOnlyClaim.alreadyShown]);
    expect(_produced(adapter), [
      {'source': 'omi', 'reason': 'discarded'},
    ]);
  });

  test('a transport failure emits null_result without the too-short explanation', () async {
    final actions = _ExplainingActions();
    final adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final provider = _provider(
      actions: actions,
      outcome: () async => const InProgressProcessOutcome(absence: ProcessAbsence.transport),
    );
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();
    await pending;
    await _flush();

    expect(actions.emptyExplanations, 0);
    expect(_produced(adapter), [
      {'source': 'omi', 'reason': 'null_result'},
    ]);
  });
}

Future<void> _flush() async {
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}

List<Map<String, Object>> _produced(_RecordingAdapter adapter) {
  return adapter.events
      .where((event) => event.$1 == 'Recording Produced No Conversation')
      .map((event) => {'source': event.$2['source']!, 'reason': event.$2['reason']!})
      .toList();
}

ServerConversation _conversation({required String id, bool discarded = false}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime.utc(2026, 1, 1),
    structured: Structured('Kept', ''),
    status: ConversationStatus.completed,
    discarded: discarded,
    source: discarded ? null : ConversationSource.phone,
  );
}

class _ExplainingActions extends NoopCaptureExternalActions {
  int emptyExplanations = 0;
  final claims = <DiscardedOnlyClaim>[];
  DiscardedOnlyClaim claimResult = DiscardedOnlyClaim.notDiscardedOnly;

  @override
  void showEmptyRecordingExplanation() => emptyExplanations++;

  @override
  DiscardedOnlyClaim claimDiscardedOnlyExplanation() {
    claims.add(claimResult);
    return claimResult;
  }
}

class _PhoneSync {
  Future<void> finalizeCurrentSession() async {}

  Future<void> stampConversationId(int start, String id, {String? recordingSessionId}) async {}

  int getInFlightSeconds() => 0;

  List<dynamic> getSessionUnsyncedWals(int start) => const [];

  void setSessionGeolocation(Object? value) {}

  void prepareConversationStamp(Object? id) {}
}

class _Syncs {
  _Syncs(this.phone);
  final _PhoneSync phone;
}

class _Wal implements IWalService {
  final phone = _PhoneSync();

  @override
  dynamic getSyncs() => _Syncs(phone);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

CaptureProvider _provider({
  required _ExplainingActions actions,
  required Future<InProgressProcessOutcome> Function() outcome,
}) {
  return CaptureProvider(
    externalActions: actions,
    walService: _Wal(),
    processInProgressOutcome: outcome,
    connectivity: CaptureConnectivityBoundary(
      initiallyConnected: true,
      changes: const Stream.empty(),
      isConnected: () => true,
    ),
    bleListeners: _NoopBle(),
    inProgressConversationLoader: () async {},
    localSegmentStore: LocalSegmentStore.disabled(),
  );
}

class _RecordingAdapter implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add((eventName, Map<String, Object>.of(properties ?? const {})));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
