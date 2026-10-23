import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

enum PowerCycleSubState { waitingForOff, deviceOff, waitingForReconnect, reconnected }

class DeviceOnboardingProvider extends ChangeNotifier {
  DeviceOnboardingProvider({
    this.questionPendingTimeout = const Duration(seconds: 65),
  });

  static const int transcriptionStep = 0;
  static const int askQuestionStep = 1;
  static const int voiceReplyStep = 2;
  static const int powerCycleStep = 3;
  static const int doublePressStep = 4;
  static const int allSetStep = 5;
  static const int totalSteps = 6;
  static const int _wordThreshold = 5;

  final Duration questionPendingTimeout;

  int currentStep = 0;
  bool isOnboardingActive = false;

  // Step 0: Transcription demo
  List<TranscriptSegment> demoSegments = [];
  int wordCount = 0;
  bool transcriptionComplete = false;

  // Step 1: Single press - ask a question
  bool voiceSessionActive = false;
  bool questionSent = false;
  String? userQuestion;
  String? aiResponse;
  // True right after a question failed (no speech, codec/device, quota, transport/timeout, etc.)
  // so the step shows a localized retry/limit explanation instead of processing forever.
  bool questionFailed = false;
  VoiceQuestionFailure? questionFailure;

  int _questionAttemptId = 0;
  int get activeQuestionAttemptId => _questionAttemptId;
  Timer? _questionTimeoutTimer;

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
  bool get isDisposed => _disposed;

  bool get canStartQuestionAttempt {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep) return false;
    return !voiceSessionActive && !questionSent && aiResponse == null;
  }

  void startOnboarding() {
    currentStep = transcriptionStep;
    isOnboardingActive = true;
    _resetOnboardingState();
    notifyListeners();
  }

  void _resetOnboardingState() {
    _questionAttemptId++;
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = null;
    demoSegments = [];
    wordCount = 0;
    transcriptionComplete = false;
    voiceSessionActive = false;
    questionSent = false;
    userQuestion = null;
    aiResponse = null;
    questionFailed = false;
    questionFailure = null;
    selectedVoiceResponseMode = null;
    powerCycleState = PowerCycleSubState.waitingForOff;
    selectedDoubleTapAction = -1;
    doublePressCount = 0;
    showSingleTapHint = false;
    reviewingFromSummary = false;
    _hintTimer?.cancel();
    _hintTimer = null;
  }

  void _retireUnansweredQuestionAttempt() {
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = null;
    if (aiResponse == null && (voiceSessionActive || questionSent)) {
      _questionAttemptId++;
      voiceSessionActive = false;
      questionSent = false;
    }
  }

  void advanceStep() {
    if (currentStep < totalSteps - 1) {
      if (currentStep == askQuestionStep) {
        _retireUnansweredQuestionAttempt();
      }
      currentStep++;
      notifyListeners();
    }
  }

  void goToStep(int step) {
    if (step < transcriptionStep || step >= totalSteps || step == currentStep) return;
    if (currentStep == askQuestionStep) {
      _retireUnansweredQuestionAttempt();
    }
    reviewingFromSummary = currentStep == allSetStep;
    currentStep = step;
    notifyListeners();
  }

  void returnToSummary() {
    if (currentStep == askQuestionStep) {
      _retireUnansweredQuestionAttempt();
    }
    reviewingFromSummary = false;
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
    _retireUnansweredQuestionAttempt();
    isOnboardingActive = false;
    _hintTimer?.cancel();
    _hintTimer = null;
    notifyListeners();
  }

  // --- Step 0: Transcription ---

  void onTranscriptSegments(List<TranscriptSegment> segments) {
    if (currentStep != transcriptionStep || transcriptionComplete) return;

    demoSegments = segments;
    int count = 0;
    for (final seg in segments) {
      count += seg.text.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
    }
    wordCount = count;

    if (wordCount >= _wordThreshold && !transcriptionComplete) {
      transcriptionComplete = true;
    }
    notifyListeners();
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
    if (buttonState != 1) return;

    if (!voiceSessionActive) {
      onVoiceQuestionListeningStarted();
    } else {
      onVoiceQuestionSubmitted();
    }
  }

  int? onVoiceQuestionListeningStarted() {
    if (!canStartQuestionAttempt) return null;
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = null;
    _questionAttemptId++;
    voiceSessionActive = true;
    questionSent = false;
    questionFailed = false;
    questionFailure = null;
    userQuestion = null;
    notifyListeners();
    return _questionAttemptId;
  }

  int? onVoiceQuestionSubmitted({int? attemptId}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep || !voiceSessionActive) {
      return null;
    }
    if (attemptId != null && attemptId != _questionAttemptId) return null;
    voiceSessionActive = false;
    questionSent = true;
    questionFailed = false;
    questionFailure = null;
    final submittedAttempt = _questionAttemptId;
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = Timer(questionPendingTimeout, () {
      if (_disposed) return;
      onVoiceQuestionFailed(
        failure: VoiceQuestionFailure.timeout,
        attemptId: submittedAttempt,
      );
    });
    notifyListeners();
    return submittedAttempt;
  }

  void cancelVoiceQuestionAttempt({int? attemptId}) {
    if (_disposed || currentStep != askQuestionStep || aiResponse != null) return;
    if (attemptId != null && attemptId != _questionAttemptId) return;
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = null;
    _questionAttemptId++;
    voiceSessionActive = false;
    questionSent = false;
    notifyListeners();
  }

  void onVoiceQuestionTranscribed(String question, {int? attemptId}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep) return;
    if (!questionSent || aiResponse != null) return;
    if (attemptId != null && attemptId != _questionAttemptId) return;
    final trimmed = question.trim();
    if (trimmed.isEmpty || userQuestion == trimmed) return;
    userQuestion = trimmed;
    notifyListeners();
  }

  void onVoiceResponseReceived(String response, {String? question, int? attemptId}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep) return;
    if (aiResponse != null) return;
    if (attemptId != null && attemptId != _questionAttemptId) return;
    final trimmed = response.trim();
    if (trimmed.isEmpty) {
      onVoiceQuestionFailed(
        failure: VoiceQuestionFailure.failed,
        question: question,
        attemptId: attemptId,
      );
      return;
    }
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = null;
    if (question != null && question.trim().isNotEmpty) {
      userQuestion = question.trim();
    }
    voiceSessionActive = false;
    questionSent = true;
    questionFailed = false;
    questionFailure = null;
    aiResponse = response;
    notifyListeners();
  }

  /// Capture's 15 s voice-command timeout sent the question without the second press this step
  /// counts, so move on to "Processing" exactly as the second press would (#20786).
  void onQuestionAutoSubmitted() {
    onVoiceQuestionSubmitted();
  }

  /// The question failed (no speech, codec/device, quota, transport/timeout, etc.).
  /// Reset back to the pre-press state with a failure reason so the step shows
  /// a localized retry/limit explanation instead of processing forever.
  void onVoiceQuestionFailed({
    VoiceQuestionFailure failure = VoiceQuestionFailure.noSpeech,
    String? question,
    int? attemptId,
  }) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep || aiResponse != null) return;
    if (attemptId != null && attemptId != _questionAttemptId) return;
    _questionTimeoutTimer?.cancel();
    _questionTimeoutTimer = null;
    _questionAttemptId++;
    if (question != null && question.trim().isNotEmpty) {
      userQuestion = question.trim();
    }
    voiceSessionActive = false;
    questionSent = false;
    questionFailed = true;
    questionFailure = failure;
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
    _questionAttemptId++;
    _questionTimeoutTimer?.cancel();
    _hintTimer?.cancel();
    super.dispose();
  }
}
