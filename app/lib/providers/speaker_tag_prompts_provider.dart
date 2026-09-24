import 'dart:io';
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/speaker_tag_prompts.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/logger.dart';

/// Answers the card can send. Wire values match the backend enum.
enum SpeakerTagAnswer {
  me('me'),
  notMe('not_me'),
  person('person'),
  newPerson('new_person'),
  someoneElse('someone_else'),
  skip('skip');

  const SpeakerTagAnswer(this.wireName);
  final String wireName;
}

typedef ClipLoader = Future<ApiResult<Uint8List>> Function(GeneratedSpeakerTagPrompt prompt);
typedef ClipPlayer = Future<bool> Function(String promptId, Uint8List wav);

/// Drives the "Help Omi recognize voices" card: a small daily set of short clips
/// from the last 48 hours, answered one at a time. The server owns eligibility and
/// pacing; this provider only asks once per app session window and reports what
/// the user saw, played and answered.
class SpeakerTagPromptsProvider extends BaseProvider {
  SpeakerTagPromptsProvider({
    Future<ApiResult<GeneratedSpeakerTagPromptsResponse>> Function()? fetchPrompts,
    Future<ApiResult<bool>> Function(List<String>)? markShown,
    Future<ApiResult<void>> Function()? dismiss,
    Future<ApiResult<GeneratedSpeakerTagPromptAnswerResponse>> Function(GeneratedSpeakerTagPromptAnswerRequest)?
        submitAnswer,
    Future<ApiResult<GeneratedVoiceProfileSettings>> Function()? fetchSettings,
    Future<ApiResult<GeneratedVoiceProfileSettings>> Function({
      bool? speakerTagPromptsEnabled,
      bool? saveOtherVoiceProfiles,
      required String source,
    })? updateSettings,
    ClipLoader? loadClip,
    ClipPlayer? playClip,
    void Function(RegisteredEvent)? emit,
    DateTime Function()? now,
  })  : _fetchPrompts = fetchPrompts ?? api.getSpeakerTagPrompts,
        _markShown = markShown ?? api.markSpeakerTagPromptsShown,
        _dismiss = dismiss ?? api.dismissSpeakerTagPrompts,
        _submitAnswer = submitAnswer ?? api.answerSpeakerTagPrompt,
        _fetchSettings = fetchSettings ?? api.getVoiceProfileSettings,
        _updateSettings = updateSettings ?? api.updateVoiceProfileSettings,
        _loadClip = loadClip ?? _defaultLoadClip,
        _playClipOverride = playClip,
        _emit = emit ?? const TypedEvents().emit,
        _now = now ?? DateTime.now;

  static const Duration refetchInterval = Duration(minutes: 30);

  final Future<ApiResult<GeneratedSpeakerTagPromptsResponse>> Function() _fetchPrompts;
  final Future<ApiResult<bool>> Function(List<String>) _markShown;
  final Future<ApiResult<void>> Function() _dismiss;
  final Future<ApiResult<GeneratedSpeakerTagPromptAnswerResponse>> Function(GeneratedSpeakerTagPromptAnswerRequest)
      _submitAnswer;
  final Future<ApiResult<GeneratedVoiceProfileSettings>> Function() _fetchSettings;
  final Future<ApiResult<GeneratedVoiceProfileSettings>> Function({
    bool? speakerTagPromptsEnabled,
    bool? saveOtherVoiceProfiles,
    required String source,
  }) _updateSettings;
  final ClipLoader _loadClip;
  final ClipPlayer? _playClipOverride;
  final void Function(RegisteredEvent) _emit;
  final DateTime Function() _now;

  AudioPlayer? _player;
  DateTime? _lastFetchAt;
  bool _shownReported = false;
  final Set<String> _played = {};
  final Map<String, Uint8List> _clips = {};

  List<GeneratedSpeakerTagPrompt> prompts = [];
  int index = 0;
  int answeredCount = 0;
  bool firstTime = false;
  bool visible = false;
  bool finished = false;
  bool submitting = false;
  String? playingPromptId;
  String? clipErrorPromptId;
  bool answerFailed = false;

  bool saveOtherVoiceProfiles = true;
  bool speakerTagPromptsEnabled = true;
  bool settingsLoaded = false;

  GeneratedSpeakerTagPrompt? get current => index < prompts.length ? prompts[index] : null;

  /// Fetch today's set when the conversations page appears. Cheap to call often.
  Future<void> loadIfDue() async {
    final now = _now();
    if (visible || loading) return;
    if (_lastFetchAt != null && now.difference(_lastFetchAt!) < refetchInterval) return;
    _lastFetchAt = now;
    loading = true;
    final result = await _fetchPrompts();
    loading = false;
    final GeneratedSpeakerTagPromptsResponse response;
    switch (result) {
      case ApiSuccess(:final data):
        response = data;
      case ApiFailure(:final problem):
        // Nothing to show on an outage; a later page visit retries after the throttle window.
        Logger.debug('speaker tag prompts unavailable: $problem');
        return;
    }
    saveOtherVoiceProfiles = response.saveOtherVoiceProfiles;
    final fetched = response.prompts ?? const <GeneratedSpeakerTagPrompt>[];
    if (fetched.isEmpty) {
      notifyListeners();
      return;
    }
    prompts = fetched;
    index = 0;
    answeredCount = 0;
    firstTime = response.firstTime;
    visible = true;
    finished = false;
    answerFailed = false;
    _shownReported = false;
    _played.clear();
    _clips.clear();
    notifyListeners();
  }

  /// Called once the card is actually on screen; starts the server's daily cooldown.
  Future<void> reportShown() async {
    if (_shownReported || prompts.isEmpty) return;
    _shownReported = true;
    _emit(SpeakerTagPromptsViewed(promptCount: prompts.length, firstTime: firstTime));
    final result = await _markShown(prompts.map((prompt) => prompt.id).toList());
    switch (result) {
      case ApiSuccess(:final data):
        if (data != firstTime) {
          firstTime = data;
          notifyListeners();
        }
      case ApiFailure(:final problem):
        // The set stays on screen; the server just does not start its cooldown.
        Logger.debug('speaker tag prompts shown report failed: $problem');
    }
  }

  Future<void> togglePlay(GeneratedSpeakerTagPrompt prompt) async {
    if (playingPromptId == prompt.id) {
      await _player?.stop();
      playingPromptId = null;
      notifyListeners();
      return;
    }
    playingPromptId = prompt.id;
    clipErrorPromptId = null;
    notifyListeners();
    var wav = _clips[prompt.id];
    if (wav == null) {
      switch (await _loadClip(prompt)) {
        case ApiSuccess(:final data):
          wav = data;
        case ApiFailure(:final problem):
          Logger.debug('speaker tag prompt clip unavailable: $problem');
      }
    }
    var played = false;
    if (wav != null && wav.isNotEmpty) {
      _clips[prompt.id] = wav;
      played = await (_playClipOverride ?? _playWithJustAudio)(prompt.id, wav);
    }
    _played.add(prompt.id);
    _emit(SpeakerTagPromptClipPlayed(kind: _kind(prompt.kind), loaded: played));
    if (!played) clipErrorPromptId = prompt.id;
    if (playingPromptId == prompt.id) playingPromptId = null;
    notifyListeners();
  }

  /// Returns true when the answer was saved and the card moved on.
  Future<bool> answer(SpeakerTagAnswer answer, {String? personId, String? name}) async {
    final prompt = current;
    if (prompt == null || submitting) return false;
    submitting = true;
    answerFailed = false;
    notifyListeners();
    final result = await _submitAnswer(
      GeneratedSpeakerTagPromptAnswerRequest(
        promptId: prompt.id,
        kind: prompt.kind,
        origin: prompt.origin,
        conversationId: prompt.conversationId,
        speakerId: prompt.speakerId,
        segmentIds: prompt.segmentIds,
        answer: answer.wireName,
        personId: personId,
        name: name,
        suggestedPersonId: prompt.suggestedPersonId,
        firstTime: firstTime,
      ),
    );
    final succeeded = result is ApiSuccess<GeneratedSpeakerTagPromptAnswerResponse>;
    _emit(
      SpeakerTagPromptAnswerSubmitted(
        kind: _answerKind(prompt.kind),
        answer: _answer(answer),
        clipPlayed: _played.contains(prompt.id),
        firstTime: firstTime,
        succeeded: succeeded,
      ),
    );
    submitting = false;
    if (!succeeded) {
      answerFailed = true;
      notifyListeners();
      return false;
    }
    await _player?.stop();
    playingPromptId = null;
    answeredCount += 1;
    index += 1;
    finished = index >= prompts.length;
    notifyListeners();
    return true;
  }

  /// The user closed the card. An unanswered set counts toward the server's back-off.
  Future<void> close() async {
    if (!visible) return;
    _emit(SpeakerTagPromptsClosed(answeredCount: answeredCount, promptCount: prompts.length));
    visible = false;
    await _player?.stop();
    playingPromptId = null;
    notifyListeners();
    if (answeredCount == 0 && _shownReported) {
      if (await _dismiss() case ApiFailure(:final problem)) {
        Logger.debug('speaker tag prompts dismiss failed: $problem');
      }
    }
  }

  Future<void> loadSettings() async {
    final GeneratedVoiceProfileSettings settings;
    switch (await _fetchSettings()) {
      case ApiSuccess(:final data):
        settings = data;
      case ApiFailure(:final problem):
        // Leave the switches disabled rather than showing a guessed value.
        Logger.debug('voice profile settings unavailable: $problem');
        return;
    }
    saveOtherVoiceProfiles = settings.saveOtherVoiceProfiles;
    speakerTagPromptsEnabled = settings.speakerTagPromptsEnabled;
    settingsLoaded = true;
    notifyListeners();
  }

  /// Returns false and restores the previous value when the server rejects the change.
  Future<bool> setSaveOtherVoiceProfiles(bool enabled, {required bool fromFirstPrompt}) async {
    final previous = saveOtherVoiceProfiles;
    saveOtherVoiceProfiles = enabled;
    notifyListeners();
    final settings = _settingsOrNull(
      await _updateSettings(saveOtherVoiceProfiles: enabled, source: fromFirstPrompt ? 'first_prompt' : 'settings'),
    );
    _emit(
      VoiceProfileSettingToggled(
        setting: VoiceProfileSettingToggledSetting.saveOtherVoices,
        enabled: enabled,
        source:
            fromFirstPrompt ? VoiceProfileSettingToggledSource.firstPrompt : VoiceProfileSettingToggledSource.settings,
        succeeded: settings != null,
      ),
    );
    if (settings == null) {
      saveOtherVoiceProfiles = previous;
      notifyListeners();
      return false;
    }
    saveOtherVoiceProfiles = settings.saveOtherVoiceProfiles;
    notifyListeners();
    return true;
  }

  Future<bool> setSpeakerTagPromptsEnabled(bool enabled) async {
    final previous = speakerTagPromptsEnabled;
    speakerTagPromptsEnabled = enabled;
    notifyListeners();
    final settings = _settingsOrNull(await _updateSettings(speakerTagPromptsEnabled: enabled, source: 'settings'));
    _emit(
      VoiceProfileSettingToggled(
        setting: VoiceProfileSettingToggledSetting.tagPrompts,
        enabled: enabled,
        source: VoiceProfileSettingToggledSource.settings,
        succeeded: settings != null,
      ),
    );
    if (settings == null) {
      speakerTagPromptsEnabled = previous;
      notifyListeners();
      return false;
    }
    speakerTagPromptsEnabled = settings.speakerTagPromptsEnabled;
    if (!enabled) {
      visible = false;
      _lastFetchAt = null;
    }
    notifyListeners();
    return true;
  }

  void clearUserData() {
    prompts = [];
    index = 0;
    answeredCount = 0;
    visible = false;
    finished = false;
    _lastFetchAt = null;
    _shownReported = false;
    _played.clear();
    _clips.clear();
    settingsLoaded = false;
    _player?.stop();
    notifyListeners();
  }

  @override
  void dispose() {
    _player?.dispose();
    super.dispose();
  }

  Future<bool> _playWithJustAudio(String promptId, Uint8List wav) async {
    try {
      final directory = await getTemporaryDirectory();
      final file = File('${directory.path}/speaker_tag_prompt_$promptId.wav');
      await file.writeAsBytes(wav, flush: true);
      final player = _player ??= AudioPlayer();
      await player.stop();
      await player.setFilePath(file.path);
      await player.play();
      return true;
    } catch (error) {
      Logger.debug('speaker tag prompt clip playback failed: $error');
      return false;
    }
  }

  static GeneratedVoiceProfileSettings? _settingsOrNull(ApiResult<GeneratedVoiceProfileSettings> result) {
    switch (result) {
      case ApiSuccess(:final data):
        return data;
      case ApiFailure(:final problem):
        // The caller restores the previous switch value and reports succeeded=false.
        Logger.debug('voice profile settings update failed: $problem');
        return null;
    }
  }

  static Future<ApiResult<Uint8List>> _defaultLoadClip(GeneratedSpeakerTagPrompt prompt) => api.getSpeakerTagPromptClip(
        conversationId: prompt.conversationId,
        start: prompt.clipStart,
        end: prompt.clipEnd,
      );

  static SpeakerTagPromptClipPlayedKind _kind(String kind) => switch (kind) {
        'owner_check' => SpeakerTagPromptClipPlayedKind.ownerCheck,
        'confirm_person' => SpeakerTagPromptClipPlayedKind.confirmPerson,
        'identify' => SpeakerTagPromptClipPlayedKind.identify,
        _ => SpeakerTagPromptClipPlayedKind.unknown,
      };

  static SpeakerTagPromptAnswerSubmittedKind _answerKind(String kind) => switch (kind) {
        'owner_check' => SpeakerTagPromptAnswerSubmittedKind.ownerCheck,
        'confirm_person' => SpeakerTagPromptAnswerSubmittedKind.confirmPerson,
        'identify' => SpeakerTagPromptAnswerSubmittedKind.identify,
        _ => SpeakerTagPromptAnswerSubmittedKind.unknown,
      };

  static SpeakerTagPromptAnswerSubmittedAnswer _answer(SpeakerTagAnswer answer) => switch (answer) {
        SpeakerTagAnswer.me => SpeakerTagPromptAnswerSubmittedAnswer.me,
        SpeakerTagAnswer.notMe => SpeakerTagPromptAnswerSubmittedAnswer.notMe,
        SpeakerTagAnswer.person => SpeakerTagPromptAnswerSubmittedAnswer.person,
        SpeakerTagAnswer.newPerson => SpeakerTagPromptAnswerSubmittedAnswer.newPerson,
        SpeakerTagAnswer.someoneElse => SpeakerTagPromptAnswerSubmittedAnswer.someoneElse,
        SpeakerTagAnswer.skip => SpeakerTagPromptAnswerSubmittedAnswer.skip,
      };
}
