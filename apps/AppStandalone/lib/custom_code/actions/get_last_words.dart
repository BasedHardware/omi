// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<String> getLastWords() async {
  // Add your function code here!

  // Add your function code here!

  /// MODIFY CODE ONLY BELOW THIS LINE

  String lastTranscript = FFAppState().lastTranscript;
  String newestTranscript = FFAppState().stt;
  // String lastMemory = FFAppState().lastMemory;

  // also update w/ latest transcript here
  FFAppState().update(() {
    FFAppState().lastTranscript = newestTranscript;
  });

  int charCount = lastTranscript.length;
  String lastWords = '';
  // Check if the updated transcript is longer than the originall
  if (newestTranscript.length > charCount) {
    // Remove the first 'charCount' characters from the updated transcript
    lastWords = newestTranscript.substring(charCount).trim();
  }

  // FFAppState().update(() {
  //   FFAppState().lastMemory = lastMemory + " " + lastWords;
  // });

  print("[LAST WORDS]: " + lastWords);
  print("[LAST TRANSCRIPT]: " + lastTranscript);
  print("[NEWEST TRANSCRIPT]: " + newestTranscript);
  return lastWords;
}
