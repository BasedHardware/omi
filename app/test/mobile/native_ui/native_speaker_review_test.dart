import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_feedback.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/earlier_voice_matches_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/pages/conversations/widgets/speaker_review_native.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

import '../../helpers/proactivity_fakes.dart';
import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

Person _person(String id, String name, {String confidence = 'likely'}) => Person(
    id: id,
    name: name,
    createdAt: DateTime.utc(2026, 9, 1),
    updatedAt: DateTime.utc(2026, 9, 1),
    confidence: confidence);

GeneratedSpeakerTagPrompt _prompt(String id, String kind, {List<GeneratedSpeakerTagCandidate>? candidates}) =>
    GeneratedSpeakerTagPrompt(
      id: id,
      kind: kind,
      origin: kind == 'confirm_person' ? 'auto_person' : 'unnamed',
      conversationId: 'c1',
      conversationTitle: 'Coffee chat',
      conversationStartedAt: DateTime.utc(2026, 10, 7, 9),
      speakerId: 1,
      segmentIds: const ['s1'],
      clipStart: 0,
      clipEnd: 8,
      excerpt: 'We should ship it on Friday',
      suggestedPersonId: kind == 'confirm_person' ? 'p1' : null,
      suggestedPersonName: kind == 'confirm_person' ? 'Sam' : null,
      candidates: candidates,
    );

/// A 16-bit mono WAV: a 44-byte header, then [samples] rising samples.
Uint8List _wav(int samples) {
  final data = ByteData(44 + samples * 2);
  for (var i = 0; i < samples; i++) {
    data.setInt16(44 + i * 2, (i % 200) * 100, Endian.little);
  }
  return data.buffer.asUint8List();
}

/// The config channel: answers each toast with [toastOutcome] and each presentation from [presentations].
class _Config {
  final toasts = <Map>[];
  final presented = <Map>[];
  final presentations = <Object? Function(Map snapshot)>[];
  String toastOutcome = 'timeout';

  static _Config install() {
    final config = _Config();
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(_config, (call) async {
      switch (call.method) {
        case 'toast':
          config.toasts.add(call.arguments as Map);
          return config.toastOutcome;
        case 'present':
          final snapshot = (call.arguments as Map)['snapshot'] as Map;
          config.presented.add(snapshot);
          return config.presentations[config.presented.length - 1](snapshot);
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
    return config;
  }
}

class _Review {
  _Review(this.provider, this.answers, this.host);
  final SpeakerTagPromptsProvider provider;
  final List<GeneratedSpeakerTagPromptAnswerRequest> answers;
  final NativeTestHost host;
}

Widget _app(Widget home, {List<Person> people = const [], SpeakerTagPromptsProvider? prompts}) => MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
        ChangeNotifierProvider<PeopleProvider>(
            create: (_) => PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))..people = people),
        if (prompts != null) ChangeNotifierProvider.value(value: prompts),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: home),
      ),
    );

Future<_Review> _pumpReview(
  WidgetTester tester,
  List<GeneratedSpeakerTagPrompt> prompts, {
  List<Person> people = const [],
  bool firstTime = false,
}) async {
  final host = NativeTestHost.install();
  final answers = <GeneratedSpeakerTagPromptAnswerRequest>[];
  final provider = SpeakerTagPromptsProvider(
    fetchPrompts: () async => ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: prompts, firstTime: firstTime)),
    markShown: (_) async => ApiSuccess(firstTime),
    dismiss: () async => const ApiSuccess<void>(null),
    submitAnswer: (request) async {
      answers.add(request);
      return ApiSuccess(GeneratedSpeakerTagPromptAnswerResponse(qualityOutcome: 'skipped', personId: request.personId));
    },
    loadClip: (_) async => ApiSuccess(_wav(4000)),
    playClip: (_, __) async => true,
    emit: (_) {},
    answeredHold: Duration.zero,
  );
  addTearDown(provider.dispose);
  await tester.pumpWidget(_app(const NativeSpeakerReview(), people: people, prompts: provider));
  await NativeTestHost.settle(tester);
  return _Review(provider, answers, host);
}

List<NativeRow> _rows(WidgetTester tester) =>
    IosNativeSurface.debugDispatchRows(tester.state(find.byType(IosNativeSurface).last));

Iterable<String> _ids(WidgetTester tester, String prefix) =>
    _rows(tester).map((row) => row.id).where((id) => id.startsWith(prefix));

/// Sends [id] from the newest native view; true when Dart accepted the command.
Future<bool> _send(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  try {
    const StandardMethodCodec().decodeEnvelope(reply!);
    return true;
  } on PlatformException {
    return false;
  }
}

PersonVoiceMatch _match(String conversationId) => PersonVoiceMatch(
    clipEnd: 4,
    clipStart: 0,
    conversationId: conversationId,
    matchLevel: 'close',
    segmentIds: const ['s1'],
    speakerId: 2,
    startedAt: DateTime.utc(2026, 10, 1, 9),
    talkSeconds: 42,
    title: 'Standup $conversationId');

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('native speaker review', () {
    testWidgets('answers follow the prompt kind', (tester) async {
      for (final (kind, expected) in [
        ('confirm_person', ['yes', 'someone', 'skip']),
        ('identify', ['someone', 'skip']),
        ('owner_check', ['me', 'not_me', 'not_a_person', 'skip']),
      ]) {
        await _pumpReview(tester, [_prompt('q-$kind', kind)], people: [_person('p1', 'Sam')]);
        expect(find.byType(UiKitView), findsOneWidget, reason: '$kind renders natively');
        expect(_ids(tester, 'speaker_review_answer:').map((id) => id.split(':').last), expected, reason: kind);
        expect(_rows(tester).every((row) => row.valid), isTrue);
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('the waveform is absent until the clip plays, then carries 40 valid bars', (tester) async {
      final review = await _pumpReview(tester, [_prompt('q1', 'identify')]);
      expect(_ids(tester, 'speaker_review_wave'), isEmpty);
      expect(_rows(tester).firstWhere((row) => row.id == 'speaker_review_play').symbol, 'play.fill');

      expect(await _send(tester, review.host, 'speaker_review_play'), isTrue);
      await NativeTestHost.settle(tester);

      final wave = _rows(tester).firstWhere((row) => row.id == 'speaker_review_wave');
      expect(wave.kind, 'waveform');
      expect(wave.points, hasLength(40));
      expect(wave.valid, isTrue);
      expect(wave.points.every((point) => (point['y'] as double) >= 0 && (point['y'] as double) <= 1), isTrue);
    });

    testWidgets('each answer button sends its answer through the provider', (tester) async {
      NativeFeedbackHost.debugActiveForTest = true;
      addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
      _Config.install();
      for (final (kind, id, wire) in [
        ('confirm_person', 'yes', 'person'),
        ('owner_check', 'not_me', 'not_me'),
        ('owner_check', 'not_a_person', 'not_a_person'),
        ('identify', 'skip', 'skip'),
      ]) {
        final review = await _pumpReview(tester, [_prompt('q-$id', kind)], people: [_person('p1', 'Sam')]);
        expect(await _send(tester, review.host, 'speaker_review_answer:$id'), isTrue);
        await NativeTestHost.settle(tester);
        await tester.pumpAndSettle();
        expect(review.answers.single.answer, wire, reason: id);
        if (id == 'yes') expect(review.answers.single.personId, 'p1');
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('a candidate index answers with the projected candidate; a stale index is refused', (tester) async {
      NativeFeedbackHost.debugActiveForTest = true;
      addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
      final config = _Config.install();
      final review = await _pumpReview(tester, [
        _prompt('q1', 'identify', candidates: const [
          GeneratedSpeakerTagCandidate(personId: 'p1', name: 'Ada', matchLevel: 3, pinned: true),
          GeneratedSpeakerTagCandidate(personId: 'p2', name: 'Grace', matchLevel: 9, pinned: false),
        ]),
      ]);
      final candidates = _rows(tester).where((row) => row.id.startsWith('speaker_review_candidate:')).toList();
      expect(candidates.map((row) => row.title), ['Ada', 'Grace']);
      expect(candidates.first.symbol, 'pin');
      expect(candidates.last.level, 3, reason: 'out-of-range match levels are clamped');

      expect(await _send(tester, review.host, 'speaker_review_candidate:7'), isFalse);
      expect(review.provider.pending, isNull);
      // A projection of an earlier prompt answers nothing once the prompt moved on.
      final earlier = _rows(tester);
      final current = review.provider.current;
      review.provider.prompts = [_prompt('q0', 'identify'), ...review.provider.prompts];
      expect(review.provider.current, isNot(same(current)));
      await earlier.firstWhere((row) => row.id == 'speaker_review_candidate:0').action!(null);
      expect(review.provider.pending, isNull);
      review.provider.prompts = review.provider.prompts.sublist(1);
      await NativeTestHost.settle(tester);

      expect(await _send(tester, review.host, 'speaker_review_candidate:1'), isTrue);
      await NativeTestHost.settle(tester);
      expect(config.toasts, hasLength(1), reason: 'the Undo toast is native');
      expect(review.answers.single.personId, 'p2');
      await tester.pumpAndSettle();
    });

    testWidgets('Undo from the native toast drops the staged answer and never commits it', (tester) async {
      NativeFeedbackHost.debugActiveForTest = true;
      addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
      final config = _Config.install()..toastOutcome = 'action';
      final review = await _pumpReview(tester, [_prompt('q1', 'owner_check')]);

      expect(await _send(tester, review.host, 'speaker_review_answer:me'), isTrue);
      await NativeTestHost.settle(tester);

      expect(config.toasts.single['kind'], 'undo');
      expect(review.provider.pending, isNull, reason: 'undoPending ran');
      expect(review.answers, isEmpty, reason: 'commitPending never ran');
      expect(_ids(tester, 'speaker_review_answer:'), isNotEmpty, reason: 'the question is back');
    });

    testWidgets('a second answer from the same projection never drops the staged one', (tester) async {
      NativeFeedbackHost.debugActiveForTest = true;
      addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
      final config = _Config.install();
      final review = await _pumpReview(tester, [_prompt('q1', 'owner_check'), _prompt('q2', 'identify')]);
      final question = _rows(tester);
      NativeRow row(String id) => question.firstWhere((row) => row.id == 'speaker_review_answer:$id');

      // Both taps land before the answered snapshot replaces the question.
      await row('me').action!(null);
      await row('skip').action!(null);
      expect(review.provider.pending?.answer, SpeakerTagAnswer.me);
      expect(review.provider.current?.id, 'q1', reason: 'skip did not advance past the staged answer');
      await NativeTestHost.settle(tester);
      await tester.pumpAndSettle();

      expect(config.toasts, hasLength(1), reason: 'one Undo toast, for the staged answer');
      expect(review.answers.map((request) => request.answer), ['me'], reason: 'committed, and no skip was sent');
    });

    testWidgets("'Someone else' is refused while an answer is staged", (tester) async {
      NativeFeedbackHost.debugActiveForTest = true;
      addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
      _Config.install();
      final review = await _pumpReview(tester, [_prompt('q1', 'identify')]);
      final someone = _rows(tester).firstWhere((row) => row.id == 'speaker_review_answer:someone');
      review.provider.stage(SpeakerTagAnswer.notMe);
      await someone.action!(null);
      await tester.pumpAndSettle();
      expect(find.byType(BottomSheet), findsNothing, reason: 'no picker over a staged answer');
      expect(review.provider.pending?.answer, SpeakerTagAnswer.notMe);
    });

    testWidgets('the answered state shows the confidence meter of the person while staged', (tester) async {
      NativeFeedbackHost.debugActiveForTest = true;
      addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
      _Config.install();
      final review = await _pumpReview(tester, [_prompt('q1', 'confirm_person'), _prompt('q2', 'identify')],
          people: [_person('p1', 'Sam', confidence: 'confirmed')], firstTime: true);
      expect(_rows(tester).firstWhere((row) => row.id == 'speaker_review_header').subtitle, '1 of 2');
      expect(_ids(tester, 'speaker_review_save_voices'), hasLength(1));

      review.provider.stage(SpeakerTagAnswer.person, personId: 'p1', displayName: 'Sam');
      await NativeTestHost.settle(tester);
      final answered = _rows(tester).firstWhere((row) => row.id == 'speaker_review_answered');
      expect(answered.level, 3);
      expect(answered.symbol, isNot('checkmark.circle.fill'));
      expect(_ids(tester, 'speaker_review_answer:'), isEmpty);
    });
  });

  group('native speaker picker', () {
    Future<Future<SpeakerPickerChoice?>> openPicker(WidgetTester tester, NativeSpeakerPicker picker) async {
      late BuildContext context;
      await tester.pumpWidget(_app(Builder(builder: (inner) {
        context = inner;
        return const SizedBox();
      })));
      final result = Navigator.of(context).push<SpeakerPickerChoice>(MaterialPageRoute(builder: (_) => picker));
      await NativeTestHost.settle(tester);
      await tester.pumpAndSettle();
      return result;
    }

    NativeSpeakerPicker picker({bool offer = true}) => NativeSpeakerPicker(
          candidates: const [
            GeneratedSpeakerTagCandidate(personId: 'p1', name: 'Sam', matchLevel: 3, pinned: false),
            GeneratedSpeakerTagCandidate(personId: 'p2', name: 'Ada', matchLevel: 2, pinned: true),
          ],
          people: [
            _person('p1', 'Sam'),
            _person('p2', 'Ada'),
            _person('p3', 'Zoe'),
            _person('p4', 'Bea'),
            _person('optimistic-person:1', 'Pending'),
          ],
          excludePersonId: 'p1',
          offerMeAndNotAPerson: offer,
          fallback: const Text('flutter picker'),
        );

    testWidgets('excludes the ruled-out person and optimistic people, and picks by person id', (tester) async {
      final host = NativeTestHost.install();
      final result = await openPicker(tester, picker());
      final titles = _rows(tester).map((row) => row.title).toList();
      expect(titles, isNot(contains('Sam')));
      expect(titles, isNot(contains('Pending')));
      expect(_ids(tester, 'speaker_picker_closest:'), ['speaker_picker_closest:p2']);
      expect(_rows(tester).firstWhere((row) => row.id == 'speaker_picker_closest:p2').subtitle,
          '${_l10n.peopleFilterPinned}, ${_l10n.voiceMatchMeterLabel(_l10n.voiceMatchPossible)}');
      expect(_rows(tester).where((row) => row.id.startsWith('speaker_picker_person:')).map((row) => row.title),
          ['Bea', 'Zoe']);
      expect(_ids(tester, 'speaker_picker_me'), hasLength(1));

      // Rows are keyed by person id, so a filter change between projection and tap never redirects it.
      expect(await _send(tester, host, '_search', 'zo'), isTrue);
      await NativeTestHost.settle(tester);
      expect(await _send(tester, host, 'speaker_picker_person:p3'), isTrue);
      await tester.pumpAndSettle();
      final choice = await result;
      expect(choice?.personId, 'p3');
      expect(choice?.displayName, 'Zoe');
    });

    testWidgets("Add '<query>' only for 2 to 40 characters that match nobody exactly", (tester) async {
      final host = NativeTestHost.install();
      final result = await openPicker(tester, picker());
      String addTitle() => _rows(tester).firstWhere((row) => row.id == 'speaker_picker_new_person').title;

      for (final (query, title) in [
        ('M', _l10n.newPersonEllipsis),
        ('zoe', _l10n.newPersonEllipsis),
        ('x' * 41, _l10n.newPersonEllipsis),
        ('  M  ', _l10n.newPersonEllipsis),
        ('Al', _l10n.addNamedPersonAction('Al')),
        ('x' * 40, _l10n.addNamedPersonAction('x' * 40)),
        ('Maya', _l10n.addNamedPersonAction('Maya')),
      ]) {
        expect(await _send(tester, host, '_search', query), isTrue);
        await NativeTestHost.settle(tester);
        expect(addTitle(), title, reason: query);
      }
      expect(_ids(tester, 'speaker_picker_me'), isEmpty, reason: 'quick answers hide while searching');
      expect(await _send(tester, host, 'speaker_picker_new_person'), isTrue);
      await tester.pumpAndSettle();
      expect((await result)?.name, 'Maya');
    });

    testWidgets('the native name loop re-asks for blank or short names and refuses over-length input', (tester) async {
      NativeTestHost.install();
      final config = _Config.install();
      late BuildContext context;
      await tester.pumpWidget(_app(Builder(builder: (inner) {
        context = inner;
        return const SizedBox();
      })));
      Map save(String name) => {
            'action': 'save',
            'values': {'name': name}
          };
      // 40 characters the field accepts, but 42 UTF-16 units: over the same limit _NameDialog applies.
      config.presentations
          .addAll([(_) => save('   '), (_) => save('A'), (_) => save('${'x' * 38}👍👍'), (_) => save(' Maya ')]);
      final named = showSpeakerTagNameDialog(context);
      await tester.pumpAndSettle();
      expect(await named, 'Maya');
      List<Map> rows(Map snapshot) =>
          [for (final section in (snapshot['sections'] as List).cast<Map>()) ...(section['rows'] as List).cast<Map>()];
      expect(rows(config.presented[0]).map((row) => row['id']), ['name']);
      expect(rows(config.presented[1]).last['title'], _l10n.pleaseEnterName);
      expect(rows(config.presented[2]).last['title'], _l10n.nameMustBeBetweenCharacters);
      expect(rows(config.presented[3]).last['title'], _l10n.nameMustBeBetweenCharacters);
      expect(rows(config.presented[0]).first['maximumLength'], 40);

      config.presentations.add((_) => save('x' * 41));
      final tooLong = showSpeakerTagNameDialog(context);
      await tester.pumpAndSettle();
      expect(await tooLong, isNull, reason: 'a value the 40-character field would refuse names nobody');
    });
  });

  group('native earlier voice matches', () {
    testWidgets('one section per open match; answers resolve the current match and the sheet pops at the end',
        (tester) async {
      final host = NativeTestHost.install();
      final matches = [_match('a'), _match('b'), _match('c')];
      final answered = <(PersonVoiceMatch, bool)>[];
      final played = <PersonVoiceMatch>[];
      late BuildContext context;
      await tester.pumpWidget(_app(Builder(builder: (inner) {
        context = inner;
        return const SizedBox();
      })));
      final closed = Navigator.of(context).push<void>(MaterialPageRoute(
          builder: (_) => EarlierVoiceMatchesList(
                personName: 'Maya',
                matches: matches,
                native: true,
                onAnswer: (match, same) async {
                  answered.add((match, same));
                  return true;
                },
                playClip: (match) async {
                  played.add(match);
                  return true;
                },
              )));
      await NativeTestHost.settle(tester);
      await tester.pumpAndSettle();

      final ids = _rows(tester).map((row) => row.id).toList();
      expect(ids.toSet(), hasLength(ids.length));
      expect(_ids(tester, 'voice_match_yes:'), ['voice_match_yes:0', 'voice_match_yes:1', 'voice_match_yes:2']);

      expect(await _send(tester, host, 'voice_match_play:2'), isTrue);
      expect(played.single, same(matches[2]));

      expect(await _send(tester, host, 'voice_match_yes:1'), isTrue);
      await tester.pumpAndSettle();
      expect(answered.single.$1, same(matches[1]));
      expect(answered.single.$2, isTrue);
      expect(_ids(tester, 'voice_match_yes:'), ['voice_match_yes:0', 'voice_match_yes:2'],
          reason: 'ids stay the original positions, never shifting to another match');

      // A tap from the snapshot that still showed 'b' is a no-op, not an answer for 'c'.
      expect(await _send(tester, host, 'voice_match_no:1'), isFalse);
      expect(answered, hasLength(1));

      expect(await _send(tester, host, 'voice_match_no:2'), isTrue);
      await tester.pumpAndSettle();
      expect(answered.last.$1, same(matches[2]));
      expect(answered.last.$2, isFalse);
      expect(await _send(tester, host, 'voice_match_yes:0'), isTrue);
      await tester.pumpAndSettle();
      expect(answered.map((answer) => answer.$1), [matches[1], matches[2], matches[0]]);
      await closed;
      expect(find.byType(EarlierVoiceMatchesList), findsNothing);
    });
  });

  group('native earlier voice matches saving', () {
    testWidgets('while an answer saves, Yes says so and both answers are disabled; a failure keeps the match',
        (tester) async {
      final host = NativeTestHost.install();
      final matches = [_match('a'), _match('b')];
      final pending = Completer<bool>();
      var calls = 0;
      await tester.pumpWidget(_app(EarlierVoiceMatchesList(
        personName: 'Maya',
        matches: matches,
        native: true,
        onAnswer: (match, same) {
          calls++;
          return pending.future;
        },
      )));
      await NativeTestHost.settle(tester);
      NativeRow row(String id) => _rows(tester).firstWhere((row) => row.id == id);
      expect(_rows(tester).where((row) => row.id.startsWith('voice_match_when:')), hasLength(2));
      final sections = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).sections;
      expect(sections.map((section) => section.footer.isNotEmpty), [true, false]);

      expect(await _send(tester, host, 'voice_match_yes:0'), isTrue);
      await NativeTestHost.settle(tester);
      expect(row('voice_match_yes:0').subtitle, _l10n.saving);
      expect(row('voice_match_yes:0').projection['enabled'], isFalse);
      expect(row('voice_match_no:0').projection['enabled'], isFalse);
      expect(await _send(tester, host, 'voice_match_no:0'), isFalse);
      expect(calls, 1);

      pending.complete(false);
      await tester.pumpAndSettle();
      expect(row('voice_match_yes:0').subtitle, isEmpty);
      expect(_ids(tester, 'voice_match_yes:'), ['voice_match_yes:0', 'voice_match_yes:1']);
    });
  });

  group('native transcript heading', () {
    var published = <NativeSection>[];
    TranscriptSegment segment(String id, int speakerId, {bool isUser = false, String? personId}) => TranscriptSegment(
          id: id,
          text: 'speech $id',
          speaker: 'SPEAKER_0$speakerId',
          speakerId: speakerId,
          isUser: isUser,
          personId: personId,
          start: speakerId * 5.0,
          end: speakerId * 5.0 + 4,
          translations: const [],
        );

    Future<List<NativeRow>> project(WidgetTester tester, ConversationSpeakers speakers, {bool named = false}) async {
      final conversation = ServerConversation(
        id: 'c-native-heading',
        createdAt: DateTime(2026, 9, 30, 12),
        structured: Structured('Title', 'Summary'),
        status: ConversationStatus.completed,
        transcriptSegments: [
          segment('own', 0, isUser: true),
          segment('a', 1, personId: named ? 'p1' : null),
          segment('b', 2, personId: 'p1')
        ],
        speakerResolution: speakers,
      );
      final detail = ConversationDetailProvider(fetchConversation: (_) async => conversation)
        ..selectedDate = conversation.createdAt
        ..setCachedConversation(conversation);
      addTearDown(detail.dispose);
      var sections = <NativeSection>[];
      final people = [_person('p1', 'Ada')];
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider<PeopleProvider>.value(
              value: PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))..people = people),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidgets(onNativePresentation: (value) => sections = value)),
        ),
      ));
      await tester.pumpAndSettle();
      published = sections;
      return sections.expand((section) => section.rows).toList();
    }

    String flutterHeading(WidgetTester tester) => tester
        .widgetList<Text>(
            find.descendant(of: find.byKey(const Key('conversation_transcript_heading')), matching: find.byType(Text)))
        .map((text) => text.data ?? '')
        .join();

    testWidgets('the heading matches the Flutter heading and its count', (tester) async {
      final rows = await project(tester, const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [1, 2]));
      final heading = rows.firstWhere((row) => row.id == 'detail_transcript_heading');
      expect(heading.title, flutterHeading(tester));
      expect(heading.title, 'Transcript · 3 speakers');
      expect(heading.valid, isTrue);
      expect(rows.where((row) => row.id == 'detail_unresolved_notice'), isEmpty);
      // The heading row says "Transcript"; a section header saying it again would repeat it.
      expect(published.single.title, isEmpty);
    });

    testWidgets('no unresolved notice when every other voice is named', (tester) async {
      final rows = await project(tester, const ConversationSpeakers(status: 'unavailable'), named: true);
      expect(rows.where((row) => row.id == 'detail_unresolved_notice'), isEmpty);
      expect(find.byKey(const Key('transcript_unresolved_speakers_notice')), findsNothing);
    });

    testWidgets('the unresolved-speakers notice appears only with an unnamed voice and opens the explanation',
        (tester) async {
      final rows = await project(tester, const ConversationSpeakers(status: 'unavailable'));
      expect(rows.firstWhere((row) => row.id == 'detail_transcript_heading').title, flutterHeading(tester));
      final notice = rows.firstWhere((row) => row.id == 'detail_unresolved_notice');
      expect(notice.symbol, 'info.circle');
      expect(find.byKey(const Key('transcript_unresolved_speakers_notice')), findsOneWidget);

      notice.action!(null);
      await tester.pumpAndSettle();
      expect(find.text(_l10n.unresolvedSpeakersTitle), findsOneWidget);
      expect(find.text(_l10n.unresolvedSpeakersMessage), findsOneWidget);
    });
  });

  group('native Home speaker and record actions', () {
    testWidgets("the 'speakers' alert opens the speaker review sheet", (tester) async {
      NativeTestHost.install();
      final provider = SpeakerTagPromptsProvider(
          fetchPrompts: () async =>
              ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: [_prompt('q1', 'identify')])),
          loadClip: (_) async => ApiSuccess(_wav(10)),
          emit: (_) {});
      addTearDown(provider.dispose);
      await provider.loadIfDue();
      final home = GlobalKey();
      await tester.pumpWidget(_app(SizedBox.expand(key: home), prompts: provider));
      final alert = nativeHomeSpeakerReviewAlert(home.currentContext!);
      expect((alert.id, alert.title, alert.symbol), ('speakers', _l10n.speakerTagPromptTitle, 'person.wave.2'));
      unawaited(Future<void>.sync(alert.perform));
      await NativeTestHost.settle(tester);
      // showOmiSheet presents nativeBuilder only on an iOS host (native_speaker_review_host_test drives
      // this alert there); everywhere else the alert keeps the Flutter card in its titled sheet.
      expect(find.byType(SpeakerTagPromptCard), findsOneWidget);
      expect(find.byType(NativeSpeakerReview), findsNothing);
      expect(find.text(_l10n.speakerTagPromptTitle), findsWidgets);
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets("'record' marks the options tip shown before the primary action; 'record_options' opens the options",
        (tester) async {
      final home = GlobalKey();
      await tester.pumpWidget(_app(SizedBox.expand(key: home)));
      final calls = <String>[];
      List<NativeHomeAction> actions({bool phoneRecording = false}) => nativeHomeRecordActions(home.currentContext!,
          phoneRecording: phoneRecording,
          enabled: true,
          primary: () async {
            // Pins the copied key of the private HomeRecordButtonState._optionsTipKey.
            calls.add('primary tip=${SharedPreferencesUtil().getBool('v2/homeRecordOptionsTipShown')}');
          },
          options: () => calls.add('options'));

      expect(actions().map((action) => action.id), ['record', 'record_options']);
      expect(actions(phoneRecording: true).map((action) => action.id), ['record'],
          reason: 'options are offered only while the phone is not recording');
      expect(actions(phoneRecording: true).single.symbol, 'stop.fill');
      expect(SharedPreferencesUtil().getBool('v2/homeRecordOptionsTipShown'), isNot(true));

      await actions().first.perform();
      await actions().last.perform();
      expect(calls, ['primary tip=true', 'options']);
    });
  });

  group('native For You feed', () {
    testWidgets('each card becomes Home actions that keep every card action and the impression record', (tester) async {
      final h = OutcomeHarness();
      addTearDown(h.outbox.dispose);
      await h.bind();
      var feed = <NativeHomeAction>[];
      final opened = <String>[];
      await tester.pumpWidget(_app(HomeForYou(
        outbox: h.outbox,
        load: (_) async => ApiSuccess(feedResponse(items: [feedItem(), feedItem(id: 'item-2')])),
        open: (route, {canOpen}) async {
          opened.add(route);
          return true;
        },
        nativeBuilder: (context, actions) {
          feed = actions;
          return const SizedBox();
        },
      )));
      await tester.pumpAndSettle();
      NativeHomeAction action(String id) => feed.singleWhere((action) => action.id == id);

      expect(feed.map((action) => action.id).take(5),
          ['feed_open:item-1', 'feed_up:item-1', 'feed_down:item-1', 'feed_dismiss:item-1', 'feed_stop:item-1']);
      expect(feed.map((action) => action.id).toSet(), hasLength(10));
      expect(
          action('feed_open:item-1').title, 'For You · Revisit Your Commitment\nYour saved task is ready to revisit.');
      expect(action('feed_dismiss:item-2').title, '${_l10n.dismiss} · Revisit Your Commitment');
      expect(h.events.where((e) => e.action == 'shown'), hasLength(2), reason: 'each projected card counts once');

      await action('feed_up:item-1').perform();
      await tester.pumpAndSettle();
      expect(h.outbox.feedback['item-1'], 'thumbs_up');
      expect(action('feed_up:item-1').symbol, 'hand.thumbsup.fill');
      expect(h.events.where((e) => e.action == 'opened'), isEmpty, reason: 'feedback never opens the card');
      final recorded = h.events.length;
      await action('feed_up:item-1').perform();
      await tester.pumpAndSettle();
      expect(h.events, hasLength(recorded), reason: 'a selected thumb is not recorded again');
      await action('feed_down:item-1').perform();
      await tester.pumpAndSettle();
      expect(h.outbox.feedback['item-1'], 'thumbs_down');

      await action('feed_open:item-1').perform();
      await tester.pumpAndSettle();
      expect(opened, hasLength(1));
      expect(h.events.where((e) => e.action == 'opened'), hasLength(1));

      await action('feed_dismiss:item-2').perform();
      await tester.pumpAndSettle();
      expect(h.events.last.action, 'dismissed');
      expect(feed.where((action) => action.id.endsWith(':item-2')), isEmpty);

      await action('feed_stop:item-1').perform();
      await tester.pumpAndSettle();
      expect(h.events.last.action, 'producer_disabled');
      expect(feed, isEmpty);
      expect(h.events.where((e) => e.action == 'shown'), hasLength(2), reason: 'rebuilds never repeat an impression');
    });

    testWidgets('no impression while the app is not in the foreground', (tester) async {
      final h = OutcomeHarness();
      addTearDown(h.outbox.dispose);
      await h.bind();
      // Inactive still draws frames, so the feed builds while impressions wait for the foreground.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      addTearDown(() => tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed));
      var feed = <NativeHomeAction>[];
      await tester.pumpWidget(_app(HomeForYou(
        outbox: h.outbox,
        load: (_) async => ApiSuccess(feedResponse(items: [feedItem()])),
        nativeBuilder: (context, actions) {
          feed = actions;
          return const SizedBox();
        },
      )));
      await tester.pumpAndSettle();
      expect(feed, isNotEmpty);
      expect(h.events.where((e) => e.action == 'shown'), isEmpty);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(h.events.where((e) => e.action == 'shown'), hasLength(1));
    });
  });
}
