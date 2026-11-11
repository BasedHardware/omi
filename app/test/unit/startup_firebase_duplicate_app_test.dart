import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/startup_firebase.dart';

/// Stands in for `FirebaseApp`, which has no public constructor and cannot be
/// obtained without a live platform channel. Only the project id matters here.
class _App {
  const _App(this.projectId);
  final String projectId;
}

/// The exact exception `firebase_core` raises when the Dart-side parameters
/// disagree with the natively-created `[DEFAULT]` app — see `duplicateApp()` in
/// `firebase_core_platform_interface/src/firebase_core_exceptions.dart`.
FirebaseException _duplicateApp() => FirebaseException(
      plugin: 'core',
      code: 'duplicate-app',
      message: 'A Firebase App named "[DEFAULT]" already exists',
    );

/// Mirrors `Env.validateFirebaseProject`: the profile pins one project id.
void Function(String) _validatorFor(String expectedProjectId) => (projectId) {
      if (projectId != expectedProjectId) {
        throw StateError(
          'Mobile profile requires Firebase project $expectedProjectId, '
          'but the app was initialized with $projectId.',
        );
      }
    };

void main() {
  group('ensureFirebaseApp', () {
    test('a duplicate-app from the native [DEFAULT] app does not kill startup', () async {
      // The regression this guards. `Firebase.apps` is empty until the Dart side
      // calls initializeApp, even when Android's FirebaseInitProvider has already
      // created [DEFAULT] from google-services.json. So `if (Firebase.apps.isEmpty)`
      // waved the call through, initializeApp compared our apiKey/databaseURL/
      // storageBucket against the native ones, disagreed, and threw
      // `[core/duplicate-app]`. That throw escaped _init() before the first frame,
      // so runApp() was never reached and the user got StartupFailureApp with
      // "Omi could not start" — with a working native Firebase app right there.
      const native = _App('omi-project');
      var apps = <_App>[];
      var initializeCalls = 0;

      final app = await ensureFirebaseApp<_App>(
        existingApp: () => apps.isEmpty ? null : apps.first,
        configuredProjectId: 'omi-project',
        initializeApp: () async {
          initializeCalls++;
          // Exactly what firebase_core does: the native app becomes visible and
          // the call fails because the parameters did not match.
          apps = [native];
          throw _duplicateApp();
        },
        projectIdOf: (app) => app.projectId,
        validateProject: _validatorFor('omi-project'),
      );

      expect(app, same(native), reason: 'startup must adopt the app that already exists');
      expect(initializeCalls, 1);
    });

    test('a genuinely foreign native project still fails validation', () async {
      // Tolerating duplicate-app must not turn into ignoring it: if the native
      // app really belongs to another Firebase project, startup must still stop.
      const native = _App('someone-elses-project');
      var apps = <_App>[];

      await expectLater(
        ensureFirebaseApp<_App>(
          existingApp: () => apps.isEmpty ? null : apps.first,
          configuredProjectId: 'omi-project',
          initializeApp: () async {
            apps = [native];
            throw _duplicateApp();
          },
          projectIdOf: (app) => app.projectId,
          validateProject: _validatorFor('omi-project'),
        ),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('someone-elses-project'),
          ),
        ),
      );
    });

    test('an already-initialized app is adopted without a second initializeApp', () async {
      // The macOS path the old `else` branch handled, kept intact.
      const native = _App('omi-project');
      var initializeCalls = 0;

      final app = await ensureFirebaseApp<_App>(
        existingApp: () => native,
        configuredProjectId: 'omi-project',
        initializeApp: () async {
          initializeCalls++;
          return const _App('unused');
        },
        projectIdOf: (app) => app.projectId,
        validateProject: _validatorFor('omi-project'),
      );

      expect(app, same(native));
      expect(initializeCalls, 0);
    });

    test('the normal path initializes with our own options', () async {
      const created = _App('omi-project');
      var initializeCalls = 0;

      final app = await ensureFirebaseApp<_App>(
        existingApp: () => null,
        configuredProjectId: 'omi-project',
        initializeApp: () async {
          initializeCalls++;
          return created;
        },
        projectIdOf: (app) => app.projectId,
        validateProject: _validatorFor('omi-project'),
      );

      expect(app, same(created));
      expect(initializeCalls, 1);
    });

    test('a misconfigured flavor still fails before initializeApp runs', () async {
      // Validating our own options up front is the pre-existing behaviour and is
      // deliberately still fatal — this is a build wired to the wrong project.
      var initializeCalls = 0;

      await expectLater(
        ensureFirebaseApp<_App>(
          existingApp: () => null,
          configuredProjectId: 'wrong-project',
          initializeApp: () async {
            initializeCalls++;
            return const _App('wrong-project');
          },
          projectIdOf: (app) => app.projectId,
          validateProject: _validatorFor('omi-project'),
        ),
        throwsStateError,
      );
      expect(initializeCalls, 0, reason: 'a bad flavor must not reach initializeApp');
    });

    test('any other FirebaseException still fails startup', () async {
      // Only duplicate-app is survivable; everything else is a real failure.
      await expectLater(
        ensureFirebaseApp<_App>(
          existingApp: () => null,
          configuredProjectId: 'omi-project',
          initializeApp: () async => throw FirebaseException(plugin: 'core', code: 'no-app'),
          projectIdOf: (app) => app.projectId,
          validateProject: _validatorFor('omi-project'),
        ),
        throwsA(isA<FirebaseException>().having((e) => e.code, 'code', 'no-app')),
      );
    });
  });
}
