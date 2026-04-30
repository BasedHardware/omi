// Firebase config for v2 dev. Reuses the legacy `nooto-dev` Firebase project +
// bundle IDs from `app/lib/firebase_options_dev.dart`. Keeping v2 on the same
// Firebase project means no console action is needed and any user signed
// into legacy dev shares the same auth state. Prod cutover (a separate
// `firebase_options_prod.dart` against `nooto-e2d27`) lands later.
//
// ignore_for_file: type=lint
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) return web;
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not configured for $defaultTargetPlatform.',
        );
    }
  }

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyBdx7JCovucC0fegVezAppim5rM3m9FiGw',
    appId: '1:1060764816205:android:732ad23ec2cfe440ac1d04',
    messagingSenderId: '1060764816205',
    projectId: 'nooto-dev',
    storageBucket: 'nooto-dev.firebasestorage.app',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyAp4itVWrAPafKVGN7PYOP7_DPwWrzj5tU',
    appId: '1:1060764816205:ios:ede0246a124508f8ac1d04',
    messagingSenderId: '1060764816205',
    projectId: 'nooto-dev',
    storageBucket: 'nooto-dev.firebasestorage.app',
    iosClientId: '1060764816205-i0hf8fsqc7rqebvah1eefnvgdrh8kcrb.apps.googleusercontent.com',
    iosBundleId: 'com.nooto-app-with-wearable.ios12.development',
  );

  static const FirebaseOptions macos = ios;

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyAPDdy9ZUCMQOPvcbjkB-dQn6WPcPY5nng',
    appId: '1:1060764816205:web:b14d871806bbbe32ac1d04',
    messagingSenderId: '1060764816205',
    projectId: 'nooto-dev',
    authDomain: 'nooto-dev.firebaseapp.com',
    storageBucket: 'nooto-dev.firebasestorage.app',
    measurementId: 'G-J4JGSXBPM3',
  );
}
