// Local-only Firebase options for the emulator harness.
// These values are intentionally non-secret placeholders. They keep the
// client project identity aligned with demo-omi-local while Auth is routed to
// the local emulator by main.dart.
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
      case TargetPlatform.windows:
      case TargetPlatform.linux:
      case TargetPlatform.fuchsia:
        throw UnsupportedError(
          'Local Firebase options are not configured for this platform.',
        );
    }
  }

  static const android = FirebaseOptions(
    apiKey: 'local-firebase-auth-emulator-api-key',
    appId: '1:000000000000:android:omi-dev-local',
    messagingSenderId: '000000000000',
    projectId: 'demo-omi-local',
    storageBucket: 'demo-omi-local.localhost',
  );

  static const ios = FirebaseOptions(
    apiKey: 'local-firebase-auth-emulator-api-key',
    appId: '1:000000000000:ios:omi-dev-local',
    messagingSenderId: '000000000000',
    projectId: 'demo-omi-local',
    storageBucket: 'demo-omi-local.localhost',
    iosBundleId: 'com.friend-app-with-wearable.ios12.development',
  );

  static const macos = FirebaseOptions(
    apiKey: 'local-firebase-auth-emulator-api-key',
    appId: '1:000000000000:ios:omi-dev-local',
    messagingSenderId: '000000000000',
    projectId: 'demo-omi-local',
    storageBucket: 'demo-omi-local.localhost',
    iosBundleId: 'com.friend-app-with-wearable.ios12.development',
  );

  static const web = FirebaseOptions(
    apiKey: 'local-firebase-auth-emulator-api-key',
    appId: '1:000000000000:web:omi-dev-local',
    messagingSenderId: '000000000000',
    projectId: 'demo-omi-local',
    authDomain: 'demo-omi-local.firebaseapp.com',
    storageBucket: 'demo-omi-local.localhost',
  );
}
