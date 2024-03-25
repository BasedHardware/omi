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

import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:speech_to_text_platform_interface/speech_to_text_platform_interface.dart';

Future<List<LocaleStruct>> listLocales() async {
  // Add your function code here!

  final locales = await SpeechToTextPlatform.instance.locales();
  var filteredLocales = locales
      .map((locale) {
        var components = locale.split(':');
        if (components.length != 2) {
          return null;
        }
        return LocaleName(components[0], components[1]);
      })
      .where((item) => item != null)
      .toList()
      .cast<LocaleName>();
  // if (filteredLocales.isNotEmpty) {
  //   _systemLocale = filteredLocales.first;
  // } else {
  //   _systemLocale = null;
  // }
  filteredLocales.sort((ln1, ln2) => ln1.name.compareTo(ln2.name));

  // Map LocaleName objects to LocaleStruct objects
  List<LocaleStruct> filteredLocalesStruct = filteredLocales
      .map((locale) => LocaleStruct(name: locale.name, id: locale.localeId))
      .toList();

  FFAppState().update(() {
    // FFAppState().btnTalk = 'listening...';
    FFAppState().languages = filteredLocalesStruct;
  });

  return filteredLocalesStruct;
}
