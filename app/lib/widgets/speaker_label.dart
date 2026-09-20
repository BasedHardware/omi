import 'package:flutter/widgets.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

/// PeopleProvider owns live names. Standalone transcript views can use the
/// persisted people snapshot, without retaining positive or negative lookups.
Person? currentSpeakerPerson(BuildContext context, String? id) {
  if (id == null) return null;
  final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
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
