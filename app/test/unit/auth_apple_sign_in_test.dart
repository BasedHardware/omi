import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

const _cancelled = SignInWithAppleAuthorizationException(
  code: AuthorizationErrorCode.canceled,
  message: 'The user canceled the authorization attempt.',
);

const _appleCredential = AuthorizationCredentialAppleID(
  userIdentifier: 'apple-user',
  givenName: null,
  familyName: null,
  authorizationCode: 'authorization-code',
  email: null,
  identityToken: 'identity-token',
  state: null,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('AuthService.signInWithAppleMobile', () {
    test('closing the Apple sheet leaves the signed-in session untouched and reports a cancellation', () async {
      final events = <String>[];
      final gateway = _SessionGateway(events, user: const AuthUserSnapshot(uid: 'user-1'));
      final service = _service(gateway, events, appleSheet: () async => throw _cancelled);
      final session = service.captureSessionSnapshot()!;

      Object? outcome;
      try {
        await service.signInWithAppleMobile();
      } catch (error) {
        outcome = error;
      }

      expect(events, ['apple-sheet'], reason: 'nothing may end the session before Apple returns a credential');
      expect(gateway.signOutCalls, 0);
      expect(service.isSessionSnapshotCurrent(session), isTrue);
      expect(outcome, same(_cancelled), reason: 'a cancellation must stay distinguishable from a failure (null)');
    });

    test('an Apple credential ends the previous session before Firebase signs the new user in', () async {
      final events = <String>[];
      final gateway = _SessionGateway(events, user: const AuthUserSnapshot(uid: 'user-1'));
      final userCredential = _FakeUserCredential();
      AuthCredential? firebaseCredential;
      final service = _service(
        gateway,
        events,
        appleSheet: () async => _appleCredential,
        firebaseSignIn: (credential) async {
          firebaseCredential = credential;
          return userCredential;
        },
      );

      final result = await service.signInWithAppleMobile();

      expect(result, same(userCredential));
      expect(events, ['apple-sheet', 'siri', 'firebase-sign-out', 'firebase-sign-in']);
      expect(
        firebaseCredential,
        isA<OAuthCredential>()
            .having((c) => c.providerId, 'providerId', 'apple.com')
            .having((c) => c.idToken, 'idToken', 'identity-token'),
      );
    });

    test('Firebase rejecting the Apple credential is a failure, not a cancellation', () async {
      final events = <String>[];
      final service = _service(
        _SessionGateway(events),
        events,
        appleSheet: () async => _appleCredential,
        firebaseSignIn: (_) async => throw FirebaseAuthException(code: 'invalid-credential'),
      );

      expect(await service.signInWithAppleMobile(), isNull);
    });
  });

  group('AuthenticationProvider.onAppleSignIn', () {
    for (final signedIn in [true, false]) {
      testWidgets('closing the Apple sheet shows no failure copy (${signedIn ? 'signed in' : 'signed out'})',
          (tester) async {
        final events = <String>[];
        final gateway = _SessionGateway(events, user: signedIn ? const AuthUserSnapshot(uid: 'user-1') : null);
        final service = _service(gateway, events, appleSheet: () async => throw _cancelled);
        final provider = _AppleAuthenticationProvider(service.signInWithAppleMobile);
        addTearDown(provider.dispose);
        await tester.pumpWidget(_app());
        var completed = 0;

        await provider.onAppleSignIn(() => completed++);
        await tester.pumpAndSettle();

        expect(find.byType(SnackBar), findsNothing);
        expect(completed, 0);
        expect(gateway.signOutCalls, 0);
      });
    }

    testWidgets('a failed Apple sign-in still shows the failed-sign-in copy', (tester) async {
      final provider = _AppleAuthenticationProvider(() async => null);
      addTearDown(provider.dispose);
      await tester.pumpWidget(_app());

      await provider.onAppleSignIn(() {});
      await tester.pumpAndSettle();

      expect(find.text('Failed to sign in with Apple, please try again.'), findsOneWidget);
    });
  });
}

AuthService _service(
  _SessionGateway gateway,
  List<String> events, {
  required Future<AuthorizationCredentialAppleID> Function() appleSheet,
  FirebaseCredentialSignIn? firebaseSignIn,
}) {
  return AuthService.forTesting(
    tokenGateway: gateway,
    prepareSiriSignOut: () async => events.add('siri'),
    requestAppleCredential: (nonce) async {
      events.add('apple-sheet');
      return appleSheet();
    },
    signInWithCredential: (credential) async {
      events.add('firebase-sign-in');
      final signIn = firebaseSignIn;
      if (signIn == null) return _FakeUserCredential();
      return signIn(credential);
    },
  );
}

Widget _app() => MaterialApp(
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: const Scaffold(),
    );

class _AppleAuthenticationProvider extends AuthenticationProvider {
  _AppleAuthenticationProvider(this._appleSignIn) : super(initializeListeners: false);

  final Future<UserCredential?> Function() _appleSignIn;

  @override
  Future<UserCredential?> signInWithApple() => _appleSignIn();
}

final class _SessionGateway implements AuthTokenGateway {
  _SessionGateway(this.events, {this.user});

  final List<String> events;
  AuthUserSnapshot? user;
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => user;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {
    signOutCalls++;
    events.add('firebase-sign-out');
    user = null;
  }
}

class _FakeUserCredential extends Fake implements UserCredential {
  @override
  User? get user => null;
}
