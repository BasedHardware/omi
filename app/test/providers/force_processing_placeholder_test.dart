import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:omi/services/telemetry/finish_home_sli_telemetry.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/reliability_experiments.dart';

import '../support/crashlytics_recorder.dart';

class _RecordingActions extends NoopCaptureExternalActions {
  final processing = <ServerConversation>[];
  final upserted = <ServerConversation>[];
  final ended = <(String, String?)>[];
  ServerConversation? manualFinishRow;
  bool? manualFinishFailed;
  ProcessAbsence? manualFinishAbsence;

  @override
  void onManualFinishStarted(ServerConversation placeholder, String? recordingId,
      {String? liveConversationId, String? captureId}) {
    manualFinishRow = placeholder;
  }

  @override
  void onManualFinishSettled(ServerConversation placeholder, InProgressProcessOutcome? outcome,
      {required bool showFailure}) {
    if (!identical(placeholder, manualFinishRow)) return;
    manualFinishFailed = outcome?.response?.conversation == null && showFailure;
    manualFinishAbsence = outcome?.absence;
  }

  @override
  void onEndAccepted(ServerConversation saved, {String? liveConversationId}) {
    ended.add((saved.id, liveConversationId));
  }

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
  _GatedPhoneSync(Completer<void> finalizeGate,
      {this.stampError, this.onFinalize, List<Completer<void>> laterFinalizeGates = const []})
      : finalizeGates = [finalizeGate, ...laterFinalizeGates];

  /// One gate per drain, in call order; later drains reuse the last gate.
  final List<Completer<void>> finalizeGates;
  final Object? stampError;

  /// Runs as each WAL drain begins.
  final void Function()? onFinalize;
  var _finalizeCalls = 0;
  var stampCalls = 0;

  Future<void> finalizeCurrentSession() {
    onFinalize?.call();
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
  Future<CreateConversationResponse?> Function()? process,
  InProgressConversationRequestSender? processRequestSender,
  List<Completer<void>> laterFinalizeGates = const [],
  _GatedPhoneSync? phone,
}) {
  final resolvedPhone = phone ?? _GatedPhoneSync(finalizeGate, laterFinalizeGates: laterFinalizeGates);
  return CaptureProvider(
    externalActions: actions,
    walService: _GatedWal(resolvedPhone),
    processInProgressConversation: process,
    processRequestSender: processRequestSender,
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

  test('manual Finish serializes its optional window in the outbound POST', () async {
    Env.overrideApiBaseUrl('https://finish.test/');
    addTearDown(Env.clearApiBaseUrlOverride);
    final requests = <ApiRequest>[];
    final actions = _RecordingActions();
    final provider = _provider(
      actions: actions,
      finalizeGate: Completer<void>()..complete(),
      processRequestSender: (request) async {
        requests.add(request);
        return http.Response('', 404);
      },
    );
    addTearDown(provider.dispose);

    await provider.forceProcessingCurrentConversation(manualFinish: true, liveConversationId: 'window-1');
    await _flushEventQueue();
    await provider.forceProcessingCurrentConversation(manualFinish: true);
    await _flushEventQueue();
    final result = await provider.finishCaptureWithOutcome(liveConversationId: 'window-2');

    expect(requests.map((request) => request.method), ['POST', 'POST', 'POST']);
    expect(requests.map((request) => request.url).toSet(), {'https://finish.test/v1/conversations'});
    expect(requests.map((request) => request.body), [
      '{"live_conversation_id":"window-1"}',
      '{}',
      '{"live_conversation_id":"window-2"}',
    ]);
    expect(result.absence, ProcessAbsence.notFound);
  });

  test('a coordinator Finish records exactly one Finish cut before the WAL drain', () async {
    const owner = 'coordinator-finish-owner';
    final wasTestFlight = Env.isTestFlight;
    Env.isTestFlight = true;
    addTearDown(() => Env.isTestFlight = wasTestFlight);
    final telemetry = FinishHomeSliTelemetry.instance;
    final (enabled, ownerId, platform) = (telemetry.testFlightEnabled, telemetry.ownerId, telemetry.platform);
    telemetry
      ..testFlightEnabled = (() => true)
      ..ownerId = (() => owner)
      ..platform = (() => 'ios');
    addTearDown(() => telemetry
      ..testFlightEnabled = enabled
      ..ownerId = ownerId
      ..platform = platform);
    List<ClientTelemetryObservation> cuts() =>
        telemetry.outbox.pending(owner).where((observation) => observation.family == 'finish_cut').toList();

    final finalize = Completer<void>();
    final drainEntered = Completer<int>();
    final provider = _provider(
      actions: _RecordingActions(),
      finalizeGate: finalize,
      phone: _GatedPhoneSync(finalize, onFinalize: () {
        if (!drainEntered.isCompleted) drainEntered.complete(cuts().length);
      }),
      process: () async => null,
    );
    addTearDown(provider.dispose);

    // Home's Wrap Up and the live page's Finish reach Process Now only through the coordinator.
    final finish = provider.finishCaptureWithOutcome(liveConversationId: 'window-1');
    expect(await drainEntered.future.timeout(const Duration(seconds: 5)), 1,
        reason: 'the cut is durable before the WAL drain starts');
    finalize.complete();
    await finish;
    await _flushEventQueue();

    expect(cuts(), hasLength(1));
    expect(cuts().single.attributes['source'], 'app');
  });

  test('end_open_conversation: every End carries the moment it was asked for; off, no header is sent', () async {
    Env.overrideApiBaseUrl('https://finish.test/');
    addTearDown(Env.clearApiBaseUrlOverride);
    addTearDown(() => ReliabilityExperiments.overrideForTesting(null));
    final requests = <ApiRequest>[];
    final finalize = Completer<void>();
    final provider = _provider(
      actions: _RecordingActions(),
      finalizeGate: finalize,
      laterFinalizeGates: [Completer<void>()..complete()],
      processRequestSender: (request) async {
        requests.add(request);
        return http.Response('', 404);
      },
    );
    addTearDown(provider.dispose);

    ReliabilityExperiments.overrideForTesting(const {});
    final baseline = provider.forceProcessingCurrentConversation(manualFinish: true);
    finalize.complete();
    await baseline;
    await _flushEventQueue();
    expect(requests.single.headers.containsKey(endedAtHeader), isFalse);

    ReliabilityExperiments.overrideForTesting({'end_open_conversation'});
    final before = DateTime.now();
    await provider.forceProcessingCurrentConversation(manualFinish: true);
    await _flushEventQueue();
    await provider.finishCaptureWithOutcome(liveConversationId: 'window-2');
    final after = DateTime.now();
    expect(requests, hasLength(3));
    for (final request in requests.skip(1)) {
      final sent = double.parse(request.headers[endedAtHeader]!);
      expect(sent, greaterThanOrEqualTo(before.millisecondsSinceEpoch / 1000 - 0.001));
      expect(sent, lessThanOrEqualTo(after.millisecondsSinceEpoch / 1000 + 0.001));
    }
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
    expect(actions.manualFinishRow, isNull, reason: 'a coordinator close must remain silent');
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

  for (final status in [ConversationStatus.processing, ConversationStatus.in_progress]) {
    test('Process Now tracks an exact recording as closed only after acceptance (${status.name})', () async {
      final provider = _provider(
        actions: _RecordingActions(),
        finalizeGate: Completer<void>()..complete(),
        process: () async => CreateConversationResponse(
          messages: [],
          conversation: _conversation(id: 'recording-1', status: status),
        ),
      );
      addTearDown(provider.dispose);

      expect(provider.hasClosedServerRecording('recording-1'), isFalse);
      await provider.forceProcessingCurrentConversation(manualFinish: true);
      await _flushEventQueue();

      expect(provider.hasClosedServerRecording('recording-1'), status == ConversationStatus.processing);
      expect(provider.hasClosedServerRecording('recording-2'), isFalse);
    });
  }

  test('pendant double tap publishes manual finish before the drain and reports an unanswered request', () async {
    final finalize = Completer<void>();
    final actions = _RecordingActions();
    final provider = _provider(actions: actions, finalizeGate: finalize, process: () async => null);
    addTearDown(provider.dispose);
    SharedPreferencesUtil().omiButtonActionsEnabled = true;
    SharedPreferencesUtil().doubleTapAction = 0;

    provider.handleButtonEventForTesting('synthetic-pendant', 2);
    expect(actions.manualFinishRow, same(actions.processing.single));
    expect(actions.manualFinishFailed, isNull);

    finalize.complete();
    await _flushEventQueue();
    expect(actions.manualFinishFailed, isTrue);
    expect(actions.manualFinishAbsence, ProcessAbsence.transport);
    expect(actions.processing, isEmpty);
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

  test('every accepted End reports its conversation once, with the window it named; an unanswered one does not',
      () async {
    final finalize = Completer<void>()..complete();
    final actions = _RecordingActions();
    final provider = _provider(
      actions: actions,
      finalizeGate: finalize,
      process: () async => CreateConversationResponse(
          messages: <ServerMessage>[], conversation: _conversation(id: 'real', status: ConversationStatus.processing)),
    );
    addTearDown(provider.dispose);

    // The shared path behind Finish, Wrap Up and the record button's stop: no manual-finish flag.
    await provider.forceProcessingCurrentConversation();
    await _flushEventQueue();
    expect(actions.ended, [('real', null)]);

    // End Conversation and a pendant double-tap: the manual finish, here naming its window.
    await provider.forceProcessingCurrentConversation(manualFinish: true, liveConversationId: 'window');
    await _flushEventQueue();
    expect(actions.ended, [('real', null), ('real', 'window')]);

    final unanswered = _RecordingActions();
    final silent = _provider(actions: unanswered, finalizeGate: finalize, process: () async => null);
    addTearDown(silent.dispose);
    await silent.forceProcessingCurrentConversation(manualFinish: true);
    await _flushEventQueue();
    expect(unanswered.ended, isEmpty);
  });

  test('a contentless completed response settles into the real row', () async {
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

    expect(actions.processing, isEmpty);
    expect(actions.upserted.map((conversation) => conversation.id), ['real']);
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

  test('a failed middle drain cannot let a later server close bypass an unresolved predecessor', () async {
    final sentinel = StateError('middle-drain-boom');
    late _GatedPhoneSync phone;
    late int stampsBeforeFirstDrain;
    final outcome = await _runInGuardedZone(() async {
      final firstDrain = Completer<void>();
      final secondDrain = Completer<void>();
      final thirdDrain = Completer<void>()..complete();
      phone = _GatedPhoneSync(firstDrain, laterFinalizeGates: [secondDrain, thirdDrain]);
      final provider = _provider(
        actions: _RecordingActions(),
        finalizeGate: firstDrain,
        phone: phone,
        process: () async => null,
      );
      try {
        provider.testSessionStartSeconds = 777;
        provider.onMessageEventReceived(ConversationProcessingStartedEvent(memory: _conversation(id: 'a')));

        provider.testSessionStartSeconds = 778;
        final second = provider.forceProcessingCurrentConversation();
        final expectedFailure = expectLater(second, throwsA(same(sentinel)));
        secondDrain.completeError(sentinel, StackTrace.fromString('#0      _fail (package:omi/fake.dart:1:1)'));
        await expectedFailure;

        provider.testSessionStartSeconds = 779;
        provider.onMessageEventReceived(ConversationProcessingStartedEvent(memory: _conversation(id: 'c')));
        await _flushEventQueue();
        stampsBeforeFirstDrain = phone.stampCalls;

        firstDrain.complete();
        await _flushEventQueue();
      } finally {
        if (!firstDrain.isCompleted) firstDrain.complete();
        if (!secondDrain.isCompleted) secondDrain.complete();
        provider.dispose();
      }
    });

    expect(stampsBeforeFirstDrain, 0, reason: 'the failed middle slot must retain the first close as its predecessor');
    expect(phone.stampCalls, 2, reason: 'both valid closes stamp after the first drain completes');
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
