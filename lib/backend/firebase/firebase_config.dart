import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

Future initFirebase() async {
  if (kIsWeb) {
    await Firebase.initializeApp(
        options: const FirebaseOptions(
            apiKey: "AIzaSyAI7LOhwfSRQnOoT-nWp5IIIflQFDBaBks",
            authDomain: "voice-76xd7x.firebaseapp.com",
            projectId: "voice-76xd7x",
            storageBucket: "voice-76xd7x.appspot.com",
            messagingSenderId: "909648207363",
            appId: "1:909648207363:web:4cba386dd6824cd2447836",
            measurementId: "G-6HE60EMNCF"));
  } else {
    await Firebase.initializeApp();
  }
}
