import 'dart:async';

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
  String? aiResponse;

  // Step 2: Voice reply preference. Null until the step is visited so a user
  // who skips the tutorial before this point keeps their existing preference.
  int? selectedVoiceResponseMode;

  // Step 2: Power cycle
  PowerCycleSubState powerCycleState = PowerCycleSubState.waitingForOff;

  // Step 3: Double press config
  int selectedDoubleTapAction = -1; // -1 = none selected
  int doublePressCount = 0;
  bool showSingleTapHint = false;

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
    selectedVoiceResponseMode = null;
    powerCycleState = PowerCycleSubState.waitingForOff;
    selectedDoubleTapAction = -1;
    doublePressCount = 0;
    showSingleTapHint = false;
    _hintTimer?.cancel();
    _hintTimer = null;
  }

  void advanceStep() {
    if (currentStep < totalSteps - 1) {
      currentStep++;
      notifyListeners();
    }
  }

  void goToStep(int step) {
    if (step < transcriptionStep || step >= totalSteps || step == currentStep) return;
    currentStep = step;
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
      voiceSessionActive = true;
      notifyListeners();
    } else {
      // Second press — question is being sent
      voiceSessionActive = false;
      questionSent = true;
      notifyListeners();
    }
  }

  void onVoiceResponseReceived(String response) {
    if (currentStep != askQuestionStep) return;
    aiResponse = response;
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
