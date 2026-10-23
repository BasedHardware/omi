import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

export 'package:omi/services/capture/capture_external_actions.dart' show VoiceQuestionFailure, VoiceQuestionOutcome;

enum PowerCycleSubState { waitingForOff, deviceOff, waitingForReconnect, reconnected }

class DeviceOnboardingProvider extends ChangeNotifier {
  static const int transcriptionStep = 0;
  static const int askQuestionStep = 1;
  static const int voiceReplyStep = 2;
  static const int powerCycleStep = 3;
  static const int doublePressStep = 4;
  static const int allSetStep = 5;
  static const int totalSteps = 6;
  static const int _wordThreshold = 5;

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
  // True right after a question failed to capture or answer, so the step can
  // show a localized retry/limit explanation instead of processing forever.
  bool questionFailed = false;
  VoiceQuestionFailure? questionFailure;
  int _activeAttemptId = 0;

  int get activeAttemptId => _activeAttemptId;

  bool get canStartVoiceQuestion =>
      !_disposed &&
      isOnboardingActive &&
      currentStep == askQuestionStep &&
      !voiceSessionActive &&
      !questionSent &&
      aiResponse == null;

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
    if (_disposed) return;
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
    userQuestion = null;
    aiResponse = null;
    questionFailed = false;
    questionFailure = null;
    _activeAttemptId++;
    selectedVoiceResponseMode = null;
    powerCycleState = PowerCycleSubState.waitingForOff;
    selectedDoubleTapAction = -1;
    doublePressCount = 0;
    showSingleTapHint = false;
    reviewingFromSummary = false;
    _hintTimer?.cancel();
    _hintTimer = null;
  }

  void _invalidateActiveQuestionAttempt() {
    voiceSessionActive = false;
    if (aiResponse == null) {
      questionSent = false;
    }
    _activeAttemptId++;
  }

  void advanceStep() {
    if (_disposed) return;
    if (currentStep < totalSteps - 1) {
      if (currentStep == askQuestionStep) {
        _invalidateActiveQuestionAttempt();
      }
      currentStep++;
      notifyListeners();
    }
  }

  void goToStep(int step) {
    if (_disposed) return;
    if (step < transcriptionStep || step >= totalSteps || step == currentStep) return;
    if (currentStep == askQuestionStep) {
      _invalidateActiveQuestionAttempt();
    }
    reviewingFromSummary = currentStep == allSetStep;
    currentStep = step;
    notifyListeners();
  }

  void returnToSummary() {
    if (_disposed) return;
    if (currentStep == askQuestionStep) {
      _invalidateActiveQuestionAttempt();
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
    if (_disposed || selectedVoiceResponseMode == mode) return;
    selectedVoiceResponseMode = mode;
    notifyListeners();
  }

  void completeOnboarding() {
    if (_disposed) return;
    isOnboardingActive = false;
    _invalidateActiveQuestionAttempt();
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
    if (_disposed || !isOnboardingActive) return;
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
      onVoiceSessionStarted();
    } else {
      // Second press — question is being sent
      onVoiceQuestionSubmitted();
    }
  }

  /// Marks that capture admitted a tutorial voice session and returns its scoped
  /// attempt id. Returns null when the step is not ready to start a new question.
  int? onVoiceSessionStarted() {
    if (!canStartVoiceQuestion) return null;
    _activeAttemptId++;
    voiceSessionActive = true;
    questionSent = false;
    questionFailed = false;
    questionFailure = null;
    userQuestion = null;
    notifyListeners();
    return _activeAttemptId;
  }

  /// Marks the active tutorial voice session as submitted and awaiting a reply.
  bool onVoiceQuestionSubmitted({int? attemptId}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep || !voiceSessionActive) {
      return false;
    }
    if (attemptId != null && attemptId != _activeAttemptId) return false;
    voiceSessionActive = false;
    questionSent = true;
    notifyListeners();
    return true;
  }

  void onVoiceResponseReceived(String response, {String? question, int? attemptId}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep) return;
    if (!questionSent || aiResponse != null) return;
    if (attemptId != null && attemptId != _activeAttemptId) return;
    final trimmed = response.trim();
    if (trimmed.isEmpty) {
      onVoiceQuestionFailed(failure: VoiceQuestionFailure.incomplete, attemptId: attemptId);
      return;
    }
    final trimmedQuestion = question?.trim();
    if (trimmedQuestion != null && trimmedQuestion.isNotEmpty) {
      userQuestion = trimmedQuestion;
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
  void onQuestionAutoSubmitted({int? attemptId}) {
    onVoiceQuestionSubmitted(attemptId: attemptId);
  }

  /// The question was dropped before sending (no audio captured), the server
  /// reported no speech detected, or transport/server/quota failed. Reset back
  /// to the pre-press state with the terminal failure reason so the step can
  /// show a localized retry/limit explanation instead of processing forever.
  void onVoiceQuestionFailed({VoiceQuestionFailure failure = VoiceQuestionFailure.noSpeech, int? attemptId}) {
    if (_disposed || !isOnboardingActive || currentStep != askQuestionStep || aiResponse != null) return;
    if (!voiceSessionActive && !questionSent) return;
    if (attemptId != null && attemptId != _activeAttemptId) return;
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
  void notifyListeners() {
    if (_disposed) return;
    super.notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _invalidateActiveQuestionAttempt();
    _hintTimer?.cancel();
    super.dispose();
  }
}
