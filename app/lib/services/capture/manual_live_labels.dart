import 'package:omi/backend/schema/transcript_segment.dart';

/// Retain manual choices before merging live revisions, including individual-line tags.
void retainManualLiveLabels(
  List<TranscriptSegment> existing,
  List<TranscriptSegment> incoming,
  Map<int, String> speakerDefaults,
) {
  final manualById = {
    for (final line in existing)
      if (line.speakerLabelSource == 'manual') line.id: line
  };
  for (final line in incoming) {
    // A new acknowledged manual edit is authoritative, including one made on
    // another client. Only stale automatic/unlabeled projections need repair.
    if (line.speakerLabelSource == 'manual') continue;
    final previous = manualById[line.id];
    final assigned = speakerDefaults[line.speakerId];
    if (previous != null) {
      line.isUser = previous.isUser;
      line.personId = previous.personId;
      line.speakerLabelSource = 'manual';
    } else if (assigned != null) {
      line.isUser = assigned == 'user';
      line.personId = line.isUser ? null : assigned;
      line.speakerLabelSource = 'manual';
    }
  }
}
