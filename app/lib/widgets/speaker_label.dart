import 'package:flutter/widgets.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/ui/format/speaker_names.dart';
import 'package:omi/utils/l10n_extensions.dart';

Person? personById(List<Person> people, String? id) {
  if (id == null) return null;
  for (final person in people) {
    if (person.id == id) return person;
  }
  return null;
}

/// In-app name for [segment]'s speaker: "You", the assigned [person], "Omi", or "Speaker N".
///
/// Pass the conversation's [segments] so "Speaker N" uses the conversation's dense numbering
/// (see [SpeakerNames]); without them only [segment] is known and it is numbered 1. Code that
/// labels many segments builds one [SpeakerNames.forSegments] resolver instead.
String speakerLabel(BuildContext context, TranscriptSegment segment, Person? person,
    {List<TranscriptSegment>? segments}) {
  return SpeakerNames.forSegments(segments ?? [segment], l10n: context.l10n).forSegment(segment, person: person);
}
