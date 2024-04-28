// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:speech_to_text/speech_to_text.dart' as stt;

Future<bool> isAppMicrophoneActive() async {
  final stt.SpeechToText speech = stt.SpeechToText();
  bool isInitialized = await speech.initialize();
  if (!isInitialized) {
    // Initialization failed, microphone is definitely not running
    return false;
  }

  return speech
      .isListening; // Returns true if microphone is currently in use by your app
}

void main() async {
  bool isMicActive = await isAppMicrophoneActive();
  print('Is microphone active: $isMicActive');
}

// Set your action name, define your arguments and return parameter,
// and then add the boilerplate code using the green button on the right!
