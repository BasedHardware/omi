import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

typedef CaptureSpeakerSaveOutcome = ({
  bool saved,
  int lines,
  bool stale,
  bool limited,
  bool partial,
  bool coverageComplete
});

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

  /// "Not a person" exclusion path for [assignSpeakerToConversation]. The
  /// owning controller implements it: it owns the exclusion state, the
  /// decision epoch and the transport seam.
  Future<bool> excludeSpeakerFromConversation(int speakerId, List<String> segmentIds);
  List<String> taggingSegmentIds = [];

  Future<void> _speakerAssignmentTail = Future.value();
  final Expando<int> _liveLabelGeneration = Expando<int>();
  int _liveLabelSequence = 0;
  final Expando<int> _pendingLiveLabels = Expando<int>();
  final Expando<(bool, String?, String?)> _confirmedLiveLabels = Expando<(bool, String?, String?)>();

  Future<bool> assignSpeakerToConversation(
    int speakerId,
    String personId,
    String personName,
    List<String> segmentIds, {
    bool applyToSpeaker = false,
    bool notAPerson = false,
    (String, String)? voice,
    ValueChanged<CaptureSpeakerSaveOutcome>? onSettled,
  }) async {
    if (notAPerson) return excludeSpeakerFromConversation(speakerId, segmentIds);
    final conversationId = speakerAssignmentConversation?.id;
    final sessionId = activeCaptureSessionId;
    if (segmentIds.isEmpty || conversationId == null || speakerAssignmentClosed) return false;
    final actions = externalActions;
    final identity = speakerAssignmentIdentity;
    final anchor = segments.where((line) => line.id == segmentIds.first).firstOrNull;
    if (anchor == null) return false;
    final selected = segments
        .where((line) => applyToSpeaker
            ? (voice == null ? anchor.sameRecordingVoice(line) : line.recordingVoice == voice)
            : segmentIds.contains(line.id))
        .toList();
    if (selected.isEmpty) return false;
    final targets = selected.map((line) => line.id).toList();
    final previous = _speakerAssignmentTail;
    final finished = Completer<void>();
    _speakerAssignmentTail = finished.future;
    final generation = ++_liveLabelSequence;
    final before = {for (final line in selected) line: (line.isUser, line.personId, line.speakerLabelSource)};
    for (final line in selected) {
      if ((_pendingLiveLabels[line] ?? 0) == 0) _confirmedLiveLabels[line] = before[line];
      _pendingLiveLabels[line] = (_pendingLiveLabels[line] ?? 0) + 1;
      _liveLabelGeneration[line] = generation;
      line.isUser = personId == 'user';
      line.personId = line.isUser || personId.isEmpty ? null : personId;
      line.speakerLabelSource = 'manual';
    }
    taggingSegmentIds = [...taggingSegmentIds, ...targets];
    speakerLabelsChanged();
    if (!speakerAssignmentClosed) notifyListeners();
    var committed = false;
    var staleFailure = false;
    var appliedCount = 0;
    var limitedFailure = false;
    var partialFailure = false;
    try {
      await previous;
      if (speakerAssignmentClosed || identity != speakerAssignmentIdentity) return false;
      final finalPersonId = personId.isEmpty ? (await actions.createPerson(personName))?.id : personId;
      if (finalPersonId == null ||
          finalPersonId.isEmpty ||
          speakerAssignmentClosed ||
          identity != speakerAssignmentIdentity) {
        return false;
      }
      bool saved;
      try {
        saved = await actions.assignSpeaker(
          conversationId,
          targets,
          finalPersonId,
          speakerId: applyToSpeaker ? speakerId : null,
          voice: applyToSpeaker ? (voice ?? anchor.recordingVoice) : null,
        );
      } on PartialSpeakerAssignmentException catch (error) {
        partialFailure = true;
        appliedCount = error.appliedCount;
        staleFailure = error.stale;
        saved = error.succeeded.contains(conversationId);
      }
      if (!saved) return false;
      committed = true;
      for (final line in selected) {
        _confirmedLiveLabels[line] =
            (finalPersonId == 'user', finalPersonId == 'user' ? null : finalPersonId, 'manual');
      }
      if (!partialFailure) appliedCount = actions.lastSpeakerAppliedCount;
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
      staleFailure = error is StaleSpeakerException;
      limitedFailure = error is RecordingSpeakerLimitException;
      return false;
    } finally {
      if (!committed) {
        for (final line in selected) {
          if (_liveLabelGeneration[line] != generation) continue;
          final original = _confirmedLiveLabels[line] ?? before[line]!;
          line.isUser = original.$1;
          line.personId = original.$2;
          line.speakerLabelSource = original.$3;
        }
        speakerLabelsChanged();
      }
      final remaining = List<String>.of(taggingSegmentIds);
      for (final id in targets) {
        remaining.remove(id);
      }
      taggingSegmentIds = remaining;
      for (final line in selected) {
        _pendingLiveLabels[line] = (_pendingLiveLabels[line] ?? 1) - 1;
      }
      finished.complete();
      if (!speakerAssignmentClosed) notifyListeners();
      if (!speakerAssignmentClosed && identity == speakerAssignmentIdentity) {
        onSettled?.call((
          saved: committed,
          lines: appliedCount,
          stale: staleFailure,
          limited: limitedFailure,
          coverageComplete: !partialFailure && actions.lastSpeakerCoverageComplete,
          partial: partialFailure
        ));
      }
    }
  }
}
