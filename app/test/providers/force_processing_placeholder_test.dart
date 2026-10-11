import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

import '../support/crashlytics_recorder.dart';

class _RecordingActions extends NoopCaptureExternalActions {
  final processing = <ServerConversation>[];
  final upserted = <ServerConversation>[];

  @override
  void addProcessingConversation(ServerConversation conversation) {
    processing.removeWhere((item) => item.id == conversation.id);
    processing.add(conversation);
  }

  @override
  void removeProcessingConversation(String conversationId) {
    processing.removeWhere((item) => item.id == conversationId);
  }

  @override
  void upsertConversation(ServerConversation conversation) {
    upserted.add(conversation);
  }
}

class _GatedPhoneSync {
  _GatedPhoneSync(Completer<void> finalizeGate, {this.stampError, List<Completer<void>> laterFinalizeGates = const []})
      : finalizeGates = [finalizeGate, ...laterFinalizeGates];

  /// One gate per drain, in call order; later drains reuse the last gate.
  final List<Completer<void>> finalizeGates;
  final Object? stampError;
  var _finalizeCalls = 0;
  var stampCalls = 0;

  Future<void> finalizeCurrentSession() {
    final call = _finalizeCalls++;
    return finalizeGates[call < finalizeGates.length ? call : finalizeGates.length - 1].future;
  }

  Future<void> stampConversationId(int start, String id, {String? recordingSessionId}) async {
    stampCalls++;
    if (stampError != null) throw stampError!;
  }

  int getInFlightSeconds() => 0;

  List<dynamic> getSessionUnsyncedWals(int start) => const [];
}

class _Syncs {
  _Syncs(this.phone);
  final _GatedPhoneSync phone;
}

class _GatedWal implements IWalService {
  _GatedWal(this.phone);
  final _GatedPhoneSync phone;

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

class _ThrowingRemovalActions extends _RecordingActions {
  _ThrowingRemovalActions(this.error);

  final Object error;

  @override
  void removeProcessingConversation(String conversationId) => throw error;
}

Future<void> _flushEventQueue() async {
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}

Future<({List<Object> unhandled, Object? harnessError})> _runInGuardedZone(Future<void> Function() body) async {
  final unhandled = <Object>[];
  final done = Completer<void>();
  Object? harnessError;
  runZonedGuarded(() async {
    try {
      await body();
    } catch (e) {
      harnessError = e;
    } finally {
      await _flushEventQueue();
      done.complete();
    }
  }, (error, stackTrace) => unhandled.add(error));
  await done.future;
  return (unhandled: unhandled, harnessError: harnessError);
}

CaptureProvider _provider({
  required _RecordingActions actions,
  required Completer<void> finalizeGate,
  required Future<CreateConversationResponse?> Function() process,
  List<Completer<void>> laterFinalizeGates = const [],
  _GatedPhoneSync? phone,
}) {
  final resolvedPhone = phone ?? _GatedPhoneSync(finalizeGate, laterFinalizeGates: laterFinalizeGates);
  return CaptureProvider(
    externalActions: actions,
    walService: _GatedWal(resolvedPhone),
    processInProgressConversation: process,
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

ServerConversation _conversation({
  required String id,
  String title = '',
  String emoji = '',
  ConversationStatus status = ConversationStatus.completed,
}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime.utc(2026),
    structured: Structured(title, '', emoji: emoji),
    status: status,
  );
}

late CrashlyticsRecorder crashlytics;

void _expectSingleReport(String exception) {
  expect(crashlytics.recordErrors, hasLength(1));
  final args = crashlytics.recordErrors.single.arguments as Map<dynamic, dynamic>;
  expect(args['exception'], exception);
  expect(args['fatal'], isFalse);
  expect(args['stackTraceElements'], isNotEmpty);
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    crashlytics = await installCrashlyticsRecorder();
  });

  setUp(() async {
    crashlytics.reset();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('adds the processing placeholder before finalizeCurrentSession completes', () async {
    final finalize = Completer<void>();
    final actions = _RecordingActions();
    final processStarted = Completer<void>();
    final provider = _provider(
      actions: actions,
      finalizeGate: finalize,
      process: () {
        processStarted.complete();
        return Completer<CreateConversationResponse?>().future;
      },
    );
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();

    expect(actions.processing.map((conversation) => conversation.id), ['0']);
    expect(actions.processing.single.status, ConversationStatus.processing);
    expect(finalize.isCompleted, isFalse);
    expect(processStarted.isCompleted, isFalse);

    finalize.complete();
    await pending;
  });

  test('removes the id 0 placeholder when processing returns null', () async {
    final finalize = Completer<void>();
    final actions = _RecordingActions();
    final provider = _provider(actions: actions, finalizeGate: finalize, process: () async => null);
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();
    expect(actions.processing.map((conversation) => conversation.id), ['0']);

    finalize.complete();
    await pending;
    await Future<void>.delayed(Duration.zero);

    expect(actions.processing, isEmpty);
    expect(actions.upserted, isEmpty);
  });

  test('a conversation that changes during the drain removes the skeleton without processing', () async {
    final finalize = Completer<void>();
    final actions = _RecordingActions();
    var processed = false;
    final provider = _provider(
      actions: actions,
      finalizeGate: finalize,
      process: () async {
        processed = true;
        return null;
      },
    );
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();
    expect(actions.processing.map((conversation) => conversation.id), ['0']);
    // Another path (a server-finished conversation or a batch cut) moves on.
    provider.startNewOfflineRecording();
    finalize.complete();
    await expectLater(pending, completes);
    await Future<void>.delayed(Duration.zero);

    expect(actions.processing, isEmpty);
    expect(processed, isFalse);
    expect(actions.upserted, isEmpty);
  });

  test('a stale drain keeps the skeleton a newer request is still showing', () async {
    final firstDrain = Completer<void>();
    final secondDrain = Completer<void>();
    final actions = _RecordingActions();
    var processCalls = 0;
    final provider = _provider(
      actions: actions,
      finalizeGate: firstDrain,
      laterFinalizeGates: [secondDrain],
      process: () {
        processCalls++;
        return Completer<CreateConversationResponse?>().future;
      },
    );
    addTearDown(provider.dispose);

    final first = provider.forceProcessingCurrentConversation();
    // The conversation moves on during the first drain and the next one is processed.
    provider.startNewOfflineRecording();
    final second = provider.forceProcessingCurrentConversation();

    firstDrain.complete();
    await first;
    expect(actions.processing.map((conversation) => conversation.id), ['0']);

    secondDrain.complete();
    await second;
    expect(processCalls, 1);
    expect(actions.processing.map((conversation) => conversation.id), ['0']);
  });

  test('keeps a processing skeleton instead of a contentless completed row', () async {
    final finalize = Completer<void>();
    final actions = _RecordingActions();
    final contentless = _conversation(id: 'real', status: ConversationStatus.completed);
    final provider = _provider(
      actions: actions,
      finalizeGate: finalize,
      process: () async => CreateConversationResponse(messages: <ServerMessage>[], conversation: contentless),
    );
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();
    finalize.complete();
    await pending;
    await Future<void>.delayed(Duration.zero);

    expect(actions.processing.map((conversation) => conversation.id), ['real']);
    expect(actions.upserted, isEmpty);
  });

  test('replaces the placeholder with the completed row once title and emoji arrive', () async {
    final finalize = Completer<void>();
    final actions = _RecordingActions();
    final ready = _conversation(id: 'ready', title: 'Weekly standup', emoji: '🧠');
    final provider = _provider(
      actions: actions,
      finalizeGate: finalize,
      process: () async => CreateConversationResponse(messages: <ServerMessage>[], conversation: ready),
    );
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();
    finalize.complete();
    await pending;
    await Future<void>.delayed(Duration.zero);

    expect(actions.processing, isEmpty);
    expect(actions.upserted.map((conversation) => conversation.id), ['ready']);
  });

  test('a failed process request is handled by the in-flight listener without an unhandled zone error', () async {
    final sentinel = StateError('process-boom');
    final deterministicStack = StackTrace.fromString('#0      _fail (package:omi/fake.dart:1:1)');
    final finalize = Completer<void>();
    late Completer<CreateConversationResponse?> processGate;
    final provider = _provider(actions: _RecordingActions(), finalizeGate: finalize, process: () => processGate.future);

    final outcome = await _runInGuardedZone(() async {
      processGate = Completer<CreateConversationResponse?>();
      final pending = provider.forceProcessingCurrentConversation();
      finalize.complete();
      await pending;
      processGate.completeError(sentinel, deterministicStack);
      await _flushEventQueue();
      provider.dispose();
    });

    expect(outcome.harnessError, isNull);
    expect(outcome.unhandled, isEmpty);
    _expectSingleReport('capture_process_now: StateError');
    final elements = crashlytics.recordErrors.single.arguments['stackTraceElements'] as List<dynamic>;
    expect(elements.single['file'], 'package:omi/fake.dart');
  });

  test('a throwing processing-list update does not escape as an unhandled zone error', () async {
    final sentinel = StateError('remove-boom');
    final finalize = Completer<void>();
    final provider = _provider(
      actions: _ThrowingRemovalActions(sentinel),
      finalizeGate: finalize,
      process: () async => null,
    );

    final outcome = await _runInGuardedZone(() async {
      final pending = provider.forceProcessingCurrentConversation();
      finalize.complete();
      await pending;
      await _flushEventQueue();
      provider.dispose();
    });

    expect(outcome.harnessError, isNull);
    expect(outcome.unhandled, isEmpty);
    _expectSingleReport('capture_process_now: StateError');
  });

  test('a failed WAL stamp after processing reports once without an unhandled zone error', () async {
    final sentinel = StateError('stamp-boom');
    final finalize = Completer<void>();
    final phone = _GatedPhoneSync(finalize, stampError: sentinel);
    final contentless = _conversation(id: 'real', status: ConversationStatus.completed);
    final provider = _provider(
      actions: _RecordingActions(),
      finalizeGate: finalize,
      process: () async => CreateConversationResponse(messages: <ServerMessage>[], conversation: contentless),
      phone: phone,
    );
    provider.testSessionStartSeconds = 777;

    final outcome = await _runInGuardedZone(() async {
      final pending = provider.forceProcessingCurrentConversation();
      finalize.complete();
      await pending;
      await _flushEventQueue();
      provider.dispose();
    });

    expect(phone.stampCalls, 1);
    expect(outcome.harnessError, isNull);
    expect(outcome.unhandled, isEmpty);
    _expectSingleReport('capture_process_now: StateError');
  });

  test('a Crashlytics transport failure stays contained and the original error remains consumed', () async {
    final sentinel = StateError('process-boom');
    crashlytics.recordErrorFailure = PlatformException(code: 'unavailable', message: 'transport down');
    final finalize = Completer<void>();
    late Completer<CreateConversationResponse?> processGate;
    final provider = _provider(actions: _RecordingActions(), finalizeGate: finalize, process: () => processGate.future);

    final outcome = await _runInGuardedZone(() async {
      processGate = Completer<CreateConversationResponse?>();
      final pending = provider.forceProcessingCurrentConversation();
      finalize.complete();
      await pending;
      processGate.completeError(sentinel);
      await _flushEventQueue();
      provider.dispose();
    });

    expect(outcome.harnessError, isNull);
    expect(outcome.unhandled, isEmpty);
    expect(crashlytics.recordErrors, hasLength(1));
  });
}
