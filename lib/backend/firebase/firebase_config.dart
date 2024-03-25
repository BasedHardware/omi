import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

Future initFirebase() async {
  if (kIsWeb) {
    await Firebase.initializeApp(
        options: FirebaseOptions(
            apiKey: "AIzaSyBW9DBpN2C5j9PELi7DyV24NRJ0DHor92w",
            authDomain: "mistral-sllz6f.firebaseapp.com",
            projectId: "mistral-sllz6f",
            storageBucket: "mistral-sllz6f.appspot.com",
            messagingSenderId: "125067220975",
            appId: "1:125067220975:web:f9b76be37fb8bfef3f881a"));
  } else {
    await Firebase.initializeApp();
  }
}
