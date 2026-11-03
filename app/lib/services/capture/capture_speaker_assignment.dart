import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

/// Serial persistence with immediate labels; capture owns the stream publication.
mixin CaptureSpeakerAssignment on ChangeNotifier {
  ServerConversation? get speakerAssignmentConversation;
  String? get activeCaptureSessionId;
  List<TranscriptSegment> get segments;
  CaptureExternalActions get externalActions;
  bool get speakerAssignmentClosed;
  Object get speakerAssignmentIdentity;
  void speakerLabelsChanged();
  void publishSpeakerAssignment(
      int speakerId, String personId, String personName, List<String> targets, bool applyToSpeaker, int generation);
  List<String> taggingSegmentIds = [];

  Future<void> _speakerAssignmentTail = Future.value();
  final Expando<int> _liveLabelGeneration = Expando<int>();
  int _liveLabelSequence = 0;
  bool speakerAssignmentStale = false;
  int lastSpeakerAppliedCount = 0;

  Future<bool> assignSpeakerToConversation(
    int speakerId,
    String personId,
    String personName,
    List<String> segmentIds, {
    bool applyToSpeaker = false,
  }) async {
    final conversationId = speakerAssignmentConversation?.id;
    final sessionId = activeCaptureSessionId;
    if (segmentIds.isEmpty || conversationId == null || speakerAssignmentClosed) return false;
    final actions = externalActions;
    final identity = speakerAssignmentIdentity;
    final previous = _speakerAssignmentTail;
    final finished = Completer<void>();
    _speakerAssignmentTail = finished.future;
    final generation = ++_liveLabelSequence;
    final targets = List<String>.of(segmentIds);
    final selected =
        segments.where((line) => applyToSpeaker ? line.speakerId == speakerId : targets.contains(line.id)).toList();
    final before = {for (final line in selected) line: (line.isUser, line.personId, line.speakerLabelSource)};
    for (final line in selected) {
      _liveLabelGeneration[line] = generation;
      line.isUser = personId == 'user';
      line.personId = line.isUser || personId.isEmpty ? null : personId;
      line.speakerLabelSource = 'manual';
    }
    taggingSegmentIds = [...taggingSegmentIds, ...targets];
    speakerLabelsChanged();
    if (!speakerAssignmentClosed) notifyListeners();
    var committed = false;
    try {
      await previous;
      if (speakerAssignmentClosed || identity != speakerAssignmentIdentity) return false;
      speakerAssignmentStale = false;
      final finalPersonId = personId.isEmpty ? (await actions.createPerson(personName))?.id : personId;
      if (finalPersonId == null ||
          finalPersonId.isEmpty ||
          speakerAssignmentClosed ||
          identity != speakerAssignmentIdentity) {
        return false;
      }
      final saved = await actions.assignSpeaker(
        conversationId,
        targets,
        finalPersonId,
        speakerId: applyToSpeaker ? speakerId : null,
      );
      if (!saved) return false;
      committed = true;
      lastSpeakerAppliedCount = actions.lastSpeakerAppliedCount;
      if (speakerAssignmentClosed ||
          speakerAssignmentIdentity != identity ||
          speakerAssignmentConversation?.id != conversationId ||
          activeCaptureSessionId != sessionId) {
        return true;
      }
      for (final segment in selected) {
        if (_liveLabelGeneration[segment] != generation) continue;
        segment.isUser = finalPersonId == 'user';
        segment.personId = segment.isUser ? null : finalPersonId;
        segment.speakerLabelSource = 'manual';
      }
      speakerLabelsChanged();
      publishSpeakerAssignment(speakerId, finalPersonId, personName, targets, applyToSpeaker, generation);
      return true;
    } catch (error) {
      speakerAssignmentStale = error is StaleSpeakerException;
      return false;
    } finally {
      if (!committed) {
        for (final line in selected) {
          if (_liveLabelGeneration[line] != generation) continue;
          final original = before[line]!;
          line.isUser = original.$1;
          line.personId = original.$2;
          line.speakerLabelSource = original.$3;
        }
        speakerLabelsChanged();
      }
      taggingSegmentIds = taggingSegmentIds.where((id) => !targets.contains(id)).toList();
      finished.complete();
      if (!speakerAssignmentClosed) notifyListeners();
    }
  }
}
