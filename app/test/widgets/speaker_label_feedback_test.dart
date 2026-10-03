import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/widgets/carried_speaker_banner.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/earlier_voice_matches_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/speaker_label_badge.dart';

Person _person(String id, String name, {String voice = 'unknown'}) =>
    Person(id: id, name: name, createdAt: DateTime(2026), updatedAt: DateTime(2026), voiceLearningState: voice);

TranscriptSegment _line(String id, int speaker, {bool isUser = false, String? personId, String? source}) =>
    TranscriptSegment(
      id: id,
      text: 'speech',
      speaker: 'SPEAKER_$speaker',
      isUser: isUser,
      personId: personId,
      translations: [],
      start: 0,
      end: 1,
      speakerLabelSource: source,
    );

Widget _app(Widget child, {List<Person> people = const []}) => ChangeNotifierProvider.value(
      value: PeopleProvider()..people = people,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: child),
      ),
    );

PersonVoiceMatch _match(String conversationId) => PersonVoiceMatch(
      conversationId: conversationId,
      title: 'Lunch planning',
      startedAt: DateTime(2026, 9, 30, 12),
      speakerId: 2,
      talkSeconds: 840,
      segmentIds: const ['e1'],
      clipStart: 1,
      clipEnd: 9,
      matchLevel: 'strong',
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('label provenance', () {
    test('wire field survives the generated round trip', () {
      final json = _line('a', 1, personId: 'p', source: 'auto').toJson();
      expect(json['speaker_label_source'], 'auto');
      expect(TranscriptSegment.fromJson(json).speakerLabelSource, 'auto');
      expect(TranscriptSegment.fromJson(json..remove('speaker_label_source')).speakerLabelSource, isNull);
    });

    test('asks once per automatically named voice, never for the owner, a manual label or no label', () {
      final ids = firstAutoLabelSegmentIds([
        _line('owner', 0, isUser: true, source: 'auto'),
        _line('manual', 1, personId: 'maya', source: 'manual'),
        _line('auto-1', 2, personId: 'jordan', source: 'auto'),
        _line('auto-2', 2, personId: 'jordan', source: 'auto'),
        _line('unnamed', 3),
        _line('auto-other-voice', 4, personId: 'jordan', source: 'auto'),
        _line('carried', 5, personId: 'maya', source: 'carried'),
      ]);
      expect(ids, {'auto-1', 'auto-other-voice'});
    });

    testWidgets('a check for the user\'s own answer, Likely for a guess, nothing for an unnamed voice', (tester) async {
      await tester.pumpWidget(
        _app(
          const Column(
            children: [
              SpeakerLabelBadge(source: 'manual'),
              SpeakerLabelBadge(source: 'carried'),
              SpeakerLabelBadge(source: 'auto'),
              SpeakerLabelBadge(source: null),
            ],
          ),
        ),
      );
      expect(find.byKey(const Key('speaker_label_confirmed')), findsNWidgets(2));
      expect(find.byKey(const Key('speaker_label_likely')), findsOneWidget);
      expect(find.text('Likely'), findsOneWidget);
    });

    testWidgets('the question names the person on both answers', (tester) async {
      var yes = 0, not = 0;
      await tester.pumpWidget(_app(SpeakerLikelyConfirm(name: 'Jordan Lee', onYes: () => yes++, onNot: () => not++)));
      // Two light chips, no boxed question: the "Likely" badge asks, and screen readers hear it.
      expect(find.text('Sounds like Jordan Lee'), findsNothing);
      expect(find.bySemanticsLabel('Sounds like Jordan Lee'), findsOneWidget);
      expect(find.byType(OmiFilterChip), findsNWidgets(2));
      await tester.tap(find.text('Yes'));
      await tester.tap(find.text('Not Jordan Lee'));
      expect((yes, not), (1, 1));
    });
  });

  group('rejecting a label', () {
    ServerConversation conversation() => ServerConversation(
          id: 'c',
          createdAt: DateTime(2026),
          structured: Structured('Title', 'Summary'),
          status: ConversationStatus.completed,
          transcriptSegments: [
            _line('a', 1, personId: 'jordan', source: 'auto'),
            _line('b', 1, personId: 'jordan', source: 'auto'),
            _line('c', 2, personId: 'jordan', source: 'manual'),
            _line('d', 0, isUser: true, source: 'auto'),
          ],
        );

    ConversationDetailProvider provider(ServerConversation value, SpeakerRejectionCall reject) {
      final provider = ConversationDetailProvider(rejectSpeaker: reject)..selectedDate = value.createdAt;
      provider.setCachedConversation(value);
      return provider;
    }

    test('clears every line of that voice with that label and sends the rejected person', () async {
      final value = conversation();
      final calls = <(String, int, SpeakerRejection, String?, List<String>?)>[];
      final detail = provider(value, (id, speakerId, kind, {personId, segmentIds}) async {
        calls.add((id, speakerId, kind, personId, segmentIds));
        return ApiSuccess(value);
      });

      expect(await detail.rejectSpeakerLabel(value.transcriptSegments.first, SpeakerRejection.notPerson), isTrue);

      final (id, speakerId, kind, personId, segmentIds) = calls.single;
      expect((id, speakerId, kind, personId), ('c', 1, SpeakerRejection.notPerson, 'jordan'));
      expect(segmentIds, ['a', 'b']);
      expect(value.transcriptSegments.map((s) => s.personId), [null, null, 'jordan', null]);
      expect(value.transcriptSegments.map((s) => s.speakerLabelSource), [null, null, 'manual', 'auto']);
    });

    test('"Not Me" clears the owner label without naming a person', () async {
      final value = conversation();
      String? sentPerson = 'unset';
      final detail = provider(value, (_, __, ___, {personId, segmentIds}) async {
        sentPerson = personId;
        return ApiSuccess(value);
      });

      expect(await detail.rejectSpeakerLabel(value.transcriptSegments.last, SpeakerRejection.notMe), isTrue);

      expect(sentPerson, isNull);
      expect(value.transcriptSegments.last.isUser, isFalse);
    });

    test('rejection clears other identities on the same scoped voice', () async {
      final value = conversation();
      value.transcriptSegments[2].speakerId = 1;
      value.transcriptSegments[2].personId = 'maya';
      final detail = provider(value, (_, __, ___, {personId, segmentIds}) async {
        final authoritative = ServerConversation.fromJson(value.toJson());
        for (final s in authoritative.transcriptSegments.where((s) => s.speakerId == 1)) {
          s.personId = null;
          s.isUser = false;
          s.speakerLabelSource = null;
        }
        return ApiSuccess(authoritative);
      });
      expect(await detail.rejectSpeakerLabel(value.transcriptSegments.first, SpeakerRejection.notPerson), isTrue);
      expect(detail.conversation.transcriptSegments.take(3).map((s) => s.personId), [null, null, null]);
      detail.dispose();
    });

    test('a refused rejection restores the label and how it was made', () async {
      final value = conversation();
      final detail = provider(
        value,
        (_, __, ___, {personId, segmentIds}) async =>
            const ApiFailure<ServerConversation>(ApiProblem(ApiProblemKind.transport)),
      );

      expect(await detail.rejectSpeakerLabel(value.transcriptSegments.first, SpeakerRejection.notPerson), isFalse);

      expect(value.transcriptSegments.first.personId, 'jordan');
      expect(value.transcriptSegments.first.speakerLabelSource, 'auto');
    });

    test('a later rejection waits for an in-flight assignment', () async {
      final value = conversation();
      final assigned = Completer<bool>();
      final calls = <String>[];
      final detail = ConversationDetailProvider(
        assignSpeaker: (_, __, {isUser, personId, speakerId}) {
          calls.add('assign');
          return assigned.future;
        },
        rejectSpeaker: (_, __, ___, {personId, segmentIds}) async {
          calls.add('reject');
          return ApiSuccess(value);
        },
      )
        ..selectedDate = value.createdAt
        ..setCachedConversation(value);
      final first = detail.assignSpeaker(['a'], 'maya', speakerId: 1);
      await Future<void>.delayed(Duration.zero);
      final rejection = detail.rejectSpeakerLabel(value.transcriptSegments.first, SpeakerRejection.notPerson);
      await Future<void>.delayed(Duration.zero);
      expect(calls, ['assign']);
      assigned.complete(true);
      expect(await first, isTrue);
      expect(await rejection, isTrue);
      expect(calls, ['assign', 'reject']);
      detail.dispose();
    });

    test('a saved tag is the user\'s own answer at once', () async {
      final value = conversation();
      final detail = ConversationDetailProvider(assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true)
        ..selectedDate = value.createdAt
        ..setCachedConversation(value);

      expect(await detail.assignSpeaker(['a'], 'maya', speakerId: 1), isTrue);

      expect(value.transcriptSegments.take(2).map((s) => s.speakerLabelSource), ['manual', 'manual']);
    });

    testWidgets('the tag sheet offers the rejections that fit the line', (tester) async {
      final rejected = <SpeakerRejection>[];
      await tester.pumpWidget(
        _app(
          NameSpeakerBottomSheet(
            speakerId: 1,
            segmentId: 'a',
            segments: [_line('a', 1, personId: 'jordan', source: 'auto')],
            onSpeakerAssigned: (_, __, ___, ____, _____) async => false,
            onSpeakerRejected: (kind) async {
              rejected.add(kind);
              return true;
            },
          ),
          people: [_person('jordan', 'Jordan Lee')],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('name_speaker_not_me')), findsNothing);
      expect(find.text('Not Jordan Lee'), findsOneWidget);
      expect(find.byKey(const Key('name_speaker_not_a_person')), findsOneWidget);

      await tester.tap(find.text('Not Jordan Lee'));
      await tester.pump();
      expect(rejected, [SpeakerRejection.notPerson]);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('the live sheet, which cannot reject, shows no rejections', (tester) async {
      await tester.pumpWidget(
        _app(
          NameSpeakerBottomSheet(
            speakerId: 1,
            segmentId: 'a',
            segments: [_line('a', 1, personId: 'jordan', source: 'auto')],
            onSpeakerAssigned: (_, __, ___, ____, _____) async => false,
          ),
          people: [_person('jordan', 'Jordan Lee')],
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('name_speaker_not_a_person')), findsNothing);
    });
  });

  group('tag outcome', () {
    SpeakerTagOutcomeController controller(List<String> states, {List<PersonVoiceMatch> matches = const []}) {
      var read = 0;
      return SpeakerTagOutcomeController(
        fetchPerson: (id) async {
          final state = states[read < states.length ? read : states.length - 1];
          read++;
          return ApiSuccess(_person(id, 'Maya', voice: state));
        },
        fetchMatches: (_) async => ApiSuccess(matches),
        pollInterval: const Duration(seconds: 1),
        maxPolls: 3,
      );
    }

    test('follows the server until the voice is learned, then looks for earlier matches', () {
      fakeAsync((async) {
        final outcome = controller(['pending', 'learned'], matches: [_match('c1')]);
        outcome.follow(personId: 'maya', personName: 'Maya', linesLabeled: 4);
        expect(outcome.outcome!.voiceState, 'pending');
        expect(outcome.outcome!.linesLabeled, 4);

        async.elapse(const Duration(seconds: 1));
        expect(outcome.outcome!.voiceState, 'pending');
        async.elapse(const Duration(seconds: 1));
        expect(outcome.outcome!.voiceState, 'learned');
        expect(outcome.outcome!.matches, hasLength(1));
        outcome.dispose();
      });
    });

    test('a late saved tag cannot revive a disposed outcome controller', () {
      fakeAsync((async) {
        var reads = 0;
        final outcome = SpeakerTagOutcomeController(
          fetchPerson: (id) async {
            reads++;
            return ApiSuccess(_person(id, 'Maya', voice: 'learned'));
          },
          fetchMatches: (_) async => const ApiSuccess([]),
        );
        outcome.dispose();
        expect(() => outcome.follow(personId: 'maya', personName: 'Maya', linesLabeled: 1), returnsNormally);
        async.elapse(const Duration(seconds: 20));
        expect(reads, 0);
        expect(async.pendingTimers, isEmpty);
      });
    });

    test('a tag still pending when the reads run out is shown as not learned yet', () {
      fakeAsync((async) {
        final outcome = controller(['pending']);
        outcome.follow(personId: 'maya', personName: 'Maya', linesLabeled: 1);
        async.elapse(const Duration(seconds: 5));
        expect(outcome.outcome!.voiceState, 'needs_more_speech');
        expect(outcome.outcome!.matches, isEmpty);
        outcome.dispose();
      });
    });

    test('a voice that was not learned never asks about earlier conversations', () {
      fakeAsync((async) {
        var asked = false;
        final outcome = SpeakerTagOutcomeController(
          fetchPerson: (id) async => ApiSuccess(_person(id, 'Maya', voice: 'disabled')),
          fetchMatches: (_) async {
            asked = true;
            return const ApiSuccess([]);
          },
          pollInterval: const Duration(seconds: 1),
        );
        outcome.follow(personId: 'maya', personName: 'Maya', linesLabeled: 1);
        async.elapse(const Duration(seconds: 2));
        expect(outcome.outcome!.voiceState, 'disabled');
        expect(asked, isFalse);
        outcome.dispose();
      });
    });

    test('a newer tag replaces the one being followed, and closing stops the reads', () {
      fakeAsync((async) {
        var reads = 0;
        final outcome = SpeakerTagOutcomeController(
          fetchPerson: (id) async {
            reads++;
            return ApiSuccess(_person(id, id, voice: 'pending'));
          },
          fetchMatches: (_) async => const ApiSuccess([]),
          pollInterval: const Duration(seconds: 1),
        );
        outcome.follow(personId: 'maya', personName: 'Maya', linesLabeled: 1);
        outcome.follow(personId: 'jordan', personName: 'Jordan', linesLabeled: 2);
        async.elapse(const Duration(seconds: 1));
        expect(outcome.outcome!.personId, 'jordan');
        expect(reads, 1);

        outcome.dismiss();
        async.elapse(const Duration(seconds: 10));
        expect(outcome.outcome, isNull);
        expect(reads, 1);
        outcome.dispose();
      });
    });

    testWidgets('the card says what the tag did and offers Review only with matches', (tester) async {
      var reviewed = 0;
      Future<void> pump(SpeakerTagOutcome outcome) =>
          tester.pumpWidget(_app(SpeakerTagOutcomeCard(outcome: outcome, onClose: () {}, onReview: () => reviewed++)));

      await pump(const SpeakerTagOutcome(personId: 'maya', personName: 'Maya', linesLabeled: 12));
      expect(find.text('Labeled as Maya'), findsOneWidget);
      expect(find.text('Labeled 12 lines'), findsOneWidget);
      expect(find.text('Learning voice…'), findsOneWidget);
      expect(find.byKey(const Key('speaker_tag_outcome_review')), findsNothing);

      await pump(
        SpeakerTagOutcome(
          personId: 'maya',
          personName: 'Maya',
          linesLabeled: 12,
          voiceState: 'learned',
          matches: [_match('c1')],
        ),
      );
      expect(find.text('Voice learned'), findsOneWidget);
      expect(find.text('Omi will recognize Maya next time.'), findsOneWidget);
      expect(find.text('Found in 1 earlier conversation'), findsOneWidget);
      await tester.tap(find.byKey(const Key('speaker_tag_outcome_review')));
      expect(reviewed, 1);

      await pump(
        const SpeakerTagOutcome(
          personId: 'maya',
          personName: 'Maya',
          linesLabeled: 12,
          voiceState: 'needs_more_speech',
        ),
      );
      expect(find.text('Voice not learned yet'), findsOneWidget);
      expect(find.text('Omi needs more clear speech from Maya and will keep trying.'), findsOneWidget);
    });
  });

  group('earlier matches', () {
    testWidgets('each answer is sent once and an answered conversation leaves the list', (tester) async {
      final answers = <(String, bool)>[];
      await tester.pumpWidget(
        _app(
          EarlierVoiceMatchesList(
            personName: 'Maya',
            matches: [_match('c1'), _match('c2')],
            playClip: (_) async => true,
            onAnswer: (match, same) async {
              answers.add((match.conversationId, same));
              return true;
            },
          ),
        ),
      );
      expect(find.textContaining('14m of this voice'), findsNWidgets(2));

      await tester.tap(find.text('Yes').first);
      await tester.pumpAndSettle();
      expect(answers, [('c1', true)]);
      expect(find.byKey(const Key('voice_match_c1_2')), findsNothing);
      expect(find.byKey(const Key('voice_match_c2_2')), findsOneWidget);
    });

    testWidgets('an answer the server refused keeps the conversation in the list', (tester) async {
      await tester.pumpWidget(
        _app(
          EarlierVoiceMatchesList(
            personName: 'Maya',
            matches: [_match('c1')],
            playClip: (_) async => true,
            onAnswer: (_, __) async => false,
          ),
        ),
      );
      await tester.tap(find.text('No'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byKey(const Key('voice_match_c1_2')), findsOneWidget);
      await tester.pump(const Duration(seconds: 9));
    });
  });

  group('carried label', () {
    test('one banner per carried person, in order of appearance', () {
      final carried = carriedSpeakerSegments([
        _line('a', 0, isUser: true, source: 'carried'),
        _line('b', 1, personId: 'maya', source: 'carried'),
        _line('c', 1, personId: 'maya', source: 'carried'),
        _line('d', 2, personId: 'jordan', source: 'manual'),
      ]);
      expect(carried.map((s) => s.id), ['b']);
    });

    testWidgets('names who was carried over and offers Change', (tester) async {
      var changed = 0, closed = 0;
      await tester.pumpWidget(
        _app(CarriedSpeakerBanner(name: 'Maya', onChange: () => changed++, onClose: () => closed++)),
      );
      expect(find.text('Still Maya. Carried over from your last conversation.'), findsOneWidget);
      await tester.tap(find.text('Change'));
      await tester.tap(find.byIcon(Icons.close));
      expect((changed, closed), (1, 1));
    });
  });
}
