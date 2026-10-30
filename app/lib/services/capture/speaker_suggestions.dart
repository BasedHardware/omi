import 'package:collection/collection.dart';

import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

enum SpeakerSuggestionDisposition { ignored, retained, assignment, reverted }

/// Reconciles questions by speaker, even when later evidence refers to another segment.
/// Only the existing assignment event path may label a transcript.
SpeakerSuggestionDisposition reconcileSpeakerSuggestion(
  SpeakerLabelSuggestionEvent event,
  List<TranscriptSegment> segments,
  List<String> taggingSegmentIds,
  Map<String, SpeakerLabelSuggestionEvent> suggestions, {
  bool explicitOwner = false,
}) {
  if (event.speakerId < 0 || event.segmentId.isEmpty) return SpeakerSuggestionDisposition.ignored;
  if (event.retracted) {
    suggestions.removeWhere((_, suggestion) => suggestion.speakerId == event.speakerId);
    if (explicitOwner) {
      var changed = false;
      for (final segment in segments) {
        if (segment.speakerId != event.speakerId ||
            segment.speakerLabelSource == 'manual' ||
            (!segment.isUser && segment.personId == null) ||
            taggingSegmentIds.contains(segment.id)) {
          continue;
        }
        segment.isUser = false;
        segment.personId = null;
        segment.speakerLabelSource = null;
        changed = true;
      }
      if (changed) return SpeakerSuggestionDisposition.reverted;
    }
    return SpeakerSuggestionDisposition.retained;
  }
  if ((!explicitOwner || !event.resolvesOwner) && event.personName.trim().isEmpty ||
      taggingSegmentIds.contains(event.segmentId)) {
    return SpeakerSuggestionDisposition.ignored;
  }
  final segment = segments.firstWhereOrNull((segment) => segment.id == event.segmentId);
  if (segment == null ||
      segment.speakerId != event.speakerId ||
      (explicitOwner ? segment.speakerLabelSource == 'manual' : segment.personId != null || segment.isUser)) {
    return SpeakerSuggestionDisposition.ignored;
  }
  suggestions.removeWhere((_, suggestion) => suggestion.speakerId == event.speakerId);
  if (event.personId.isEmpty && !(explicitOwner && event.resolvesOwner)) {
    suggestions[event.segmentId] = event;
    return SpeakerSuggestionDisposition.retained;
  }
  return SpeakerSuggestionDisposition.assignment;
}

/// Server-resolved labels replace automatic labels; manual edits remain authoritative.
void applyResolvedSpeakerSuggestion(
    SpeakerLabelSuggestionEvent event, List<TranscriptSegment> segments, List<String> taggingSegmentIds) {
  for (final segment in segments) {
    if (segment.speakerId != event.speakerId ||
        segment.speakerLabelSource == 'manual' ||
        taggingSegmentIds.contains(segment.id)) {
      continue;
    }
    segment.isUser = event.resolvesOwner;
    segment.personId = event.resolvesOwner || event.personId.isEmpty ? null : event.personId;
    segment.speakerLabelSource = 'auto';
  }
}
