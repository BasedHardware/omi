import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/speaker_names.dart';
import 'package:omi/ui/format/diarization_label.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_meta.dart';
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

Person person(String id, String name) =>
    Person(id: id, name: name, createdAt: DateTime(2026), updatedAt: DateTime(2026));

/// One speaker vocabulary on every surface: "You", people's names, "Omi", and dense "Speaker N".
void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  test('on-device engines carry no speaker label in UI or transcript exports', () {
    final segment = seg(0, text: 'Synthetic speech.')..sttProvider = 'on_device:parakeet_v2';
    expect(SpeakerNames.forSegments([segment], l10n: en).forSegment(segment), '');
    expect(TranscriptSegment.segmentsAsString([segment], l10n: en, people: const [], ownerName: 'Test'),
        'Synthetic speech.');
  });

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

  test('live short socket epochs stay unnamed and do not spend ordinals', () {
    final rows = [for (var id = 4; id <= 8; id++) seg(id)];
    final names = SpeakerNames.forSegments(rows, deferShortVoices: true, l10n: en);
    expect(rows.map(names.forSegment).toSet(), {'Speaker'});
    expect(rows.map((r) => r.speakerId).toSet().length, 5);
    final qualified = [...rows, seg(20)..end = 5, seg(21)..end = 5];
    final next = SpeakerNames.forSegments(qualified, deferShortVoices: true, l10n: en);
    expect(qualified.take(5).map(next.forSegment).toSet(), {'Speaker'});
    expect(qualified.skip(5).map(next.forSegment), ['Speaker 1', 'Speaker 2']);
    expect(next.anonymousName(50), 'Speaker', reason: 'new arrivals have no evidence yet');
  });

  test('live evidence pools short turns once and allocates in qualification order', () {
    final first = seg(4)..end = 2.5;
    final second = seg(4)
      ..start = 3
      ..end = 5.5;
    final substantial = seg(8)..end = 5;
    final rows = [first, substantial, second];
    final names = SpeakerNames.forSegments(rows, deferShortVoices: true, l10n: en);
    expect(names.forSegment(substantial), 'Speaker 1');
    expect(names.forSegment(first), 'Speaker 2');
    final repeats = [
      first,
      seg(4)..end = 4.99,
      seg(9)
        ..start = -1
        ..end = -1
    ];
    final pending = SpeakerNames.forSegments(repeats, deferShortVoices: true, l10n: en);
    expect(repeats.map(pending.forSegment).toSet(), {'Speaker'});
  });

  test('live deferral preserves owner and manual names without guessing another owner', () {
    final rows = [seg(4, isUser: true), seg(5, personId: 'ada'), seg(6), seg(7, isUser: true)];
    final names = SpeakerNames.forSegments(rows, people: [person('ada', 'Ada')], deferShortVoices: true, l10n: en);
    expect(rows.map(names.forSegment), ['You', 'Ada', 'Speaker', 'You']);
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

  test('unresolved chunk ids do not appear as dozens of people', () {
    final segments = [seg(0, isUser: true), seg(27), seg(28, personId: 'p1'), seg(30)];
    final names = SpeakerNames.forSegments(segments, people: [person('p1', 'Ada')], unresolved: true, l10n: en);
    expect(segments.map(names.forSegment), ['You', 'Speaker', 'Ada', 'Speaker']);
    expect(names.anonymousName(27), 'Speaker');
    expect(names.anonymousName(30), 'Speaker');
  });

  test('unresolved keeps Omi and falls back on a missing or blank name', () {
    final segments = [seg(omiSpeakerId), seg(27, personId: 'gone'), seg(28, personId: 'blank')];
    final names = SpeakerNames.forSegments(segments, people: [person('blank', '  ')], unresolved: true, l10n: en);
    expect(segments.map(names.forSegment), ['Omi', 'Speaker', 'Speaker']);
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

  test('raw 378/379 never become labels, including old Review responses', () {
    final rows = [seg(378), seg(379)];
    final names = SpeakerNames.forSegments(rows, l10n: en);
    expect(rows.map(names.forSegment), ['Speaker 1', 'Speaker 2']);
    expect(SpeakerNames.excerptLabel(isUser: false, speakerLabel: 'Speaker 379', l10n: en), 'Speaker');
    expect(SpeakerNames.excerptLabel(isUser: false, speakerLabel: 'Speaker B', l10n: en), 'Speaker 2');
    expect(SpeakerNames.excerptLabel(isUser: false, speakerLabel: 'Others', l10n: en), 'Others');
    expect(SpeakerNames.excerptLabel(isUser: false, speakerLabel: 'Unknown speaker', l10n: en), 'Speaker');
    expect(() => '${DiarizationLabel.fromRaw(379)}', throwsUnsupportedError);
    expect(DiarizationLabel.fromRaw(379).rawForTransport, 379);
  });

  test('over-split tiny voices collapse, substantial and named voices stay', () {
    final rows = [seg(378)..end = 30, for (var id = 400; id < 417; id++) seg(id), seg(379, personId: 'ada')];
    final names = SpeakerNames.forSegments(rows, people: [person('ada', 'Ada')], l10n: en);
    expect(names.forSegment(rows.first), 'Speaker 1');
    expect(rows.skip(1).take(17).map(names.forSegment).toSet(), {'Others'});
    expect(names.forSegment(rows.last), 'Ada');
  });

  test('resolved over-split headers omit a numeric people count', () {
    final rows = [seg(0, isUser: true), for (var id = 378; id < 395; id++) seg(id)];
    final meta = ConversationDetailMeta.participants(rows,
        you: 'You',
        speakers:
            ConversationSpeakers(status: 'resolved', participantSpeakerIds: [for (var id = 378; id < 395; id++) id]));
    expect(meta.named, ['You']);
    expect(meta.unnamed, 0);
    expect(meta.uncounted, isTrue);
  });

  group('export (segmentsAsString)', () {
    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    tearDown(() => Intl.defaultLocale = null);

    test('uses the same names as the screen, localized, owner by given name', () {
      final segments = [seg(0, isUser: true, text: 'Hello'), seg(3, text: 'Hi'), seg(omiSpeakerId, text: 'Noted')];
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

    test('an unavailable resolution exports the neutral "Speaker" label', () async {
      final now = DateTime.now();
      SharedPreferences.setMockInitialValues({
        'cachedPeople': [
          jsonEncode({
            'id': 'p1',
            'name': 'Ada',
            'created_at': now.toUtc().toIso8601String(),
            'updated_at': now.toUtc().toIso8601String(),
          }),
        ],
      });
      await SharedPreferencesUtil.init();

      final conversation = ServerConversation(
        id: 'c-export',
        createdAt: DateTime(2026),
        structured: Structured('Title', 'Summary'),
        transcriptSegments: [
          seg(0, isUser: true, text: 'Mine'),
          seg(27, text: 'Unsure voice'),
          seg(28, personId: 'p1', text: 'Known voice'),
        ],
        speakerResolution: const ConversationSpeakers(status: 'unavailable'),
      );
      final out = conversation.getTranscript();

      expect(out, contains('You: Mine'));
      expect(out, contains('Ada: Known voice'));
      expect(out, contains('Speaker: Unsure voice'));
      expect(out, isNot(contains('Speaker ?')));
      expect(out, isNot(contains('Speaker 1')));
    });
  });
}
