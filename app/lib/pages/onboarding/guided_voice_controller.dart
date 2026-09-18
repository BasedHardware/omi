import 'dart:async';
import 'dart:typed_data';
import 'dart:math';

import 'package:flutter/foundation.dart';
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
  GuidedVoiceController(this.io);
  final GuidedVoiceIO io;
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
  final _sessionId = DateTime.now().microsecondsSinceEpoch.toString();

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
      _previewTimer = Timer.periodic(const Duration(seconds: 3), (_) => _updatePreview(generation));
    } catch (_) {
      if (!_current(generation)) return;
      stage = IntroductionStage.paused;
      error = 'microphone';
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
      await _advance();
    } catch (_) {
      if (!_current(generation)) return;
      stage = IntroductionStage.paused;
      error = 'transcription';
      _emit();
    }
  }

  Future<void> skipPrompt() async {
    if (busy || _disposed) return;
    ++_generation;
    _previewTimer?.cancel();
    stage = IntroductionStage.transcribing;
    await io.stop();
    if (_disposed) return;
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
      _emit();
      return;
    }
    final generation = _generation;
    stage = IntroductionStage.savingVoice;
    error = null;
    _emit();
    try {
      final audio = pcm.takeBytes();
      // Four prompt caps can overshoot by one native buffer each. Respect the
      // upload contract without throwing away the full answers used for review.
      final saved = await io.enroll(Uint8List.sublistView(audio, 0, min(audio.length, 180 * 32000)));
      if (!_current(generation)) return;
      voiceSaved = saved;
      stage = saved ? IntroductionStage.review : IntroductionStage.voiceError;
      if (!saved) error = 'upload';
    } on VoiceEnrollmentUnavailable {
      if (!_current(generation)) return;
      stage = IntroductionStage.voiceError;
      error = 'voiceUnavailable';
    } catch (_) {
      if (!_current(generation)) return;
      stage = IntroductionStage.voiceError;
      error = 'upload';
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
    await _saveMemories();
  }

  Future<void> _saveMemories() async {
    final generation = _generation;
    stage = IntroductionStage.savingMemories;
    error = null;
    _emit();
    String? saveError;
    for (final answer in answers.where((a) => a.keep && !a.saved && a.text.trim().isNotEmpty)) {
      if (!_current(generation)) return;
      try {
        if (answer.isGoal && answer.text.trim().length > 500) {
          stage = IntroductionStage.review;
          error = 'goalLong';
          _emit();
          return;
        }
        if (answer.isGoal) answer.submittedGoal ??= answer.text.trim();
        final saved =
            answer.isGoal ? await io.saveGoal(answer.submittedGoal!, answer.id) : await io.remember(answer.text.trim());
        if (!_current(generation)) return;
        answer.saved = saved;
        _emit();
        if (!saved) {
          saveError = answer.isGoal ? 'goal' : 'memories';
        }
      } catch (_) {
        saveError = answer.isGoal ? 'goal' : 'memories';
      }
    }
    if (!_current(generation)) return;
    stage = allMemoriesSaved && !_savingAll ? IntroductionStage.done : IntroductionStage.review;
    if (!allMemoriesSaved) {
      error = saveError ?? 'memories';
    }
    _emit();
  }

  @override
  void dispose() {
    _disposed = true;
    ++_generation;
    _previewTimer?.cancel();
    unawaited(io.close());
    super.dispose();
  }
}
