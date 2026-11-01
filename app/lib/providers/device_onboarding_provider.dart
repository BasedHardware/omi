import 'package:omi/models/voice_question_result.dart';
import 'dart:async';

import 'package:characters/characters.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

enum PowerCycleSubState { waitingForOff, deviceOff, waitingForReconnect, reconnected }

class DeviceOnboardingProvider extends ChangeNotifier {
  static const int transcriptionStep = 0;
  static const int askQuestionStep = 1;
  static const int voiceReplyStep = 2;
  static const int powerCycleStep = 3;
  static const int doublePressStep = 4;
  static const int allSetStep = 5;
  static const int totalSteps = 6;
  // Enough speech to see live transcription work, in any language: five different words, or four that
  // hold 20 letters (Arabic and Tamil say the example in four long words). [Bracketed] and (parenthesized)
  // non-speech and punctuation don't count; Chinese, Japanese and Thai, written without spaces, count one
  // word per two characters, rounded down. Repeats and a bare greeting are not enough.
  static const int _wordThreshold = 5;
  static const int _longWordsThreshold = 4;
  static const int _longWordsLetters = 20;
  static final RegExp _nonSpeech = RegExp(r'\[[^\]]*\]|\([^)]*\)');
  static final RegExp _wordChar = RegExp(r'[\p{L}\p{M}\p{N}]', unicode: true);
  static final RegExp _unspaced =
      RegExp(r'[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\u30FC]', unicode: true);

  int currentStep = 0;
  bool isOnboardingActive = false;

  // Step 0: Transcription demo
  List<TranscriptSegment> demoSegments = [];
  int wordCount = 0;
  bool transcriptionComplete = false;

  // Step 1: Single press - ask a question
  bool voiceSessionActive = false;
  bool questionSent = false;
  String? aiResponse;
  String? userQuestion;
  VoiceQuestionFailure? questionFailure;
  int _questionAttempt = 0;
  int get questionAttempt => _questionAttempt;
  // True right after a question was dropped empty or came back with no speech
  // detected, so the step can show a retry hint instead of processing forever.
  bool questionFailed = false;

  // Step 2: Voice reply preference. Null until the step is visited so a user
  // who skips the tutorial before this point keeps their existing preference.
  int? selectedVoiceResponseMode;

  // Step 2: Power cycle
  PowerCycleSubState powerCycleState = PowerCycleSubState.waitingForOff;

  // Step 3: Double press config
  int selectedDoubleTapAction = -1; // -1 = none selected
  int doublePressCount = 0;
  bool showSingleTapHint = false;

  /// A step reopened from the All Set summary; finishing it goes back to the summary instead of
  /// walking through every later step again (#20787).
  bool reviewingFromSummary = false;

  Timer? _hintTimer;
  bool _disposed = false;

  void startOnboarding() {
    currentStep = transcriptionStep;
    isOnboardingActive = true;
    _resetOnboardingState();
    notifyListeners();
  }

  void _resetOnboardingState() {
    demoSegments = [];
    wordCount = 0;
    transcriptionComplete = false;
    voiceSessionActive = false;
    questionSent = false;
    aiResponse = null;
    userQuestion = null;
    questionFailure = null;
    _questionAttempt++;
    questionFailed = false;
    selectedVoiceResponseMode = null;
    powerCycleState = PowerCycleSubState.waitingForOff;
    selectedDoubleTapAction = -1;
    doublePressCount = 0;
    showSingleTapHint = false;
    reviewingFromSummary = false;
    _hintTimer?.cancel();
    _hintTimer = null;
  }

  void advanceStep() {
    if (currentStep < totalSteps - 1) {
      _questionAttempt++;
      currentStep++;
      notifyListeners();
    }
  }

  void goToStep(int step) {
    if (step < transcriptionStep || step >= totalSteps || step == currentStep) return;
    reviewingFromSummary = currentStep == allSetStep;
    _questionAttempt++;
    currentStep = step;
    notifyListeners();
  }

  void returnToSummary() {
    reviewingFromSummary = false;
    _questionAttempt++;
    currentStep = allSetStep;
    notifyListeners();
  }

  /// Returns true only when the tutorial establishes its initial selection.
  bool initializeVoiceResponseMode({required bool firstRun, required int currentPreference}) {
    if (selectedVoiceResponseMode != null) return false;
    selectedVoiceResponseMode = firstRun ? 0 : currentPreference;
    return true;
  }

  void selectVoiceResponseMode(int mode) {
    if (selectedVoiceResponseMode == mode) return;
    selectedVoiceResponseMode = mode;
    notifyListeners();
  }

  void completeOnboarding() {
    _questionAttempt++;
    isOnboardingActive = false;
    _hintTimer?.cancel();
    _hintTimer = null;
    notifyListeners();
  }

  // --- Step 0: Transcription ---

  void onTranscriptSegments(List<TranscriptSegment> segments) {
    if (currentStep != transcriptionStep || transcriptionComplete) return;

    demoSegments = segments;
    final words = _distinctWords(segments.map((s) => s.text).join(' '));
    wordCount = words.length;
    final letters = words.fold<int>(0, (sum, w) => sum + _wordChar.allMatches(w).length);
    if (wordCount >= _wordThreshold || (wordCount >= _longWordsThreshold && letters >= _longWordsLetters)) {
      transcriptionComplete = true;
    }
    notifyListeners();
  }

  static Set<String> _distinctWords(String text) {
    final words = <String>{};
    final run = <String>[];
    var runUnspaced = false;
    void flush() {
      if (runUnspaced) {
        for (var i = 0; i + 1 < run.length; i += 2) {
          words.add(run[i] + run[i + 1]);
        }
      } else if (run.isNotEmpty) {
        words.add(run.join().toLowerCase());
      }
      run.clear();
    }

    for (final grapheme in text.replaceAll(_nonSpeech, ' ').characters) {
      if (!_wordChar.hasMatch(grapheme)) {
        flush();
        continue;
      }
      final unspaced = _unspaced.hasMatch(grapheme);
      if (run.isNotEmpty && unspaced != runUnspaced) flush();
      runUnspaced = unspaced;
      run.add(grapheme);
    }
    flush();
    return words;
  }

  // --- Step 1: Single press (ask question) ---

  void onButtonEvent(int buttonState) {
    switch (currentStep) {
      case askQuestionStep:
        _handleStep1Button(buttonState);
        break;
      case powerCycleStep:
        // Button events not used for power cycle — we detect disconnect/reconnect instead
        break;
      case doublePressStep:
        _handleStep3Button(buttonState);
        break;
    }
  }

  void _handleStep1Button(int buttonState) {
    if (buttonState != 1 || (questionSent && aiResponse == null)) return;

    if (!voiceSessionActive) {
      onVoiceQuestionStarted();
    } else {
      // Second press — question is being sent
      voiceSessionActive = false;
      questionSent = true;
      notifyListeners();
    }
  }

  /// Capture calls this only after it admits the physical press.
  void onVoiceQuestionStarted() {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep) return;
    _questionAttempt++;
    voiceSessionActive = true;
    questionSent = false;
    questionFailed = false;
    questionFailure = null;
    aiResponse = null;
    userQuestion = null;
    notifyListeners();
  }

  bool acceptsQuestionResult(int attempt) =>
      !_disposed && isOnboardingActive && currentStep == askQuestionStep && attempt == _questionAttempt;

  void onVoiceQuestionFinished(VoiceQuestionResult result, int attempt) {
    if (!acceptsQuestionResult(attempt)) return;
    if (result.answer case final String answer when answer.trim().isNotEmpty) {
      onVoiceResponseReceived(answer, question: result.question);
    } else {
      onVoiceQuestionFailed(result.failure ?? VoiceQuestionFailure.unavailable);
    }
  }

  void onVoiceResponseReceived(String response, {String? question}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep) return;
    voiceSessionActive = false;
    questionSent = true;
    questionFailed = false;
    questionFailure = null;
    userQuestion = question;
    aiResponse = response;
    notifyListeners();
  }

  /// Capture's 15 s voice-command timeout sent the question without the second press this step
  /// counts, so move on to "Processing" exactly as the second press would (#20786).
  void onQuestionAutoSubmitted() {
    if (!isOnboardingActive || currentStep != askQuestionStep || !voiceSessionActive) return;
    voiceSessionActive = false;
    questionSent = true;
    notifyListeners();
  }

  /// The question was dropped before sending (no audio captured) or the
  /// server reported no speech detected. Reset back to the pre-press state
  /// so the step can show a retry hint instead of processing forever.
  void onVoiceQuestionFailed([VoiceQuestionFailure failure = VoiceQuestionFailure.noSpeech]) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep || aiResponse != null) return;
    questionFailure = failure;
    voiceSessionActive = false;
    questionSent = false;
    questionFailed = true;
    notifyListeners();
  }

  // --- Step 2: Power cycle ---

  void onDeviceDisconnected() {
    if (currentStep != powerCycleStep) return;
    if (powerCycleState == PowerCycleSubState.waitingForOff) {
      powerCycleState = PowerCycleSubState.deviceOff;
      notifyListeners();

      // After short delay, transition to waiting for reconnect
      Future.delayed(const Duration(seconds: 1), () {
        if (_disposed) return;
        if (powerCycleState == PowerCycleSubState.deviceOff) {
          powerCycleState = PowerCycleSubState.waitingForReconnect;
          notifyListeners();
        }
      });
    }
  }

  void onDeviceReconnected() {
    if (currentStep != powerCycleStep) return;
    if (powerCycleState == PowerCycleSubState.waitingForReconnect || powerCycleState == PowerCycleSubState.deviceOff) {
      powerCycleState = PowerCycleSubState.reconnected;
      notifyListeners();
    }
  }

  void startPowerCycleHintTimer(VoidCallback onHint) {
    _hintTimer?.cancel();
    _hintTimer = Timer(const Duration(seconds: 30), () {
      if (powerCycleState == PowerCycleSubState.waitingForOff) {
        onHint();
      }
    });
  }

  // --- Step 3: Double press config ---

  void selectDoubleTapAction(int action) {
    selectedDoubleTapAction = action;
    doublePressCount = 0;
    notifyListeners();
  }

  void _handleStep3Button(int buttonState) {
    if (buttonState == 1) {
      showSingleTapHint = true;
      notifyListeners();
      return;
    }
    if (buttonState != 2) return;
    if (selectedDoubleTapAction == -1) return; // no option selected yet
    showSingleTapHint = false;
    doublePressCount++;
    // Save the selected action
    SharedPreferencesUtil().doubleTapAction = selectedDoubleTapAction;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _hintTimer?.cancel();
    super.dispose();
  }
}
