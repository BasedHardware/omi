import 'package:collection/collection.dart';

import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

enum SpeakerSuggestionDisposition { ignored, retained, assignment }

/// Reconciles questions by speaker, even when later evidence refers to another segment.
/// Only the existing assignment event path may label a transcript.
SpeakerSuggestionDisposition reconcileSpeakerSuggestion(
  SpeakerLabelSuggestionEvent event,
  List<TranscriptSegment> segments,
  List<String> taggingSegmentIds,
  Map<String, SpeakerLabelSuggestionEvent> suggestions,
) {
  if (event.speakerId < 0 || event.segmentId.isEmpty) return SpeakerSuggestionDisposition.ignored;
  if (event.retracted) {
    suggestions.removeWhere((_, suggestion) => suggestion.speakerId == event.speakerId);
    return SpeakerSuggestionDisposition.retained;
  }
  if (event.personName.trim().isEmpty || taggingSegmentIds.contains(event.segmentId)) {
    return SpeakerSuggestionDisposition.ignored;
  }
  final segment = segments.firstWhereOrNull((segment) => segment.id == event.segmentId);
  if (segment == null || segment.speakerId != event.speakerId || segment.personId != null || segment.isUser) {
    return SpeakerSuggestionDisposition.ignored;
  }
  suggestions.removeWhere((_, suggestion) => suggestion.speakerId == event.speakerId);
  if (event.personId.isEmpty) {
    suggestions[event.segmentId] = event;
    return SpeakerSuggestionDisposition.retained;
  }
  return SpeakerSuggestionDisposition.assignment;
}
