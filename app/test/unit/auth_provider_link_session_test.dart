import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

final credential = GoogleAuthProvider.credential(idToken: 'fixture-id-token');
final appleCredential = OAuthProvider('apple.com').credential(idToken: 'fixture-apple-id-token');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('Google OAuth return for A cannot link after B replaced the account', () async {
    final firebase = _Firebase();
    final gateway = _Gateway(firebase);
    final authorizeStarted = Completer<void>();
    final authorization = Completer<AuthCredential>();
    final service = AuthService.forTesting(
        tokenGateway: gateway,
        firebaseAuth: firebase,
        authorizeProviderLink: (_) {
          authorizeStarted.complete();
          return authorization.future;
        });
    final pending = service.linkWithGoogle();
    final rejected = expectLater(pending, throwsStateError);
    await authorizeStarted.future;
    final source = firebase.user!;
    await service.runAccountMutation(() async {
      firebase.user = _User('b');
      service.markAuthenticatedUser('b');
    });
    authorization.complete(credential);
    await rejected;
    expect(source.links, 0);
    expect(source.tokenReads, 0);
    expect(firebase.signIns, 0);
    expect(gateway.signOuts, 0);
    expect(firebase.user!.uid, 'b');
  });

  test('cancelling provider authorization releases the attempt and ignores late credentials', () async {
    final firebase = _Firebase();
    final gateway = _Gateway(firebase);
    final firstAuthorization = Completer<AuthCredential>();
    final secondAuthorization = Completer<AuthCredential>();
    var requests = 0;
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      firebaseAuth: firebase,
      authorizeProviderLink: (_) => (++requests == 1 ? firstAuthorization : secondAuthorization).future,
    );
    final first = ProviderLinkAuthorization();
    addTearDown(first.dispose);
    final second = ProviderLinkAuthorization();
    addTearDown(second.dispose);

    final attempt = service.linkWithGoogle(authorization: first);
    first.cancel();
    expect(await attempt, isNull);
    expect(first.canCancel, isFalse);

    final retry = service.linkWithGoogle(authorization: second);
    firstAuthorization.complete(credential);
    expect(firebase.user!.links, 0);
    final submitted = Completer<void>();
    final completeLink = Completer<UserCredential>();
    firebase.user!.onLink = () {
      submitted.complete();
      return completeLink.future;
    };
    secondAuthorization.complete(credential);
    await submitted.future;
    expect(second.canCancel, isFalse);
    second.cancel();
    completeLink.complete(_Credential(firebase.user!));
    expect((await retry)?.destinationUid, 'a');
    expect(firebase.user!.links, 1);
    expect(gateway.signOuts, 0);
  });

  test('Apple link checks its originating owner inside queue admission', () async {
    final firebase = _Firebase();
    final gateway = _Gateway(firebase);
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      firebaseAuth: firebase,
      authorizeProviderLink: (_) async => appleCredential,
    );
    final entered = Completer<void>();
    final release = Completer<void>();
    final blocker = service.runAccountMutation(() async {
      entered.complete();
      await release.future;
    });
    await entered.future;
    final source = firebase.user!;
    final replacement = service.runAccountMutation(() async {
      firebase.user = _User('b');
      service.markAuthenticatedUser('b');
    });
    final pending = service.linkWithApple();
    final rejected = expectLater(pending, throwsStateError);
    release.complete();
    await Future.wait([blocker, replacement, rejected]);
    expect(source.links, 0);
    expect(source.tokenReads, 0);
    expect(gateway.signOuts, 0);
    expect(firebase.user!.uid, 'b');
  });

  test('submitted Apple link holds the slot until SDK completion', () async {
    final firebase = _Firebase();
    final gateway = _Gateway(firebase);
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      firebaseAuth: firebase,
      authorizeProviderLink: (_) async => appleCredential,
    );
    final entered = Completer<void>();
    final release = Completer<void>();
    firebase.user!.onLink = () async {
      entered.complete();
      await release.future;
      throw FirebaseAuthException(code: 'provider-already-linked');
    };
    final pending = service.linkWithApple();
    final rejected = expectLater(pending, throwsA(isA<FirebaseAuthException>()));
    await entered.future;
    var replacementStarted = false;
    final replacement = service.runAccountMutation(() async {
      replacementStarted = true;
      firebase.user = _User('b');
      service.markAuthenticatedUser('b');
    });
    await Future<void>.delayed(Duration.zero);
    expect(replacementStarted, false);
    release.complete();
    await Future.wait([replacement, rejected]);
    expect(firebase.user!.uid, 'b');
    expect(gateway.signOuts, 0);
  });

  test('late Apple collision never reads or signs out replacement B', () async {
    final firebase = _Firebase();
    final gateway = _Gateway(firebase);
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      firebaseAuth: firebase,
      authorizeProviderLink: (_) async => appleCredential,
    );
    final source = firebase.user!;
    final entered = Completer<void>();
    final release = Completer<void>();
    final replacement = _User('b');
    source.onLink = () async {
      entered.complete();
      await release.future;
      firebase.user = replacement;
      service.markAuthenticatedUser('b');
      throw FirebaseAuthException(code: 'credential-already-in-use', credential: appleCredential);
    };
    final pending = service.linkWithApple();
    final rejected = expectLater(pending, throwsStateError);
    await entered.future;
    expect(source.tokenReads, 1);
    release.complete();
    await rejected;
    expect(replacement.tokenReads, 0);
    expect(firebase.signIns, 0);
    expect(gateway.signOuts, 0);
    expect(firebase.user, same(replacement));
  });

  test('Google collision returns only the proof captured before native linking', () async {
    final firebase = _Firebase();
    final gateway = _Gateway(firebase);
    final source = firebase.user!;
    source.onLink = () async {
      expect(source.tokenReads, 1);
      throw FirebaseAuthException(code: 'credential-already-in-use', credential: credential);
    };
    final service = AuthService.forTesting(
        tokenGateway: gateway, firebaseAuth: firebase, authorizeProviderLink: (_) async => credential);
    final result = await service.linkWithGoogle();
    expect(result!.destinationUid, 'destination');
    expect(result.anonymousSourceMigration!.uid, 'a');
    expect(result.anonymousSourceMigration!.token, 'proof-a');
    expect(source.tokenReads, 1);
    expect(firebase.user!.tokenReads, 0);
    expect(firebase.signIns, 1);
    expect(gateway.signOuts, 1);
    expect(SharedPreferencesUtil().uid, 'destination');
  });

  for (final provider in ['google', 'apple']) {
    for (final code in [
      'credential-already-in-use',
      'account-exists-with-different-credential',
      'email-already-in-use'
    ]) {
      test('$provider $code keeps an established session and profile', () async {
        final source = _User('established');
        final firebase = _Firebase()..user = source;
        final gateway = _Gateway(firebase);
        final service = AuthService.forTesting(
          tokenGateway: gateway,
          firebaseAuth: firebase,
          authorizeProviderLink: (_) async => provider == 'google' ? credential : appleCredential,
        );
        final prefs = SharedPreferencesUtil()
          ..uid = source.uid
          ..givenName = 'Original name'
          ..email = 'original@local.test'
          ..onboardingCompleted = true;
        final session = service.captureSessionSnapshot(expectedUid: source.uid)!;
        source.onLink = () async => throw FirebaseAuthException(
              code: code,
              credential: provider == 'google' ? credential : null,
            );

        final pending = provider == 'google'
            ? service.linkWithGoogle(expectedOwnerUid: source.uid)
            : service.linkWithApple(expectedOwnerUid: source.uid);
        await expectLater(pending, throwsA(isA<ProviderLinkConflict>()));

        expect(firebase.user, same(source));
        expect(firebase.signIns, 0);
        expect(gateway.signOuts, 0);
        expect(source.links, 1);
        expect(source.tokenReads, 0);
        expect(service.isSessionSnapshotCurrent(session), isTrue);
        expect(prefs.uid, source.uid);
        expect(prefs.givenName, 'Original name');
        expect(prefs.email, 'original@local.test');
        expect(prefs.onboardingCompleted, isTrue);
      });
    }

    test('$provider refuses an account change between confirmation and opening OAuth', () async {
      final firebase = _Firebase()..user = _User('replacement');
      final gateway = _Gateway(firebase);
      var authorizations = 0;
      final service = AuthService.forTesting(
        tokenGateway: gateway,
        firebaseAuth: firebase,
        authorizeProviderLink: (_) async {
          authorizations++;
          return credential;
        },
      );

      final pending = provider == 'google'
          ? service.linkWithGoogle(expectedOwnerUid: 'previous')
          : service.linkWithApple(expectedOwnerUid: 'previous');
      await expectLater(pending, throwsStateError);
      expect(authorizations, 0);
      expect(firebase.user!.links, 0);
      expect(firebase.signIns, 0);
      expect(gateway.signOuts, 0);
    });
  }

  test('adding an unused method keeps the established UID, profile and owner generation', () async {
    final source = _User('established');
    final firebase = _Firebase()..user = source;
    final gateway = _Gateway(firebase);
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      firebaseAuth: firebase,
      authorizeProviderLink: (_) async => credential,
    );
    final prefs = SharedPreferencesUtil()
      ..uid = source.uid
      ..givenName = 'Original name'
      ..email = 'original@local.test';
    final session = service.captureSessionSnapshot(expectedUid: source.uid)!;
    source.onLink = () async => _Credential(source);

    final result = await service.linkWithGoogle(expectedOwnerUid: source.uid);

    expect(result?.destinationUid, source.uid);
    expect(result?.destinationSession?.generation, session.generation);
    expect(result?.anonymousSourceMigration, isNull);
    expect(service.isSessionSnapshotCurrent(session), isTrue);
    expect(source.links, 1);
    expect(firebase.signIns, 0);
    expect(gateway.signOuts, 0);
    expect(prefs.givenName, 'Original name');
    expect(prefs.email, 'original@local.test');
  });
}

class _Firebase implements FirebaseAuth {
  _User? user = _User('a', anonymous: true);
  int signIns = 0;
  @override
  User? get currentUser => user;
  @override
  Future<UserCredential> signInWithCredential(AuthCredential credential) async {
    signIns++;
    user = _User('destination');
    return _Credential(user!);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _User implements User {
  _User(this.uid, {this.anonymous = false});
  @override
  final String uid;
  final bool anonymous;
  int links = 0;
  int tokenReads = 0;
  Future<UserCredential> Function()? onLink;
  @override
  bool get isAnonymous => anonymous;
  @override
  String? get email => '$uid@local.test';
  @override
  String? get displayName => uid;
  @override
  Future<String?> getIdToken([bool forceRefresh = false]) async {
    tokenReads++;
    return 'proof-$uid';
  }

  @override
  Future<UserCredential> linkWithCredential(AuthCredential credential) async {
    links++;
    return onLink!();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Credential implements UserCredential {
  _Credential(this.user);
  @override
  final User user;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Gateway implements AuthTokenGateway {
  _Gateway(this.firebase);
  final _Firebase firebase;
  int signOuts = 0;
  @override
  AuthUserSnapshot? get currentUser =>
      firebase.user == null ? null : AuthUserSnapshot(uid: firebase.user!.uid, isAnonymous: firebase.user!.isAnonymous);
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => RefreshedAuthToken(
      token: 'token-${firebase.user!.uid}', expirationTime: DateTime.now().add(const Duration(hours: 1)));
  @override
  Future<void> signOut() async {
    signOuts++;
    firebase.user = null;
  }
}
