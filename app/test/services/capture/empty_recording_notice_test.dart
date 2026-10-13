import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';

void main() {
  test('missing process results map to empty-deleted or null', () {
    expect(
      reasonForMissingConversation(hasResponse: false, hasConversation: false, absence: ProcessAbsence.notFound),
      EmptyRecordingReason.emptyDeleted,
    );
    expect(
      reasonForMissingConversation(hasResponse: false, hasConversation: false, absence: ProcessAbsence.emptyBody),
      EmptyRecordingReason.emptyDeleted,
    );
    expect(
      reasonForMissingConversation(hasResponse: true, hasConversation: false),
      EmptyRecordingReason.emptyDeleted,
    );
    expect(
      reasonForMissingConversation(hasResponse: false, hasConversation: false, absence: ProcessAbsence.transport),
      EmptyRecordingReason.nullResult,
    );
    expect(
      reasonForMissingConversation(hasResponse: true, hasConversation: true),
      isNull,
    );
  });

  test('only a short phone stop with no transcript is explained immediately', () {
    expect(
      shouldExplainShortPhoneStop(
        surface: RecordingSurface.phone,
        durationSeconds: 12,
        transcriptObserved: false,
        conversationDelivered: false,
      ),
      isTrue,
    );
    expect(
      shouldExplainShortPhoneStop(
        surface: RecordingSurface.phone,
        durationSeconds: 30,
        transcriptObserved: false,
        conversationDelivered: false,
      ),
      isFalse,
    );
    expect(
      shouldExplainShortPhoneStop(
        surface: RecordingSurface.watch,
        durationSeconds: 4,
        transcriptObserved: false,
        conversationDelivered: false,
      ),
      isFalse,
    );
    expect(
      shouldExplainShortPhoneStop(
        surface: RecordingSurface.omi,
        durationSeconds: 4,
        transcriptObserved: false,
        conversationDelivered: false,
      ),
      isFalse,
    );
    expect(
      shouldExplainShortPhoneStop(
        surface: RecordingSurface.phone,
        durationSeconds: 8,
        transcriptObserved: true,
        conversationDelivered: false,
      ),
      isFalse,
    );
    expect(
      shouldExplainShortPhoneStop(
        surface: RecordingSurface.phone,
        durationSeconds: 8,
        transcriptObserved: false,
        conversationDelivered: true,
      ),
      isFalse,
    );
  });

  test('recording surfaces stay phone, watch, or omi', () {
    expect(recordingSurfaceForSource('phone_mic_live'), RecordingSurface.phone);
    expect(recordingSurfaceForSource('apple_watch'), RecordingSurface.watch);
    expect(recordingSurfaceForSource('pendant_live'), RecordingSurface.omi);
    expect(recordingSurfaceForConversation(ConversationSource.phone), RecordingSurface.phone);
    expect(recordingSurfaceForConversation(ConversationSource.apple_watch), RecordingSurface.watch);
    expect(recordingSurfaceForConversation(ConversationSource.omi), RecordingSurface.omi);
  });

  test('discarded-only is true only when every known row was discarded', () {
    expect(onlyDiscardedConversations(const []), isFalse);
    expect(onlyDiscardedConversations(const [true]), isTrue);
    expect(onlyDiscardedConversations(const [true, false]), isFalse);
  });

  test('a null process result removes the placeholder and reports why', () async {
    final reasons = <EmptyRecordingReason>[];
    final id = await OptimisticProcessingPlaceholder.applyProcessResult(
      result: null,
      absence: ProcessAbsence.notFound,
      actions: const NoopCaptureExternalActions(),
      onCreated: (_, __) async {},
      onNoConversation: reasons.add,
    );
    expect(id, isNull);
    expect(reasons, [EmptyRecordingReason.emptyDeleted]);

    reasons.clear();
    await OptimisticProcessingPlaceholder.applyProcessResult(
      result: null,
      absence: ProcessAbsence.transport,
      actions: const NoopCaptureExternalActions(),
      onCreated: (_, __) async {},
      onNoConversation: reasons.add,
    );
    expect(reasons, [EmptyRecordingReason.nullResult]);
  });

  test('a returned conversation does not explain an empty recording', () async {
    final reasons = <EmptyRecordingReason>[];
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
      onNoConversation: reasons.add,
    );
    expect(id, 'kept');
    expect(created, ['kept']);
    expect(reasons, isEmpty);
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
