import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

GeneratedSpeakerTagPrompt prompt(
  String id, {
  String kind = 'owner_check',
  String origin = 'unnamed',
}) =>
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

class _FakeFile extends Fake implements File {
  _FakeFile(this.path, {required this.onWrite, required this.onDelete});

  @override
  final String path;
  final void Function() onWrite;
  final void Function() onDelete;

  @override
  Future<File> writeAsBytes(
    List<int> bytes, {
    FileMode mode = FileMode.write,
    bool flush = false,
  }) async {
    onWrite();
    return this;
  }

  @override
  Future<File> delete({bool recursive = false}) async {
    onDelete();
    return this;
  }
}

class Harness {
  Harness({
    List<GeneratedSpeakerTagPrompt>? prompts,
    bool firstTime = true,
    bool answerOk = true,
    bool settingsOk = true,
  }) {
    provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async {
        fetches += 1;
        return ApiSuccess(
          GeneratedSpeakerTagPromptsResponse(
            prompts: prompts ?? [prompt('a'), prompt('b', kind: 'identify')],
            firstTime: firstTime,
          ),
        );
      },
      markShown: (ids) async {
        shown.add(ids);
        return ApiSuccess(firstTime);
      },
      dismiss: () async {
        dismissals += 1;
        return const ApiSuccess<void>(null);
      },
      submitAnswer: (request) async {
        answers.add(request);
        return answerOk
            ? const ApiSuccess(
                GeneratedSpeakerTagPromptAnswerResponse(
                  qualityOutcome: 'owner_missed',
                ),
              )
            : const ApiFailure(
                ApiProblem(ApiProblemKind.server, statusCode: 500),
              );
      },
      fetchSettings: () async => const ApiSuccess(GeneratedVoiceProfileSettings()),
      updateSettings: ({
        bool? speakerTagPromptsEnabled,
        bool? saveOtherVoiceProfiles,
        required String source,
      }) async {
        settingUpdates.add({
          'tag': speakerTagPromptsEnabled,
          'save': saveOtherVoiceProfiles,
          'source': source,
        });
        return settingsOk
            ? ApiSuccess(
                GeneratedVoiceProfileSettings(
                  saveOtherVoiceProfiles: saveOtherVoiceProfiles ?? true,
                  speakerTagPromptsEnabled: speakerTagPromptsEnabled ?? true,
                ),
              )
            : const ApiFailure(ApiProblem(ApiProblemKind.transport));
      },
      loadClip: (p) async => clipAvailable
          ? ApiSuccess(Uint8List.fromList([1, 2, 3]))
          : const ApiFailure(
              ApiProblem(ApiProblemKind.notFound, statusCode: 404),
            ),
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
      ['a', 'b'],
    ]);
    expect(h.events.whereType<SpeakerTagPromptsViewed>().single.properties, {
      'prompt_count': 2,
      'first_time': true,
    });

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

    expect(
      await h.provider.answer(SpeakerTagAnswer.newPerson, name: 'Ana'),
      isTrue,
    );
    expect(h.answers.last.name, 'Ana');
    expect(h.provider.finished, isTrue);
  });

  test('a failed answer keeps the question and shows the error', () async {
    final h = Harness(answerOk: false);
    await h.provider.loadIfDue();
    expect(await h.provider.answer(SpeakerTagAnswer.skip), isFalse);
    expect(h.provider.answerFailed, isTrue);
    expect(h.provider.current!.id, 'a');
    expect(
      h.events.whereType<SpeakerTagPromptAnswerSubmitted>().single.properties['succeeded'],
      isFalse,
    );
  });

  test(
    'closing an unanswered set counts as a dismissal; an answered one does not',
    () async {
      final unanswered = Harness();
      await unanswered.provider.loadIfDue();
      await unanswered.provider.reportShown();
      await unanswered.provider.close();
      expect(unanswered.dismissals, 1);
      expect(
        unanswered.events.whereType<SpeakerTagPromptsClosed>().single.properties,
        {'answered_count': 0, 'prompt_count': 2},
      );

      final answered = Harness();
      await answered.provider.loadIfDue();
      await answered.provider.reportShown();
      await answered.provider.answer(SpeakerTagAnswer.me);
      await answered.provider.close();
      expect(answered.dismissals, 0);
    },
  );

  test('an empty server response keeps the card hidden', () async {
    final h = Harness(prompts: const []);
    await h.provider.loadIfDue();
    expect(h.provider.visible, isFalse);
  });

  test(
    'missing clip audio is reported and advances without submitting an answer',
    () async {
      final h = Harness()..clipAvailable = false;
      await h.provider.loadIfDue();
      await h.provider.togglePlay(h.provider.current!);
      expect(h.provider.current?.id, 'b');
      expect(h.provider.clipErrorPromptId, isNull);
      expect(
        h.events.whereType<SpeakerTagPromptClipPlayed>().single.properties,
        {'kind': 'owner_check', 'loaded': false},
      );
      expect(h.answers, isEmpty);
      expect(h.provider.answeredCount, 0);
      expect(await h.provider.answer(SpeakerTagAnswer.notMe), isTrue);
    },
  );

  test('last unavailable clip refetches once and does not reoffer it', () async {
    final h = Harness(prompts: [prompt('a')])..clipAvailable = false;
    await h.provider.loadIfDue();
    await h.provider.togglePlay(h.provider.current!);
    expect(h.fetches, 2);
    expect(h.provider.visible, isFalse);
    expect(h.provider.current, isNull);
    expect(h.provider.answeredCount, 0);
    expect(h.answers, isEmpty);
    await h.provider.loadIfDue();
    expect(h.fetches, 2);
    h.clock = h.clock.add(SpeakerTagPromptsProvider.refetchInterval);
    await h.provider.loadIfDue();
    expect(h.fetches, 3);
    expect(h.provider.current?.id, 'a');
  });

  test(
    'first-prompt toggle writes with its source and reverts when rejected',
    () async {
      final ok = Harness();
      expect(
        await ok.provider.setSaveOtherVoiceProfiles(
          false,
          fromFirstPrompt: true,
        ),
        isTrue,
      );
      expect(ok.provider.saveOtherVoiceProfiles, isFalse);
      expect(ok.settingUpdates.single, {
        'tag': null,
        'save': false,
        'source': 'first_prompt',
      });
      expect(
        ok.events.whereType<VoiceProfileSettingToggled>().single.properties,
        {
          'setting': 'save_other_voices',
          'enabled': false,
          'source': 'first_prompt',
          'succeeded': true,
        },
      );

      final rejected = Harness(settingsOk: false);
      expect(
        await rejected.provider.setSaveOtherVoiceProfiles(
          false,
          fromFirstPrompt: false,
        ),
        isFalse,
      );
      expect(rejected.provider.saveOtherVoiceProfiles, isTrue);
    },
  );

  test('turning prompts off hides the card', () async {
    final h = Harness();
    await h.provider.loadIfDue();
    expect(await h.provider.setSpeakerTagPromptsEnabled(false), isTrue);
    expect(h.provider.visible, isFalse);
    expect(h.settingUpdates.single['source'], 'settings');
  });

  test('a stale fetch cannot repopulate prompts after clearUserData', () async {
    final fetch = Completer<ApiResult<GeneratedSpeakerTagPromptsResponse>>();
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () => fetch.future,
      emit: (_) {},
    );
    var notifications = 0;
    provider.addListener(() => notifications++);
    final pending = provider.loadIfDue();
    provider.clearUserData();
    final afterClear = notifications;
    fetch.complete(
      ApiSuccess(
        GeneratedSpeakerTagPromptsResponse(
          prompts: [prompt('a')],
          firstTime: true,
        ),
      ),
    );
    await pending;
    expect(provider.prompts, isEmpty);
    expect(provider.visible, isFalse);
    expect(provider.loading, isFalse);
    expect(notifications, afterClear, reason: 'a stale fetch must not notify');
  });

  test('a stale answer cannot advance or emit after clearUserData', () async {
    final answer = Completer<ApiResult<GeneratedSpeakerTagPromptAnswerResponse>>();
    final events = <RegisteredEvent>[];
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(
        GeneratedSpeakerTagPromptsResponse(
          prompts: [
            prompt('a'),
            prompt('b', kind: 'identify'),
          ],
        ),
      ),
      submitAnswer: (_) => answer.future,
      emit: events.add,
    );
    await provider.loadIfDue();
    final pending = provider.answer(SpeakerTagAnswer.me);
    provider.clearUserData();
    answer.complete(
      const ApiSuccess(
        GeneratedSpeakerTagPromptAnswerResponse(qualityOutcome: 'owner_missed'),
      ),
    );
    expect(await pending, isFalse);
    expect(provider.index, 0);
    expect(provider.submitting, isFalse);
    expect(events.whereType<SpeakerTagPromptAnswerSubmitted>(), isEmpty);
  });

  test('a stale settings update cannot overwrite the reset switches', () async {
    final update = Completer<ApiResult<GeneratedVoiceProfileSettings>>();
    final provider = SpeakerTagPromptsProvider(
      updateSettings: ({
        bool? speakerTagPromptsEnabled,
        bool? saveOtherVoiceProfiles,
        required String source,
      }) =>
          update.future,
      emit: (_) {},
    );
    final pending = provider.setSaveOtherVoiceProfiles(
      false,
      fromFirstPrompt: false,
    );
    provider.clearUserData();
    update.complete(
      const ApiSuccess(
        GeneratedVoiceProfileSettings(saveOtherVoiceProfiles: false),
      ),
    );
    expect(await pending, isFalse);
    expect(provider.saveOtherVoiceProfiles, isTrue);
  });

  test(
    'a stale clip load cannot flag an error or emit after clearUserData',
    () async {
      final clip = Completer<ApiResult<Uint8List>>();
      final events = <RegisteredEvent>[];
      final provider = SpeakerTagPromptsProvider(
        fetchPrompts: () async => ApiSuccess(
          GeneratedSpeakerTagPromptsResponse(prompts: [prompt('a')]),
        ),
        loadClip: (_) => clip.future,
        emit: events.add,
      );
      await provider.loadIfDue();
      final pending = provider.togglePlay(provider.current!);
      provider.clearUserData();
      clip.complete(ApiSuccess(Uint8List.fromList([1, 2, 3])));
      await pending;
      expect(provider.clipErrorPromptId, isNull);
      expect(provider.playingPromptId, isNull);
      expect(events.whereType<SpeakerTagPromptClipPlayed>(), isEmpty);
    },
  );

  test(
    'a stale shown report cannot restore firstTime after clearUserData',
    () async {
      final shown = Completer<ApiResult<bool>>();
      final provider = SpeakerTagPromptsProvider(
        fetchPrompts: () async => ApiSuccess(
          GeneratedSpeakerTagPromptsResponse(
            prompts: [prompt('a')],
            firstTime: true,
          ),
        ),
        markShown: (_) => shown.future,
        emit: (_) {},
      );
      await provider.loadIfDue();
      expect(provider.firstTime, isTrue);
      final pending = provider.reportShown();
      provider.clearUserData();
      shown.complete(const ApiSuccess(true));
      await pending;
      expect(provider.firstTime, isFalse);
    },
  );

  test('dispose while a fetch is in flight does not notify or throw', () async {
    final fetch = Completer<ApiResult<GeneratedSpeakerTagPromptsResponse>>();
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () => fetch.future,
      emit: (_) {},
    );
    final pending = provider.loadIfDue();
    provider.dispose();
    fetch.complete(
      ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: [prompt('a')])),
    );
    await pending;
    expect(provider.prompts, isEmpty);
  });

  test(
    'dispose while an answer is in flight does not notify or throw',
    () async {
      final answer = Completer<ApiResult<GeneratedSpeakerTagPromptAnswerResponse>>();
      final provider = SpeakerTagPromptsProvider(
        fetchPrompts: () async => ApiSuccess(
          GeneratedSpeakerTagPromptsResponse(prompts: [prompt('a')]),
        ),
        submitAnswer: (_) => answer.future,
        emit: (_) {},
      );
      await provider.loadIfDue();
      final pending = provider.answer(SpeakerTagAnswer.me);
      provider.dispose();
      answer.complete(
        const ApiSuccess(
          GeneratedSpeakerTagPromptAnswerResponse(
            qualityOutcome: 'owner_missed',
          ),
        ),
      );
      expect(await pending, isFalse);
    },
  );

  test('stopping during a clip load never starts playback', () async {
    final clip = Completer<ApiResult<Uint8List>>();
    var plays = 0;
    final events = <RegisteredEvent>[];
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(
        GeneratedSpeakerTagPromptsResponse(prompts: [prompt('a')]),
      ),
      loadClip: (_) => clip.future,
      playClip: (id, wav) async {
        plays += 1;
        return true;
      },
      emit: events.add,
    );
    await provider.loadIfDue();
    final current = provider.current!;
    final loading = provider.togglePlay(current);
    final stopping = provider.togglePlay(current);
    clip.complete(ApiSuccess(Uint8List.fromList([1, 2, 3])));
    await loading;
    await stopping;
    expect(plays, 0);
    expect(provider.playingPromptId, isNull);
    expect(events.whereType<SpeakerTagPromptClipPlayed>(), isEmpty);
  });

  test('a clip loaded for the previous account never plays', () async {
    final clip = Completer<ApiResult<Uint8List>>();
    var plays = 0;
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(
        GeneratedSpeakerTagPromptsResponse(prompts: [prompt('a')]),
      ),
      loadClip: (_) => clip.future,
      playClip: (id, wav) async {
        plays += 1;
        return true;
      },
      emit: (_) {},
    );
    await provider.loadIfDue();
    final pending = provider.togglePlay(provider.current!);
    provider.clearUserData();
    await provider.loadIfDue();
    clip.complete(ApiSuccess(Uint8List.fromList([1, 2, 3])));
    await pending;
    expect(plays, 0);
    expect(provider.playingPromptId, isNull);
  });

  test('dispose during a clip load does not play or throw', () async {
    final clip = Completer<ApiResult<Uint8List>>();
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(
        GeneratedSpeakerTagPromptsResponse(prompts: [prompt('a')]),
      ),
      loadClip: (_) => clip.future,
      emit: (_) {},
    );
    await provider.loadIfDue();
    final pending = provider.togglePlay(provider.current!);
    provider.dispose();
    clip.complete(ApiSuccess(Uint8List.fromList([1, 2, 3])));
    await pending;
  });

  test(
    'default playback writes a unique temp file that never contains the prompt id',
    () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async => '/tmp/omi_test');
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null),
      );
      final written = <String>[];
      final deleted = <String>[];
      late SpeakerTagPromptsProvider provider;
      await IOOverrides.runZoned(
        () async {
          provider = SpeakerTagPromptsProvider(
            fetchPrompts: () async => ApiSuccess(
              GeneratedSpeakerTagPromptsResponse(
                prompts: [prompt('secret-prompt-id')],
              ),
            ),
            loadClip: (_) async => ApiSuccess(Uint8List.fromList([1, 2, 3])),
            emit: (_) {},
          );
          for (var i = 0; i < 2; i++) {
            await provider.loadIfDue();
            await provider.togglePlay(provider.current!);
          }
        },
        createFile: (path) {
          written.add(path);
          return _FakeFile(
            path,
            onWrite: provider.clearUserData,
            onDelete: () => deleted.add(path),
          );
        },
      );
      expect(written, hasLength(2));
      expect(written[0], isNot(written[1]));
      expect(deleted, written);
      for (final path in written) {
        expect(path, isNot(contains('secret-prompt-id')));
        expect(path, matches(RegExp(r'speaker_tag_prompt_\d+_\d+\.wav$')));
      }
    },
  );
}
