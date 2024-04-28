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
import '../../auth/firebase_auth/auth_util.dart';
import '../../backend/push_notifications/push_notifications_util.dart';

Future monitorListenner() async {
  Timer.periodic(Duration(minutes: 5), (timer) {
    if (!FFAppState().isSpeechRunning) {
      DateTime now = DateTime.now();
      if (FFAppState().latestUse == null) {
        FFAppState().latestUse = now;
      }
      if (now.difference(FFAppState().latestUse!).inMinutes > 5) {
        if (currentUserReference != null) {
          triggerPushNotification(
            notificationTitle: 'Sama',
            notificationText:
            'Recording is disabled. Please restart audio recording',
            notificationSound: 'default',
            userRefs: [currentUserReference!],
            initialPageName: 'homePage',
            parameterData: {},
          );
        }

      }
    }
  });
}
