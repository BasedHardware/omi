import 'dart:async';

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
  _GatedPhoneSync(this.finalizeGate);

  final Completer<void> finalizeGate;
  var stampCalls = 0;

  Future<void> finalizeCurrentSession() => finalizeGate.future;

  Future<void> stampConversationId(int start, String id) async {
    stampCalls++;
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

CaptureProvider _provider({
  required _RecordingActions actions,
  required Completer<void> finalizeGate,
  required Future<CreateConversationResponse?> Function() process,
}) {
  final phone = _GatedPhoneSync(finalizeGate);
  return CaptureProvider(
    externalActions: actions,
    walService: _GatedWal(phone),
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

void main() {
  setUp(() async {
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
    final provider = _provider(
      actions: actions,
      finalizeGate: finalize,
      process: () async => null,
    );
    addTearDown(provider.dispose);

    final pending = provider.forceProcessingCurrentConversation();
    expect(actions.processing.map((conversation) => conversation.id), ['0']);

    finalize.complete();
    await pending;
    await Future<void>.delayed(Duration.zero);

    expect(actions.processing, isEmpty);
    expect(actions.upserted, isEmpty);
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
}
