import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/auth/sign_in_failure.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

const _appleChannel = MethodChannel('com.aboutyou.dart_packages.sign_in_with_apple');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_appleChannel, null);
  });

  void appleReplies(Future<Object?> Function() reply) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      _appleChannel,
      (call) async => call.method == 'performAuthorizationRequest' ? reply() : null,
    );
  }

  test('Apple error 1000 reaches the caller with its code instead of a silent null', () async {
    appleReplies(() async => throw PlatformException(code: 'authorization-error/unknown', message: 'error 1000'));
    final firebase = _Firebase();
    final service = AuthService.forTesting(tokenGateway: _Gateway(), firebaseAuth: firebase);

    final error = await service.signInWithAppleMobile().then<Object?>((_) => null, onError: (Object e) => e);

    expect(error, isA<SignInWithAppleAuthorizationException>());
    expect(isSignInCancellation(error!), isFalse);
    expect(classifySignInFailure(error), SignInFailedErrorClass.credential);
    expect(classifySignInFailureCode(error), SignInFailureDetailErrorCode.appleUnknown);
    expect(firebase.signIns, 0);
  });

  test('a user cancel stays a cancel', () async {
    appleReplies(() async => throw PlatformException(code: 'authorization-error/canceled', message: 'error 1001'));
    final service = AuthService.forTesting(tokenGateway: _Gateway(), firebaseAuth: _Firebase());

    final error = await service.signInWithAppleMobile().then<Object?>((_) => null, onError: (Object e) => e);

    expect(isSignInCancellation(error!), isTrue);
    expect(classifySignInFailureCode(error), SignInFailureDetailErrorCode.appleCanceled);
  });

  test('a Firebase rejection of the Apple token reaches the caller with its code', () async {
    appleReplies(() async => {
          'type': 'appleid',
          'userIdentifier': 'apple-user',
          'identityToken': 'apple-id-token',
          'authorizationCode': 'apple-code',
        });
    final firebase = _Firebase()
      ..failure = FirebaseAuthException(
        code: 'invalid-credential',
        message: 'The audience in ID Token [com.example] does not match the expected audience.',
      );
    final service = AuthService.forTesting(tokenGateway: _Gateway(), firebaseAuth: firebase);

    final error = await service.signInWithAppleMobile().then<Object?>((_) => null, onError: (Object e) => e);

    expect(firebase.signIns, 1);
    expect(error, isA<FirebaseAuthException>());
    expect(classifySignInFailureCode(error!), SignInFailureDetailErrorCode.firebaseInvalidCredentialAudience);
  });

  test('a credential without an identity token is a typed failure', () async {
    appleReplies(() async => {'type': 'appleid', 'userIdentifier': 'apple-user', 'authorizationCode': 'apple-code'});
    final firebase = _Firebase();
    final service = AuthService.forTesting(tokenGateway: _Gateway(), firebaseAuth: firebase);

    final error = await service.signInWithAppleMobile().then<Object?>((_) => null, onError: (Object e) => e);

    expect(error, isA<AppleIdentityTokenMissing>());
    expect(classifySignInFailureCode(error!), SignInFailureDetailErrorCode.appleMissingIdentityToken);
    expect(firebase.signIns, 0);
  });
}

class _Firebase implements FirebaseAuth {
  int signIns = 0;
  FirebaseAuthException? failure;

  @override
  User? get currentUser => null;

  @override
  Future<UserCredential> signInWithCredential(AuthCredential credential) async {
    signIns++;
    throw failure ?? StateError('unexpected sign-in');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Gateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => null;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {}
}
