import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

GeneratedSpeakerTagPrompt prompt(String id, {String kind = 'owner_check', String origin = 'unnamed'}) =>
    GeneratedSpeakerTagPrompt(
      id: id,
      kind: kind,
      origin: origin,
      conversationId: 'c1',
      speakerId: 1,
      segmentIds: const ['s1'],
      clipStart: 0,
      clipEnd: 8,
      suggestedPersonId: kind == 'confirm_person' ? 'p1' : null,
      suggestedPersonName: kind == 'confirm_person' ? 'Sam' : null,
    );

class Harness {
  Harness(
      {List<GeneratedSpeakerTagPrompt>? prompts, bool firstTime = true, bool answerOk = true, bool settingsOk = true}) {
    provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async {
        fetches += 1;
        return GeneratedSpeakerTagPromptsResponse(
            prompts: prompts ?? [prompt('a'), prompt('b', kind: 'identify')], firstTime: firstTime);
      },
      markShown: (ids) async {
        shown.add(ids);
        return firstTime;
      },
      dismiss: () async {
        dismissals += 1;
        return true;
      },
      submitAnswer: (request) async {
        answers.add(request);
        return answerOk ? const GeneratedSpeakerTagPromptAnswerResponse(qualityOutcome: 'owner_missed') : null;
      },
      fetchSettings: () async => const GeneratedVoiceProfileSettings(),
      updateSettings: ({bool? speakerTagPromptsEnabled, bool? saveOtherVoiceProfiles, required String source}) async {
        settingUpdates.add({'tag': speakerTagPromptsEnabled, 'save': saveOtherVoiceProfiles, 'source': source});
        return settingsOk
            ? GeneratedVoiceProfileSettings(
                saveOtherVoiceProfiles: saveOtherVoiceProfiles ?? true,
                speakerTagPromptsEnabled: speakerTagPromptsEnabled ?? true,
              )
            : null;
      },
      loadClip: (p) async => clipAvailable ? Uint8List.fromList([1, 2, 3]) : null,
      playClip: (id, wav) async => true,
      emit: events.add,
      now: () => clock,
    );
  }

  late final SpeakerTagPromptsProvider provider;
  final events = <RegisteredEvent>[];
  final answers = <GeneratedSpeakerTagPromptAnswerRequest>[];
  final shown = <List<String>>[];
  final settingUpdates = <Map<String, Object?>>[];
  int fetches = 0;
  int dismissals = 0;
  bool clipAvailable = true;
  DateTime clock = DateTime(2026, 9, 24, 12);
}

void main() {
  test('loads a set, reports it once, and throttles refetches', () async {
    final h = Harness();
    await h.provider.loadIfDue();
    expect(h.provider.visible, isTrue);
    expect(h.provider.current!.id, 'a');
    await h.provider.reportShown();
    await h.provider.reportShown();
    expect(h.shown, [
      ['a', 'b']
    ]);
    expect(h.events.whereType<SpeakerTagPromptsViewed>().single.properties, {'prompt_count': 2, 'first_time': true});

    await h.provider.close();
    await h.provider.loadIfDue();
    expect(h.fetches, 1, reason: 'no refetch within the throttle window');
    h.clock = h.clock.add(SpeakerTagPromptsProvider.refetchInterval);
    await h.provider.loadIfDue();
    expect(h.fetches, 2);
  });

  test('answers advance the card and carry the prompt identity', () async {
    final h = Harness();
    await h.provider.loadIfDue();
    await h.provider.togglePlay(h.provider.current!);
    expect(await h.provider.answer(SpeakerTagAnswer.me), isTrue);
    expect(h.answers.single.answer, 'me');
    expect(h.answers.single.kind, 'owner_check');
    expect(h.answers.single.firstTime, isTrue);
    final submitted = h.events.whereType<SpeakerTagPromptAnswerSubmitted>().single.properties;
    expect(submitted['clip_played'], isTrue);
    expect(submitted['succeeded'], isTrue);
    expect(h.provider.current!.id, 'b');

    expect(await h.provider.answer(SpeakerTagAnswer.newPerson, name: 'Ana'), isTrue);
    expect(h.answers.last.name, 'Ana');
    expect(h.provider.finished, isTrue);
  });

  test('a failed answer keeps the question and shows the error', () async {
    final h = Harness(answerOk: false);
    await h.provider.loadIfDue();
    expect(await h.provider.answer(SpeakerTagAnswer.skip), isFalse);
    expect(h.provider.answerFailed, isTrue);
    expect(h.provider.current!.id, 'a');
    expect(h.events.whereType<SpeakerTagPromptAnswerSubmitted>().single.properties['succeeded'], isFalse);
  });

  test('closing an unanswered set counts as a dismissal; an answered one does not', () async {
    final unanswered = Harness();
    await unanswered.provider.loadIfDue();
    await unanswered.provider.reportShown();
    await unanswered.provider.close();
    expect(unanswered.dismissals, 1);
    expect(unanswered.events.whereType<SpeakerTagPromptsClosed>().single.properties,
        {'answered_count': 0, 'prompt_count': 2});

    final answered = Harness();
    await answered.provider.loadIfDue();
    await answered.provider.reportShown();
    await answered.provider.answer(SpeakerTagAnswer.me);
    await answered.provider.close();
    expect(answered.dismissals, 0);
  });

  test('an empty server response keeps the card hidden', () async {
    final h = Harness(prompts: const []);
    await h.provider.loadIfDue();
    expect(h.provider.visible, isFalse);
  });

  test('missing clip audio is reported without blocking answers', () async {
    final h = Harness()..clipAvailable = false;
    await h.provider.loadIfDue();
    await h.provider.togglePlay(h.provider.current!);
    expect(h.provider.clipErrorPromptId, 'a');
    expect(
        h.events.whereType<SpeakerTagPromptClipPlayed>().single.properties, {'kind': 'owner_check', 'loaded': false});
    expect(await h.provider.answer(SpeakerTagAnswer.notMe), isTrue);
  });

  test('first-prompt toggle writes with its source and reverts when rejected', () async {
    final ok = Harness();
    expect(await ok.provider.setSaveOtherVoiceProfiles(false, fromFirstPrompt: true), isTrue);
    expect(ok.provider.saveOtherVoiceProfiles, isFalse);
    expect(ok.settingUpdates.single, {'tag': null, 'save': false, 'source': 'first_prompt'});
    expect(ok.events.whereType<VoiceProfileSettingToggled>().single.properties,
        {'setting': 'save_other_voices', 'enabled': false, 'source': 'first_prompt', 'succeeded': true});

    final rejected = Harness(settingsOk: false);
    expect(await rejected.provider.setSaveOtherVoiceProfiles(false, fromFirstPrompt: false), isFalse);
    expect(rejected.provider.saveOtherVoiceProfiles, isTrue);
  });

  test('turning prompts off hides the card', () async {
    final h = Harness();
    await h.provider.loadIfDue();
    expect(await h.provider.setSpeakerTagPromptsEnabled(false), isTrue);
    expect(h.provider.visible, isFalse);
    expect(h.settingUpdates.single['source'], 'settings');
  });
}
