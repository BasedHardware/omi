// The "Help Omi recognize voices" card on Conversations: identify, confirm and owner-check
// questions, the answered state with its Undo toast, and the Someone Else… picker.
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/people_wire.g.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';

import '../harness.dart';

const _page = 'lib/pages/conversations/widgets/speaker_tag_prompt_card.dart (SpeakerTagPromptCard)';

Person _person(String id, String name, {bool pinned = false, String confidence = 'likely'}) => Person(
      id: id,
      name: name,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
      voiceReadiness: 'ready',
      pinned: pinned,
      confidence: confidence,
      confidenceReasons: const [GeneratedPersonConfidenceReason(code: 'card_picks', count: 2)],
    );

GeneratedSpeakerTagPrompt _prompt(String kind) => GeneratedSpeakerTagPrompt(
      id: 'prompt-$kind',
      kind: kind,
      origin: kind == 'confirm_person'
          ? 'auto_person'
          : kind == 'owner_check'
              ? 'auto_user'
              : 'unnamed',
      conversationId: 'c1',
      conversationTitle: 'Kitchen renovation call',
      conversationStartedAt: DateTime.now().subtract(const Duration(hours: 20)),
      speakerId: 2,
      segmentIds: const ['s1'],
      clipStart: 12,
      clipEnd: 19,
      excerpt: kind == 'owner_check'
          ? 'Honestly I think the second quote was better.'
          : 'Yeah, he said Thursday works if we sign today.',
      suggestedPersonId: kind == 'confirm_person' ? 'p-sam' : null,
      suggestedPersonName: kind == 'confirm_person' ? 'Sam Okafor' : null,
      candidates: kind == 'identify'
          ? const [
              GeneratedSpeakerTagCandidate(personId: 'p-jordan', name: 'Jordan Lee', matchLevel: 2, pinned: true),
              GeneratedSpeakerTagCandidate(personId: 'p-sam', name: 'Sam Okafor', matchLevel: 2),
              GeneratedSpeakerTagCandidate(personId: 'p-alex', name: 'Alex Rivera', matchLevel: 1),
            ]
          : null,
    );

/// Seven seconds of a speech-like envelope, so the waveform draws real samples.
Uint8List _clip() {
  const rate = 16000, seconds = 7;
  final data = ByteData(44 + rate * seconds * 2);
  for (var i = 0; i < rate * seconds; i++) {
    final t = i / rate;
    final envelope = (0.35 + 0.65 * math.pow(math.sin(t * 2.3) * math.sin(t * 0.7), 2)).clamp(0.0, 1.0);
    data.setInt16(44 + i * 2, (math.sin(t * 2 * math.pi * 180) * 12000 * envelope).round(), Endian.little);
  }
  return data.buffer.asUint8List();
}

Future<SpeakerTagPromptsProvider> _pumpCard(AuditRun a, String kind, {bool playClip = true}) async {
  final prompts = SpeakerTagPromptsProvider(
    fetchPrompts: () async => ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: [_prompt(kind)])),
    markShown: (_) async => const ApiSuccess(false),
    dismiss: () async => const ApiSuccess<void>(null),
    submitAnswer: (request) async =>
        ApiSuccess(GeneratedSpeakerTagPromptAnswerResponse(qualityOutcome: 'skipped', personId: request.personId)),
    loadClip: (_) async => ApiSuccess(_clip()),
    playClip: (_, __) async => true,
    emit: (_) {},
    answeredHold: Duration.zero,
  );
  final people = PeopleProvider(
    loadPeople: () async => [
      _person('p-jordan', 'Jordan Lee', pinned: true, confidence: 'confirmed'),
      _person('p-sam', 'Sam Okafor'),
      _person('p-alex', 'Alex Rivera'),
      _person('p-priya', 'Priya Natarajan'),
      _person('p-because', 'Because', confidence: 'unverified'),
    ],
  );
  await people.setPeople();
  await a.pump(
    Scaffold(
      backgroundColor: OmiColors.surface0,
      body: SafeArea(child: ListView(children: const [SpeakerTagPromptCard()])),
    ),
    scaffold: false,
    providers: [
      ChangeNotifierProvider<PeopleProvider>.value(value: people),
      ChangeNotifierProvider<SpeakerTagPromptsProvider>.value(value: prompts),
    ],
  );
  if (playClip) {
    await a.tap(find.byKey(const Key('speaker_tag_prompt_play')));
  }
  return prompts;
}

final speakerPromptScenarios = <AuditScenario>[
  AuditScenario(
    id: 'speaker-card-identify',
    title: 'Voice card: who is this, with candidates ranked by voice match',
    page: _page,
    state: 'An unnamed voice; Jordan (pinned) and Sam both possible matches, Alex weak; clip played',
    run: (a) async {
      await _pumpCard(a, 'identify');
      expect(find.text('Closest voices'), findsOneWidget);
      await a.shot('Card appears on Conversations; play the clip');
    },
  ),
  AuditScenario(
    id: 'speaker-card-confirm',
    title: 'Voice card: confirm an automatic match, then the answered state with Undo',
    page: _page,
    state: 'Omi matched Sam automatically; clip played',
    run: (a) async {
      await _pumpCard(a, 'confirm_person');
      await a.shot('Card asks about an automatic match');
      await a.tester.tap(find.byKey(const Key('speaker_tag_prompt_answer_yes')));
      await a.tester.pump();
      await a.tester.pump(const Duration(milliseconds: 400));
      await a.shot('Tap Yes: answered, with Undo', step: 'answered');
      await a.tap(find.text('Undo'));
    },
  ),
  AuditScenario(
    id: 'speaker-card-owner',
    title: 'Voice card: is this you',
    page: _page,
    state: 'An automatic owner label nobody reviewed; clip not played yet',
    run: (a) async {
      await _pumpCard(a, 'owner_check', playClip: false);
      await a.shot('Card asks about the owner');
    },
  ),
  AuditScenario(
    id: 'speaker-card-picker',
    title: 'Voice card: Someone Else… picker',
    page: _page,
    state: 'Confirm card for Sam; Someone Else… opened, so Sam is left out',
    run: (a) async {
      await _pumpCard(a, 'confirm_person');
      await a.tap(find.byKey(const Key('speaker_tag_prompt_answer_someone_else')));
      await a.shot('Tap Someone Else…');
    },
  ),
];
