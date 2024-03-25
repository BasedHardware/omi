import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import "../../env/env.dart";

Future initFirebase() async {
  if (kIsWeb) {
    await Firebase.initializeApp(
        options: const FirebaseOptions(
            apiKey: Env.firebaseApiKey,
            authDomain: Env.firebaseAuthDomain,
            projectId: Env.firebaseProjectId,
            storageBucket: Env.firebaseStorageBucket,
            messagingSenderId: Env.firebaseMessageSenderId,
            appId: Env.firebaseAppId,
            measurementId: Env.firebaseMeasurementId));
  } else {
    await Firebase.initializeApp();
  }
}
