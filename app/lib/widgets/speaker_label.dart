import 'package:flutter/widgets.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';

Person? personById(List<Person> people, String? id) {
  if (id == null) return null;
  for (final person in people) {
    if (person.id == id) return person;
  }
  return null;
}

String speakerLabel(BuildContext context, TranscriptSegment segment, Person? person) {
  if (segment.isUser) return context.l10n.you;
  if (segment.speakerId == omiSpeakerId) return 'omi';
  return person?.name ?? context.l10n.speakerWithId('${segment.speakerId + 1}');
}
