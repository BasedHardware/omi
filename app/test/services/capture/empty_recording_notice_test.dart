import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';

void main() {
  test('recording surfaces come from the session device, then phone versus pendant', () {
    expect(recordingSurfaceForTelemetry('phone_mic_live'), RecordingSurface.phone);
    expect(recordingSurfaceForTelemetry('apple_watch'), RecordingSurface.omi);
    expect(recordingSurfaceForTelemetry('pendant_live'), RecordingSurface.omi);
    expect(
      recordingSurfaceForSession(deviceSource: ConversationSource.apple_watch, telemetrySource: 'pendant_live'),
      RecordingSurface.watch,
    );
    expect(
      recordingSurfaceForSession(deviceSource: ConversationSource.phone, telemetrySource: 'pendant_live'),
      RecordingSurface.phone,
    );
    expect(
      recordingSurfaceForSession(conversationSource: ConversationSource.apple_watch, telemetrySource: 'phone_mic_live'),
      RecordingSurface.watch,
    );
    expect(recordingSurfaceForSession(telemetrySource: 'phone_mic_batch'), RecordingSurface.phone);
    expect(recordingSurfaceForSession(telemetrySource: 'pendant_batch'), RecordingSurface.omi);
    expect(recordingSurfaceForConversation(ConversationSource.omi), RecordingSurface.omi);
  });

  test('discarded-only is true only when every known row was discarded', () {
    expect(onlyDiscardedConversations(const []), isFalse);
    expect(onlyDiscardedConversations(const [true]), isTrue);
    expect(onlyDiscardedConversations(const [true, false]), isFalse);
  });

  test('a null process result removes the placeholder and reports the absence', () async {
    final absences = <ProcessAbsence>[];
    final id = await OptimisticProcessingPlaceholder.applyProcessResult(
      result: null,
      absence: ProcessAbsence.notFound,
      actions: const NoopCaptureExternalActions(),
      onCreated: (_, __) async {},
      onNoConversation: absences.add,
    );
    expect(id, isNull);
    expect(absences, [ProcessAbsence.notFound]);

    absences.clear();
    await OptimisticProcessingPlaceholder.applyProcessResult(
      result: null,
      absence: ProcessAbsence.emptyBody,
      actions: const NoopCaptureExternalActions(),
      onCreated: (_, __) async {},
      onNoConversation: absences.add,
    );
    expect(absences, [ProcessAbsence.emptyBody]);

    absences.clear();
    await OptimisticProcessingPlaceholder.applyProcessResult(
      result: null,
      absence: ProcessAbsence.transport,
      actions: const NoopCaptureExternalActions(),
      onCreated: (_, __) async {},
      onNoConversation: absences.add,
    );
    expect(absences, [ProcessAbsence.transport]);
  });

  test('a returned conversation does not explain an empty recording', () async {
    final absences = <ProcessAbsence>[];
    final created = <String>[];
    final id = await OptimisticProcessingPlaceholder.applyProcessResult(
      result: CreateConversationResponse(
        messages: const <ServerMessage>[],
        conversation: ServerConversation(
          id: 'kept',
          createdAt: DateTime.utc(2026, 1, 1),
          structured: Structured('Kept', 'Overview', emoji: '🧠'),
          status: ConversationStatus.completed,
        ),
      ),
      actions: const NoopCaptureExternalActions(),
      onCreated: (conversation, _) async => created.add(conversation.id),
      onNoConversation: absences.add,
    );
    expect(id, 'kept');
    expect(created, ['kept']);
    expect(absences, isEmpty);
  });

  test('completion facts survive stop and a failed start does not reuse them', () {
    var now = DateTime.utc(2026, 1, 1, 12);
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (_, __) {},
      idFactory: () => 'rec-1',
      clock: () => now,
      identityEpoch: () => 1,
    );
    telemetry.prepare(source: 'phone_mic_live');
    expect(telemetry.markStarted(), isTrue);
    expect(telemetry.markStarted(), isFalse);
    now = now.add(const Duration(seconds: 12));
    expect(telemetry.complete(), isTrue);
    final facts = telemetry.completionFacts();
    expect(facts?.source, 'phone_mic_live');
    expect(facts?.durationSeconds, 12);
    expect(facts?.transcriptObserved, isFalse);

    telemetry.prepare(source: 'phone_mic_live');
    expect(telemetry.complete(), isFalse);
    expect(telemetry.completionFacts()?.durationSeconds, 12);
  });
}
