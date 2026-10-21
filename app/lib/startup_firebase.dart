import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// The `firebase_core` error code raised when `initializeApp` is asked to create
/// an app that the native SDK has already created with different parameters.
const String _duplicateAppCode = 'duplicate-app';

/// Bring up the Firebase app for the current engine without letting a
/// configuration mismatch take the whole app down.
///
/// The check this replaces was `if (Firebase.apps.isEmpty) initializeApp()`, and
/// it guaranteed nothing: `Firebase.apps` is empty until the *Dart* side calls
/// `initializeApp`, even when a native `[DEFAULT]` app is already running — on
/// Android `FirebaseInitProvider` creates it from `google-services.json` before
/// any Dart code runs, and on macOS the native SDK does the same. The real check
/// lives *inside* `initializeApp`: `firebase_core` pulls in the native apps and
/// throws `[core/duplicate-app]` when our `apiKey` / `databaseURL` /
/// `storageBucket` disagree with the native ones
/// (`firebase_core_platform_interface/method_channel_firebase.dart`).
///
/// That throw only reproduces on a device, and it is fatal: it escapes startup
/// before the first frame, so `runApp` is never reached for the real UI and the
/// user gets `StartupFailureApp` ("Omi could not start") — while a perfectly
/// usable native Firebase app sits right next to it. A configuration mismatch is
/// worth complaining loudly about; it is not worth refusing to start over.
///
/// So `duplicate-app` is no longer fatal: the app that already exists is adopted
/// and run through the same [validateProject] check, which means a genuinely
/// foreign Firebase project is still caught and still fails startup.
///
/// [existingApp] must return the already-initialized app, or `null` when there
/// is none — callers pass `() => Firebase.apps.isEmpty ? null : Firebase.app()`,
/// because `Firebase.app()` throws instead of returning `null`.
///
/// Generic over the app type so it can be unit-tested: `FirebaseApp` has no
/// public constructor, and obtaining a real one needs a live platform channel.
/// Kept in its own library, free of the generated `firebase_options_*` imports,
/// for the same reason `startup_auth.dart` is separate — it stays testable
/// without codegen.
///
/// Not test-only: called from `main.dart` by both `_init()` and the FCM
/// background handler, and directly by `startup_firebase_duplicate_app_test.dart`.
Future<T> ensureFirebaseApp<T extends Object>({
  required T? Function() existingApp,
  required String configuredProjectId,
  required Future<T> Function() initializeApp,
  required String Function(T app) projectIdOf,
  required void Function(String projectId) validateProject,
}) async {
  final alreadyRunning = existingApp();
  if (alreadyRunning != null) {
    debugPrint('Firebase already initialized.');
    validateProject(projectIdOf(alreadyRunning));
    return alreadyRunning;
  }

  validateProject(configuredProjectId);
  try {
    return await initializeApp();
  } on FirebaseException catch (error) {
    if (error.code != _duplicateAppCode) rethrow;

    // `duplicate-app` is only thrown when a native app already exists, so this
    // is expected to be non-null. If it somehow is not, the original failure is
    // the more useful one to report.
    final native = existingApp();
    if (native == null) rethrow;

    final nativeProjectId = projectIdOf(native);
    debugPrint(
      'Firebase was already initialized natively (project $nativeProjectId) with parameters that '
      'differ from ours (project $configuredProjectId); continuing with the existing app.',
    );
    validateProject(nativeProjectId);
    return native;
  }
}
