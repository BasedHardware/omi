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

import 'dart:async';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

Future speechToTextWithChunk(
    int callbackSec,
    Future<dynamic> Function()? periodicAction,
    Future<dynamic> Function()? onFinishAction,
    Future<dynamic> Function()? commandResponse) async {
  print("start");
  // List<String> validCommands = [
  //   "ey Sam",
  //   "ey Summer",
  //   "ey Salma"
  // ]; // Add more commands as needed

  Future startListen() async {
    bool _onDevice = false;
    Timer? periodicTimer; // Timer reference
    Timer? statusListenner;
    // Timer? refresh;
    double minSoundLevel = 100000;
    double maxSoundLevel = -50000;
    String _currentLocaleId = '';
    final SpeechToText speech = SpeechToText();

    bool isInitialized = await speech.initialize();
    print("start listenning");
    if (isInitialized) {
      var systemLocale = await speech.systemLocale();
      _currentLocaleId = systemLocale?.localeId ?? '';
      String selectedLanguage = FFAppState().selectedLanguage;
      List<LocaleStruct> languages = FFAppState().languages;
      for (LocaleStruct locale in languages) {
        if (locale.name == selectedLanguage) {
          _currentLocaleId = locale.id;
        }
      }

      // _currentLocaleId = systemLocale?.localeId ?? '';
      periodicTimer =
          Timer.periodic(Duration(seconds: callbackSec), (timer) async {
        if (periodicAction != null) {
          periodicAction.call();
        }
        // statusListenner?.cancel();
        // await speech.stop();
        // await speech.cancel();
        // print("service stop");
        // // refresh?.cancel();
        // periodicTimer?.cancel();
        // await Future.delayed(Duration(seconds: 5), () {
        //   print("delay");
        // });
        // await startListen();
      });
      speech.listen(
        onResult: (result) {
          if (!result.finalResult) {
            // // check for voice commands
            // var limitedTranscript = limitTranscript(result.recognizedWords, 10);
            // if (limitedTranscript != null) {
            //   for (var command in validCommands) {
            //     if (limitedTranscript.contains(command)) {
            //       print("command detected: $command");

            //       // action has check for if action is processing. otherwise will call like 4 times
            //       if (commandResponse != null) {
            //         commandResponse.call();
            //       }
            //       break; // Command recognized, no need to check furthers
            //     }
            //   }
            // }

            FFAppState().update(() {
              // FFAppState().btnTalk = 'listening...';
              FFAppState().stt = '${result.recognizedWords}';
            });
          } else {
            periodicTimer?.cancel();
            statusListenner?.cancel();

            // FFAppState().update(() {
            //   FFAppState().sstSendText = '${result.recognizedWords}';
            //   FFAppState().btnTalk = 'Talk';
            // });
            print("saving last memory");

            if (onFinishAction != null) {
              onFinishAction.call();
            }
          }
        },
        listenFor: Duration(seconds: 4000000000),
        pauseFor: Duration(seconds: 6000),
        partialResults: true,
        localeId: _currentLocaleId,
        onSoundLevelChange: (level) {
          minSoundLevel = min(minSoundLevel, level);
          maxSoundLevel = max(maxSoundLevel, level);
          FFAppState().update(() {
            FFAppState().speechWorkin = true;
          });
          level = level;
        },
        cancelOnError: false,
        listenMode: ListenMode.confirmation,
        onDevice: _onDevice,
      );

      statusListenner = Timer.periodic(Duration(seconds: 2), (timer) {
        // print([DateTime.now(), speech.isAvailable, speech.isListening]);

        if (FFAppState().speechWorkin) {
          print("[WE GOOD]");
          // print('speech Running: ${FFAppState().isSpeechRunning}');
          // print('stop action: ${FFAppState().stopAction}');
          // print(
          //     'speech was activated by user: ${FFAppState().speechWasActivatedByUser}');
        } else {
          FFAppState().update(() {
            FFAppState().isSpeechRunning = false;
          });
          print("[AUDIO STOPPED]");
          print('speech Running: ${FFAppState().isSpeechRunning}');
          print('stop action: ${FFAppState().stopAction}');
          print(
              'speech was activated by user: ${FFAppState().speechWasActivatedByUser}');
        }

        FFAppState().update(() {
          FFAppState().speechWorkin = false;
        });

        if (FFAppState().stopAction) {
          FFAppState().stopAction = false;

          // if (periodicAction != null) {
          //   periodicAction.call();
          // }

          speech.stop();
          speech.cancel();
          periodicTimer?.cancel();
          statusListenner?.cancel();
        }
        // if (speech.isListening != FFAppState().serviceRunnung) {
        //   FFAppState().update(() {
        //     FFAppState().serviceRunnung = speech.isListening;
        //   });
        // }
      });
    }
  }

  await startListen();
}
