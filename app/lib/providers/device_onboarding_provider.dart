import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

enum PowerCycleSubState {
  waitingForOff,
  deviceOff,
  waitingForReconnect,
  reconnected,
}

class DeviceOnboardingProvider extends ChangeNotifier {
  static const int totalSteps = 4;
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

  // Step 2: Power cycle
  PowerCycleSubState powerCycleState = PowerCycleSubState.waitingForOff;

  // Step 3: Double press config
  int selectedDoubleTapAction = 0;
  bool doublePressDetected = false;
  bool showSingleTapHint = false;

  Timer? _hintTimer;

  void startOnboarding() {
    currentStep = 0;
    isOnboardingActive = true;
    _resetStepState();
    notifyListeners();
  }

  void _resetStepState() {
    demoSegments = [];
    wordCount = 0;
    transcriptionComplete = false;
    voiceSessionActive = false;
    questionSent = false;
    aiResponse = null;
    powerCycleState = PowerCycleSubState.waitingForOff;
    selectedDoubleTapAction = SharedPreferencesUtil().doubleTapAction;
    doublePressDetected = false;
    showSingleTapHint = false;
    _hintTimer?.cancel();
    _hintTimer = null;
  }

  void advanceStep() {
    if (currentStep < totalSteps - 1) {
      currentStep++;
      _resetStepState();
      notifyListeners();
    }
  }

  void completeOnboarding() {
    isOnboardingActive = false;
    _hintTimer?.cancel();
    _hintTimer = null;
    notifyListeners();
  }

  // --- Step 0: Transcription ---

  void onTranscriptSegments(List<TranscriptSegment> segments) {
    if (currentStep != 0 || transcriptionComplete) return;

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
      case 1:
        _handleStep1Button(buttonState);
        break;
      case 2:
        // Button events not used for power cycle — we detect disconnect/reconnect instead
        break;
      case 3:
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
    if (currentStep != 1) return;
    aiResponse = response;
    notifyListeners();
  }

  // --- Step 2: Power cycle ---

  void onDeviceDisconnected() {
    if (currentStep != 2) return;
    if (powerCycleState == PowerCycleSubState.waitingForOff) {
      powerCycleState = PowerCycleSubState.deviceOff;
      notifyListeners();

      // After short delay, transition to waiting for reconnect
      Future.delayed(const Duration(seconds: 1), () {
        if (powerCycleState == PowerCycleSubState.deviceOff) {
          powerCycleState = PowerCycleSubState.waitingForReconnect;
          notifyListeners();
        }
      });
    }
  }

  void onDeviceReconnected() {
    if (currentStep != 2) return;
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
    doublePressDetected = false;
    notifyListeners();
  }

  void _handleStep3Button(int buttonState) {
    if (buttonState == 1) {
      showSingleTapHint = true;
      notifyListeners();
      return;
    }
    if (buttonState != 2) return;
    showSingleTapHint = false;
    doublePressDetected = true;
    // Save the selected action
    SharedPreferencesUtil().doubleTapAction = selectedDoubleTapAction;
    notifyListeners();
  }

  @override
  void dispose() {
    _hintTimer?.cancel();
    super.dispose();
  }
}
