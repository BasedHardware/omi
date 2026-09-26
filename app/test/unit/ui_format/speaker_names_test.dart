import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/speaker_names.dart';
import 'package:omi/utils/constants.dart';

TranscriptSegment seg(int speakerId, {bool isUser = false, String? personId, String text = 'hi'}) => TranscriptSegment(
      id: '$speakerId-$text',
      text: text,
      speaker: 'SPEAKER_${speakerId.toString().padLeft(2, '0')}',
      speakerId: speakerId,
      isUser: isUser,
      personId: personId,
      start: 0,
      end: 1,
      translations: const [],
    );

Person person(String id, String name) => Person(
      id: id,
      name: name,
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    );

/// One speaker vocabulary on every surface: "You", people's names, "Omi", and dense "Speaker N".
void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  test('anonymous speakers are numbered densely in order of first appearance', () {
    // Owner is SPEAKER_00; the others are 2 and 7 (a provider restart left a gap).
    final segments = [seg(0, isUser: true), seg(7), seg(2), seg(7), seg(0, isUser: true)];
    final names = SpeakerNames.forSegments(segments, l10n: en);
    expect(segments.map(names.forSegment).toList(), ['You', 'Speaker 1', 'Speaker 2', 'Speaker 1', 'You']);
  });

  test('naming a person does not renumber the others', () {
    final before = [seg(1), seg(2), seg(3)];
    final after = [seg(1), seg(2, personId: 'p1'), seg(3)];
    final people = [person('p1', 'Ada')];
    final names = SpeakerNames.forSegments(after, people: people, l10n: en);
    expect(after.map(names.forSegment).toList(), ['Speaker 1', 'Ada', 'Speaker 3']);
    expect(SpeakerNames.forSegments(before, l10n: en).forSegment(before[2]), 'Speaker 3');
  });

  test('Omi is "Omi", never "Speaker 100", and never takes a number', () {
    final segments = [seg(omiSpeakerId), seg(4)];
    final names = SpeakerNames.forSegments(segments, l10n: en);
    expect(names.forSegment(segments[0]), 'Omi');
    expect(names.forSegment(segments[1]), 'Speaker 1');
  });

  test('an unknown person id falls back to Speaker N; an explicit person wins', () {
    final segments = [seg(3, personId: 'gone')];
    final names = SpeakerNames.forSegments(segments, l10n: en);
    expect(names.forSegment(segments[0]), 'Speaker 1');
    expect(names.forSegment(segments[0], person: person('x', 'Grace')), 'Grace');
  });

  test('owner name replaces "You" only when given', () {
    final segments = [seg(0, isUser: true)];
    expect(SpeakerNames.forSegments(segments, l10n: en).forSegment(segments[0]), 'You');
    expect(SpeakerNames.forSegments(segments, ownerName: 'Dana', l10n: en).forSegment(segments[0]), 'Dana');
    expect(SpeakerNames.forSegments(segments, ownerName: '  ', l10n: en).forSegment(segments[0]), 'You');
  });

  test('getDisplaySpeakerId matches the resolver', () {
    final segments = [seg(0, isUser: true), seg(5), seg(9)];
    expect(TranscriptSegment.getDisplaySpeakerId(5, segments), 1);
    expect(TranscriptSegment.getDisplaySpeakerId(9, segments), 2);
    expect(TranscriptSegment.getDisplaySpeakerId(11, segments), 3, reason: 'unseen ids number after the known ones');
  });

  group('export (segmentsAsString)', () {
    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    tearDown(() => Intl.defaultLocale = null);

    test('uses the same names as the screen, localized, owner by given name', () {
      final segments = [
        seg(0, isUser: true, text: 'Hello'),
        seg(3, text: 'Hi'),
        seg(omiSpeakerId, text: 'Noted'),
      ];
      final de = lookupAppLocalizations(const Locale('de'));
      final out = TranscriptSegment.segmentsAsString(segments, l10n: de, ownerName: 'Dana', people: const []);
      expect(out, contains('Dana: Hello'));
      expect(out, contains('${de.speakerWithId('1')}: Hi'));
      expect(out, contains('Omi: Noted'));
      expect(out, isNot(contains('Speaker 100')));
      expect(out, isNot(contains('User:')));
    });

    test('defaults: localized "You" from the app locale when no given name is set', () {
      Intl.defaultLocale = 'fr';
      final segments = [seg(0, isUser: true, text: 'Salut'), seg(2, text: 'Bonjour')];
      final fr = lookupAppLocalizations(const Locale('fr'));
      final out = TranscriptSegment.segmentsAsString(segments);
      expect(out, contains('${fr.you}: Salut'));
      expect(out, contains('${fr.speakerWithId('1')}: Bonjour'));
    });

    test('a slice keeps the whole conversation\'s numbering when told', () {
      final all = [seg(1, text: 'a'), seg(2, text: 'b')];
      final out = TranscriptSegment.segmentsAsString([all[1]], l10n: en, numberingSegments: all, people: const []);
      expect(out, 'Speaker 2: b');
    });
  });
}
