import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

// This probe runs against a disposable Auth emulator and simulator. It substitutes
// provider authorization with the emulator's synthetic provider claims, then uses
// the real Firebase SDK, account-mutation queue, and Omi preferences.
// Start `firebase emulators:start --only auth --project demo-omi-25927` from
// the repository root, then pass the Auth port and the disposable simulator to
// `flutter test --flavor dev --dart-define=OMI_APP_PROFILE=local_dev
// --dart-define=OMI_25927_AUTH_PORT=9099 -d <simulator>
// integration_test/provider_link_collision_emulator_test.dart` from app/.
const _port = int.fromEnvironment('OMI_25927_AUTH_PORT');
const _qaFirebaseOptions = FirebaseOptions(
  apiKey: 'AIzaSyDEMOOMILOCALFAKEKEY00000000000000',
  appId: '1:000000000000:ios:0000000000000000',
  messagingSenderId: '000000000000',
  projectId: 'demo-omi-25927',
  storageBucket: 'demo-omi-25927.localhost',
);

String _claims(String subject) => jsonEncode({
      'sub': subject,
      'email': '$subject@local.test',
      'email_verified': true,
    });

Set<String> _providers(User user) => user.providerData.map((provider) => provider.providerId).toSet();

Future<void> _expectUsableSession(User user) async {
  final token = await user.getIdToken();
  expect(token, isNotNull);
  final http = HttpClient()..connectionTimeout = const Duration(seconds: 5);
  try {
    final request = await http.postUrl(Uri(
      scheme: 'http',
      host: '127.0.0.1',
      port: _port,
      path: '/identitytoolkit.googleapis.com/v1/accounts:lookup',
      queryParameters: {'key': _qaFirebaseOptions.apiKey},
    ));
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({'idToken': token}));
    final response = await request.close();
    expect(response.statusCode, 200);
    final verified = jsonDecode(await utf8.decoder.bind(response).join()) as Map<String, dynamic>;
    final identities = verified['users'] as List<dynamic>;
    expect(identities, hasLength(1));
    expect((identities.single as Map<String, dynamic>)['localId'], user.uid);
  } finally {
    http.close(force: true);
  }
}

class _EmulatorGateway implements AuthTokenGateway {
  _EmulatorGateway(this.auth);

  final FirebaseAuth auth;
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser {
    final user = auth.currentUser;
    if (user == null) return null;
    return AuthUserSnapshot(uid: user.uid, email: user.email, isAnonymous: user.isAnonymous);
  }

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    final result = await auth.currentUser?.getIdTokenResult(true);
    if (result == null) return null;
    return RefreshedAuthToken(token: result.token, expirationTime: result.expirationTime);
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
    await auth.signOut();
  }
}

Future<void> _expectConflict(FirebaseAuth auth, AuthCredential source, AuthCredential occupied, String provider) async {
  final owner = (await auth.signInWithCredential(source)).user!;
  final providers = _providers(owner);
  final activeToken = await owner.getIdToken();
  final prefs = SharedPreferencesUtil()
    ..uid = owner.uid
    ..email = owner.email!
    ..givenName = 'Original profile'
    ..onboardingCompleted = true
    ..authToken = activeToken!;
  final gateway = _EmulatorGateway(auth);
  final service = AuthService.forTesting(
    tokenGateway: gateway,
    firebaseAuth: auth,
    authorizeProviderLink: (_) async => occupied,
  );
  final snapshot = service.captureSessionSnapshot(expectedUid: owner.uid)!;
  final generations = <int>[];
  final changes = service.sessionGenerationEvents.listen(generations.add);
  final authorization = ProviderLinkAuthorization();
  try {
    final link = provider == 'apple' ? service.linkWithApple : service.linkWithGoogle;
    await expectLater(
      link(expectedOwnerUid: owner.uid, authorization: authorization),
      throwsA(isA<ProviderLinkConflict>()),
    );
    expect(gateway.signOutCalls, 0);
    expect(generations, isEmpty);
    expect(service.isSessionSnapshotCurrent(snapshot), isTrue);
    expect(auth.currentUser?.uid, owner.uid);
    expect(prefs.uid, owner.uid);
    expect(prefs.email, owner.email);
    expect(prefs.givenName, 'Original profile');
    expect(prefs.onboardingCompleted, isTrue);
    expect(prefs.authToken, activeToken);
    await auth.currentUser!.reload();
    expect(_providers(auth.currentUser!), providers);
    await _expectUsableSession(auth.currentUser!);
  } finally {
    authorization.dispose();
    await changes.cancel();
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('established collision keeps both identities and only an unclaimed provider can link', (tester) async {
    expect(Platform.isIOS, isTrue, reason: 'Run on the disposable iOS simulator');
    expect(_port, inInclusiveRange(1, 65535), reason: 'An explicit loopback Auth emulator port is required');
    await tester.runAsync(() async {
      await SharedPreferencesUtil.init();
      Env.overrideApiBaseUrl('http://127.0.0.1:$_port/');
      final app = await Firebase.initializeApp(name: 'omi-25927-auth-proof', options: _qaFirebaseOptions);
      final auth = FirebaseAuth.instanceFor(app: app);
      await auth.useAuthEmulator('127.0.0.1', _port);

      try {
        final apple = OAuthProvider('apple.com').credential(idToken: _claims('fixture-apple-25927'));
        final google = GoogleAuthProvider.credential(idToken: _claims('fixture-google-25927'));
        final appleUid = (await auth.signInWithCredential(apple)).user!.uid;
        final googleUid = (await auth.signInWithCredential(google)).user!.uid;
        expect(googleUid, isNot(appleUid));

        await _expectConflict(auth, apple, google, 'google');
        await _expectConflict(auth, google, apple, 'apple');
        for (final (credential, uid, provider) in [(apple, appleUid, 'apple.com'), (google, googleUid, 'google.com')]) {
          final user = (await auth.signInWithCredential(credential)).user!;
          expect(user.uid, uid);
          expect(_providers(user), {provider});
        }

        final appleUser = (await auth.signInWithCredential(apple)).user!;
        final token = await appleUser.getIdToken();
        final prefs = SharedPreferencesUtil()
          ..uid = appleUser.uid
          ..email = appleUser.email!
          ..givenName = 'Original profile'
          ..onboardingCompleted = true
          ..authToken = token!;
        final unused = GoogleAuthProvider.credential(idToken: _claims('fixture-unused-25927'));
        final gateway = _EmulatorGateway(auth);
        final authorized = Completer<AuthCredential>();
        final service = AuthService.forTesting(
          tokenGateway: gateway,
          firebaseAuth: auth,
          authorizeProviderLink: (_) => authorized.future,
        );
        final owner = service.captureSessionSnapshot(expectedUid: appleUid)!;

        final cancelled = ProviderLinkAuthorization();
        final cancelledLink = service.linkWithGoogle(expectedOwnerUid: appleUid, authorization: cancelled);
        cancelled.cancel();
        expect(await cancelledLink, isNull);
        cancelled.dispose();
        authorized.complete(unused);
        await auth.currentUser!.reload();
        expect(_providers(auth.currentUser!), {'apple.com'});
        expect(service.isSessionSnapshotCurrent(owner), isTrue);

        final approved = ProviderLinkAuthorization();
        final result = await service.linkWithGoogle(expectedOwnerUid: appleUid, authorization: approved);
        expect(approved.canCancel, isFalse);
        approved.dispose();
        expect(result?.destinationUid, appleUid);
        expect(result?.anonymousSourceMigration, isNull);
        expect(gateway.signOutCalls, 0);
        expect(auth.currentUser?.uid, appleUid);
        expect(service.isSessionSnapshotCurrent(owner), isTrue);
        expect(prefs.uid, appleUid);
        expect(prefs.email, appleUser.email);
        expect(prefs.givenName, 'Original profile');
        expect(prefs.onboardingCompleted, isTrue);
        expect(prefs.authToken, token);
        expect(_providers(auth.currentUser!), {'apple.com', 'google.com'});
        final linkedUser = (await auth.signInWithCredential(unused)).user!;
        expect(linkedUser.uid, appleUid);
        await _expectUsableSession(linkedUser);
        expect((await auth.signInWithCredential(google)).user?.uid, googleUid);
      } finally {
        await auth.signOut();
        await app.delete();
        Env.clearApiBaseUrlOverrideForTesting();
      }
    });
  });
}
