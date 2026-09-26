import 'dart:async';
import 'dart:typed_data';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'goal_text_cleanup.dart';

class VoiceEnrollmentUnavailable implements Exception {}

enum IntroductionStage {
  ready,
  starting,
  recording,
  paused,
  transcribing,
  review,
  savingVoice,
  voiceError,
  savingMemories,
  done
}

/// The boundary is deliberately transcription-only. Drafts must not enter the
/// conversation/memory pipeline before the user reviews and keeps them.
abstract class GuidedVoiceIO {
  bool get livePreview;
  Future<void> prepare();
  Future<void> start(void Function(Uint8List) onAudio, VoidCallback onInterrupted);
  Future<void> stop();
  Future<String> transcribe(Uint8List pcm);
  Future<bool> enroll(Uint8List pcm);
  Future<bool> remember(String text);
  Future<bool> saveGoal(String text, String idempotencyKey);
  Future<void> close();
}

class IntroductionAnswer {
  IntroductionAnswer(this.text, this.audio, this.id, {this.isGoal = false, this.originalText});
  String text;
  final Uint8List audio;
  final String id;
  final bool isGoal;
  final String? originalText;
  int editRevision = 0;
  String? submittedGoal;
  bool get locked => saved || submittedGoal != null;
  bool keep = true;
  bool saved = false;
}

class GuidedVoiceController extends ChangeNotifier {
  static const promptCount = 4;
  GuidedVoiceController(this.io, {this.flowSource = 'first_run', this.flowVariant = 'guided_voice_v1'});
  final GuidedVoiceIO io;
  final String flowSource;
  final String flowVariant;
  IntroductionStage stage = IntroductionStage.ready;
  int promptIndex = 0;
  int alternative = 0;
  final answers = <IntroductionAnswer>[];
  final _frames = BytesBuilder(copy: true);
  String transcript = '';
  String? error;
  String? voiceError;
  bool _savingAll = false;
  bool voiceSaved = false;
  double level = 0;
  double seconds = 0;
  bool _disposed = false;
  int _generation = 0;
  Timer? _previewTimer;
  Future<String>? _preview;
  bool _prepared = false;
  bool _autoStart = false;
  bool _extraSample = false;
  final _sessionId = const Uuid().v4();
  DateTime? _startedAt;
  DateTime? _promptViewedAt;
  int _viewedPrompt = -1;
  int _recordingAttempts = 0;
  int _reviewAttempts = 0;
  int _saveAttempts = 0;
  int _voiceAttempts = 0;
  bool _startedTelemetry = false;
  bool _terminalTelemetry = false;

  String get sessionId => _sessionId;

  void markStarted() {
    if (_startedTelemetry || _disposed) return;
    _startedTelemetry = true;
    _startedAt = DateTime.now();
    final analytics = PlatformManager.instance.analytics;
    analytics.guidedIntroStarted(
      sessionId: _sessionId,
      source: flowSource,
      variant: flowVariant,
      promptCount: promptCount,
    );
    _recordPromptViewed();
  }

  void _recordPromptViewed() {
    if (promptIndex >= promptCount || _viewedPrompt == promptIndex) return;
    _viewedPrompt = promptIndex;
    _promptViewedAt = DateTime.now();
    PlatformManager.instance.analytics.guidedIntroPromptViewed(
      sessionId: _sessionId,
      source: flowSource,
      variant: flowVariant,
      promptIndex: promptIndex,
    );
  }

  int _promptDurationMs() => _promptViewedAt == null ? 0 : DateTime.now().difference(_promptViewedAt!).inMilliseconds;

  void _recordCompletedPrompt({required String result, required bool transcriptPresent}) {
    PlatformManager.instance.analytics.guidedIntroPromptCompleted(
      sessionId: _sessionId,
      source: flowSource,
      variant: flowVariant,
      promptIndex: promptIndex,
      result: result,
      durationMs: _promptDurationMs(),
      transcriptPresent: transcriptPresent,
    );
  }

  void _recordTerminal({required String completionMode}) {
    if (_terminalTelemetry) return;
    _terminalTelemetry = true;
    final goals = answers.where((answer) => answer.isGoal).toList(growable: false);
    final goal = goals.isEmpty ? null : goals.first;
    PlatformManager.instance.analytics.guidedIntroCompleted(
      sessionId: _sessionId,
      source: flowSource,
      variant: flowVariant,
      completionMode: completionMode,
      voiceResult: voiceSaved
          ? 'success'
          : completionMode == 'saved'
              ? 'failed'
              : 'skipped',
      memorySaved: savedMemoryCount,
      goalResult: goal == null
          ? 'not_present'
          : goal.saved
              ? 'saved'
              : goal.keep
                  ? 'failed'
                  : 'skipped',
      elapsedMs: _startedAt == null ? 0 : DateTime.now().difference(_startedAt!).inMilliseconds,
    );
  }

  double get progress => promptIndex / promptCount;
  bool get isGoalPrompt => promptIndex == promptCount - 1 && !_extraSample;
  bool get goalSaved => answers.any((a) => a.isGoal && a.saved);
  int get savedMemoryCount => answers.where((a) => !a.isGoal && a.saved).length;
  bool get saving => _savingAll || stage == IntroductionStage.savingVoice || stage == IntroductionStage.savingMemories;
  bool get busy =>
      _savingAll ||
      const [
        IntroductionStage.starting,
        IntroductionStage.transcribing,
        IntroductionStage.savingVoice,
        IntroductionStage.savingMemories
      ].contains(stage);
  bool get active => stage == IntroductionStage.recording;
  bool get canFinish => _frames.length >= 16000; // Half a second, never a voice-quality claim.
  int get keptCount => answers.where((a) => a.keep && a.text.trim().isNotEmpty).length;
  bool get allMemoriesSaved => answers.where((a) => a.keep && a.text.trim().isNotEmpty).every((a) => a.saved);

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  bool _current(int generation) => !_disposed && _generation == generation;

  Future<void> start() async {
    if (busy || active || _disposed) return;
    markStarted();
    _autoStart = true;
    final generation = ++_generation;
    stage = IntroductionStage.starting;
    error = null;
    _emit();
    try {
      if (!_prepared) {
        await io.prepare();
        _prepared = true;
      }
      if (!_current(generation)) return;
      await io.start((bytes) {
        if (!_current(generation)) return;
        _frames.add(bytes);
        seconds = _frames.length / 32000;
        final data = ByteData.sublistView(bytes);
        double sum = 0;
        for (var i = 0; i + 1 < bytes.length; i += 2) {
          final sample = data.getInt16(i, Endian.little);
          sum += sample * sample;
        }
        level = bytes.length < 2 ? 0 : (sqrt(sum / (bytes.length ~/ 2)) / 1800).clamp(0, 1);
        _emit();
        if (seconds >= 45 && active) unawaited(pause());
      }, () {
        if (_current(generation) && active) unawaited(pause());
      });
      if (!_current(generation)) {
        await io.stop();
        return;
      }
      stage = IntroductionStage.recording;
      _recordingAttempts++;
      PlatformManager.instance.analytics.guidedIntroRecordingStarted(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        promptIndex: promptIndex,
        attempt: _recordingAttempts,
      );
      _previewTimer = Timer.periodic(const Duration(seconds: 3), (_) => _updatePreview(generation));
    } catch (_) {
      if (!_current(generation)) return;
      stage = IntroductionStage.paused;
      error = 'microphone';
      PlatformManager.instance.analytics.guidedIntroRecordingFailed(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        promptIndex: promptIndex,
        failureClass: 'microphone',
      );
      await io.stop();
    }
    _emit();
  }

  Future<void> _updatePreview(int generation) async {
    if (!active || !io.livePreview || _preview != null || !canFinish) return;
    final pending = io.transcribe(_frames.toBytes());
    _preview = pending;
    try {
      final text = await pending;
      if (_current(generation) && active && text.trim().isNotEmpty) transcript = text.trim();
    } catch (_) {
      // The final transcription has a visible retry. A preview is not a receipt.
    } finally {
      _preview = null;
      _emit();
    }
  }

  Future<void> pause() async {
    _autoStart = false;
    if (!active && stage != IntroductionStage.starting) return;
    if (stage == IntroductionStage.starting) ++_generation;
    stage = IntroductionStage.paused;
    _previewTimer?.cancel();
    await io.stop();
    level = 0;
    _emit();
  }

  Future<void> next() async {
    if (busy || !canFinish || _disposed) return;
    _autoStart = true;
    final generation = _generation;
    stage = IntroductionStage.transcribing;
    error = null;
    _previewTimer?.cancel();
    _emit();
    try {
      await io.stop();
      try {
        await _preview;
      } catch (_) {}
      if (!_current(generation)) return;
      final audio = _frames.toBytes();
      final text = (await io.transcribe(audio)).trim();
      if (!_current(generation)) return;
      if (text.isEmpty) throw StateError('No speech');
      final answer = IntroductionAnswer(
          isGoalPrompt ? cleanIntroductionGoal(text) : text, audio, 'intro-$_sessionId-${answers.length}',
          isGoal: isGoalPrompt, originalText: isGoalPrompt ? text : null);
      answer.keep = answer.text.isNotEmpty;
      answers.add(answer);
      _recordCompletedPrompt(result: 'answered', transcriptPresent: true);
      await _advance();
    } catch (_) {
      if (!_current(generation)) return;
      stage = IntroductionStage.paused;
      error = 'transcription';
      _recordCompletedPrompt(result: 'transcription_failed', transcriptPresent: false);
      _emit();
    }
  }

  Future<void> skipPrompt() async {
    if (busy || _disposed) return;
    markStarted();
    ++_generation;
    _previewTimer?.cancel();
    stage = IntroductionStage.transcribing;
    await io.stop();
    if (_disposed) return;
    _recordCompletedPrompt(result: 'skipped', transcriptPresent: false);
    await _advance();
  }

  Future<void> _advance() async {
    ++_generation;
    _frames.clear();
    seconds = 0;
    transcript = '';
    level = 0;
    alternative = 0;
    error = null;
    promptIndex++;
    stage = promptIndex >= promptCount ? IntroductionStage.review : IntroductionStage.ready;
    if (stage == IntroductionStage.review) {
      _reviewAttempts++;
      PlatformManager.instance.analytics.guidedIntroReviewShown(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        answerCount: answers.length,
        goalPresent: answers.any((answer) => answer.isGoal),
        reviewAttempt: _reviewAttempts,
      );
    } else {
      _recordPromptViewed();
    }
    _emit();
    if (stage == IntroductionStage.ready && _autoStart) await start();
  }

  void changePrompt() {
    if (stage != IntroductionStage.ready || isGoalPrompt) return;
    alternative = (alternative + 1) % 3;
    _emit();
  }

  void setKeep(int index, bool value) {
    if (busy || answers[index].locked) return;
    answers[index].keep = value;
    _emit();
  }

  void edit(int index, String text) {
    if (busy || answers[index].locked) return;
    answers[index].text = text;
  }

  void useOriginalGoal(int index) {
    final answer = answers[index];
    if (busy || answer.locked || answer.originalText == null) return;
    answer.text = answer.originalText!;
    answer.editRevision++;
    _emit();
  }

  Future<void> saveAll() async {
    if (busy || _disposed || stage == IntroductionStage.done) return;
    markStarted();
    _saveAttempts++;
    PlatformManager.instance.analytics.guidedIntroSaveSubmitted(
      sessionId: _sessionId,
      source: flowSource,
      variant: flowVariant,
      selectedAnswerCount: keptCount,
      selectedMemoryCount: answers.where((answer) => answer.keep && !answer.isGoal).length,
      goalSelected: answers.any((answer) => answer.isGoal && answer.keep),
      voiceAttempted: !voiceSaved,
      attempt: _saveAttempts,
    );
    if (answers.any((a) => a.isGoal && a.keep && a.text.trim().length > 500)) {
      error = 'goalLong';
      _emit();
      return;
    }
    _savingAll = true;
    error = null;
    try {
      if (!voiceSaved) await _saveVoice();
      if (_disposed) return;
      voiceError = voiceSaved ? null : error;
      await _saveMemories();
      if (_disposed) return;
      stage = voiceSaved && allMemoriesSaved ? IntroductionStage.done : IntroductionStage.review;
      if (stage == IntroductionStage.done) _recordTerminal(completionMode: 'saved');
    } finally {
      _savingAll = false;
      _emit();
    }
  }

  /// Voice enrollment and memory writes have independent receipts. Keep the
  /// same audio across failed uploads and confirmed content across memory retries.
  Future<void> saveVoice() async {
    if (busy || voiceSaved || _disposed) return;
    await _saveVoice();
    voiceError = voiceSaved ? null : error;
  }

  Future<void> _saveVoice() async {
    final pcm = BytesBuilder();
    for (final answer in answers) {
      pcm.add(answer.audio);
    }
    if (pcm.length < 5 * 32000) {
      error = 'short';
      stage = IntroductionStage.voiceError;
      _voiceAttempts++;
      PlatformManager.instance.analytics.guidedIntroVoiceEnrollment(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        result: 'short',
        durationMs: 0,
        attempt: _voiceAttempts,
      );
      _emit();
      return;
    }
    final generation = _generation;
    stage = IntroductionStage.savingVoice;
    error = null;
    _emit();
    _voiceAttempts++;
    final voiceStartedAt = DateTime.now();
    try {
      final audio = pcm.takeBytes();
      // Four prompt caps can overshoot by one native buffer each. Respect the
      // upload contract without throwing away the full answers used for review.
      final saved = await io.enroll(Uint8List.sublistView(audio, 0, min(audio.length, 180 * 32000)));
      if (!_current(generation)) return;
      voiceSaved = saved;
      stage = saved ? IntroductionStage.review : IntroductionStage.voiceError;
      if (!saved) error = 'upload';
      PlatformManager.instance.analytics.guidedIntroVoiceEnrollment(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        result: saved ? 'success' : 'failure',
        durationMs: DateTime.now().difference(voiceStartedAt).inMilliseconds,
        attempt: _voiceAttempts,
      );
    } on VoiceEnrollmentUnavailable {
      if (!_current(generation)) return;
      stage = IntroductionStage.voiceError;
      error = 'voiceUnavailable';
      PlatformManager.instance.analytics.guidedIntroVoiceEnrollment(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        result: 'unavailable',
        durationMs: DateTime.now().difference(voiceStartedAt).inMilliseconds,
        attempt: _voiceAttempts,
      );
    } catch (_) {
      if (!_current(generation)) return;
      stage = IntroductionStage.voiceError;
      error = 'upload';
      PlatformManager.instance.analytics.guidedIntroVoiceEnrollment(
        sessionId: _sessionId,
        source: flowSource,
        variant: flowVariant,
        result: 'failure',
        durationMs: DateTime.now().difference(voiceStartedAt).inMilliseconds,
        attempt: _voiceAttempts,
      );
    }
    _emit();
  }

  void addSample() {
    if (busy || _disposed) return;
    // An optional additional sample preserves the previous answers and audio.
    promptIndex = promptCount - 1;
    _extraSample = true;
    alternative = 1;
    stage = IntroductionStage.ready;
    error = null;
    _emit();
  }

  Future<void> saveMemories() async {
    if (busy || _disposed) return;
    markStarted();
    await _saveMemories();
  }

  Future<void> _saveMemories() async {
    final generation = _generation;
    stage = IntroductionStage.savingMemories;
    error = null;
    _emit();
    String? saveError;
    var memoryAttempted = 0;
    var memorySaved = 0;
    var memoryFailed = 0;
    var goalResult = 'not_selected';
    for (final answer in answers.where((a) => a.keep && !a.saved && a.text.trim().isNotEmpty)) {
      if (!_current(generation)) return;
      try {
        if (answer.isGoal && answer.text.trim().length > 500) {
          PlatformManager.instance.analytics.guidedIntroContentSave(
            sessionId: _sessionId,
            source: flowSource,
            variant: flowVariant,
            memoryAttempted: memoryAttempted,
            memorySaved: memorySaved,
            memoryFailed: memoryFailed,
            goalResult: 'failed',
            attempt: _saveAttempts,
          );
          stage = IntroductionStage.review;
          error = 'goalLong';
          _emit();
          return;
        }
        if (answer.isGoal) {
          goalResult = 'attempted';
        } else {
          memoryAttempted++;
        }
        if (answer.isGoal) answer.submittedGoal ??= answer.text.trim();
        final saved =
            answer.isGoal ? await io.saveGoal(answer.submittedGoal!, answer.id) : await io.remember(answer.text.trim());
        if (!_current(generation)) return;
        answer.saved = saved;
        if (answer.isGoal) {
          goalResult = saved ? 'saved' : 'failed';
        } else if (saved) {
          memorySaved++;
        } else {
          memoryFailed++;
        }
        _emit();
        if (!saved) {
          saveError = answer.isGoal ? 'goal' : 'memories';
        }
      } catch (_) {
        saveError = answer.isGoal ? 'goal' : 'memories';
        if (answer.isGoal) {
          goalResult = 'failed';
        } else {
          memoryFailed++;
        }
      }
    }
    if (!_current(generation)) return;
    PlatformManager.instance.analytics.guidedIntroContentSave(
      sessionId: _sessionId,
      source: flowSource,
      variant: flowVariant,
      memoryAttempted: memoryAttempted,
      memorySaved: memorySaved,
      memoryFailed: memoryFailed,
      goalResult: goalResult,
      attempt: _saveAttempts,
    );
    stage = allMemoriesSaved && !_savingAll ? IntroductionStage.done : IntroductionStage.review;
    if (!allMemoriesSaved) {
      error = saveError ?? 'memories';
    }
    _emit();
  }

  void markSkipped() {
    if (_disposed) return;
    markStarted();
    _recordTerminal(completionMode: 'skipped');
  }

  @override
  void dispose() {
    if (_startedTelemetry && !_terminalTelemetry) _recordTerminal(completionMode: 'abandoned');
    _disposed = true;
    ++_generation;
    _previewTimer?.cancel();
    unawaited(io.close());
    super.dispose();
  }
}
