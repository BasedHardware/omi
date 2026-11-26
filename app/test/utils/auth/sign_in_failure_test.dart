import 'dart:async';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/auth/sign_in_failure.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

void main() {
  test('sign-in providers are only apple and google', () {
    expect(signInProvider('apple'), SignInStartedProvider.apple);
    expect(signInProvider('google'), SignInStartedProvider.google);
    expect(signInProvider('local_dev'), isNull);
    expect(signInFailedProvider('email'), isNull);
  });

  test('sign-in failures stay in a closed class and do not keep exception text', () {
    expect(
      classifySignInFailure(
        const SignInWithAppleAuthorizationException(code: AuthorizationErrorCode.canceled, message: 'x'),
      ),
      SignInFailedErrorClass.cancelled,
    );
    expect(
      classifySignInFailure(
        const SignInWithAppleAuthorizationException(code: AuthorizationErrorCode.failed, message: 'x'),
      ),
      SignInFailedErrorClass.credential,
    );
    expect(
      classifySignInFailure(FirebaseAuthException(code: 'network-request-failed', message: 'secret')),
      SignInFailedErrorClass.network,
    );
    expect(
      classifySignInFailure(FirebaseAuthException(code: 'invalid-credential')),
      SignInFailedErrorClass.credential,
    );
    expect(
      classifySignInFailure(FirebaseAuthException(code: 'operation-not-allowed')),
      SignInFailedErrorClass.configuration,
    );
    expect(classifySignInFailure(const SocketException('down')), SignInFailedErrorClass.network);
    expect(classifySignInFailure(TimeoutException('slow')), SignInFailedErrorClass.network);
    expect(classifySignInFailure(Exception('raw user message')), SignInFailedErrorClass.unknown);
  });

  test('failure detail keeps the Apple and Firebase code, never the message', () {
    SignInFailureDetailErrorCode apple(AuthorizationErrorCode code) =>
        classifySignInFailureCode(SignInWithAppleAuthorizationException(code: code, message: 'secret'));
    expect(apple(AuthorizationErrorCode.unknown), SignInFailureDetailErrorCode.appleUnknown);
    expect(apple(AuthorizationErrorCode.failed), SignInFailureDetailErrorCode.appleFailed);
    expect(apple(AuthorizationErrorCode.canceled), SignInFailureDetailErrorCode.appleCanceled);
    expect(apple(AuthorizationErrorCode.notHandled), SignInFailureDetailErrorCode.appleNotHandled);
    expect(
      classifySignInFailureCode(const SignInWithAppleNotSupportedException(message: 'x')),
      SignInFailureDetailErrorCode.appleNotSupported,
    );
    expect(
      classifySignInFailureCode(const AppleIdentityTokenMissing()),
      SignInFailureDetailErrorCode.appleMissingIdentityToken,
    );
    expect(classifySignInFailure(const AppleIdentityTokenMissing()), SignInFailedErrorClass.credential);

    SignInFailureDetailErrorCode firebase(String code, [String? message]) =>
        classifySignInFailureCode(FirebaseAuthException(code: code, message: message));
    expect(firebase('invalid-credential'), SignInFailureDetailErrorCode.firebaseInvalidCredential);
    expect(
      firebase('invalid-credential', 'The supplied auth credential is malformed or has expired.'),
      SignInFailureDetailErrorCode.firebaseInvalidCredential,
    );
    expect(
      firebase('invalid-credential', 'The audience in ID Token [x] does not match the expected audience y.'),
      SignInFailureDetailErrorCode.firebaseInvalidCredentialAudience,
    );
    expect(
      firebase('invalid-credential', 'ID token issued at 1 is stale to sign-in.'),
      SignInFailureDetailErrorCode.firebaseInvalidCredentialStale,
    );
    expect(
      firebase('invalid-credential', 'Invalid OAuth response from apple.com'),
      SignInFailureDetailErrorCode.firebaseInvalidIdpResponse,
    );
    expect(firebase('missing-or-invalid-nonce'), SignInFailureDetailErrorCode.firebaseMissingOrInvalidNonce);
    expect(
      firebase('account-exists-with-different-credential'),
      SignInFailureDetailErrorCode.firebaseAccountExistsWithDifferentCredential,
    );
    expect(firebase('network-request-failed'), SignInFailureDetailErrorCode.firebaseNetworkRequestFailed);
    expect(firebase('something-new'), SignInFailureDetailErrorCode.firebaseOther);

    expect(classifySignInFailureCode(TimeoutException('slow')), SignInFailureDetailErrorCode.timeout);
    expect(classifySignInFailureCode(const SocketException('down')), SignInFailureDetailErrorCode.network);
    expect(classifySignInFailureCode(Exception('raw user message')), SignInFailureDetailErrorCode.other);
  });

  test('only an Apple user cancel counts as a cancellation', () {
    expect(
      isSignInCancellation(
        const SignInWithAppleAuthorizationException(code: AuthorizationErrorCode.canceled, message: 'x'),
      ),
      isTrue,
    );
    expect(
      isSignInCancellation(
        const SignInWithAppleAuthorizationException(code: AuthorizationErrorCode.unknown, message: 'x'),
      ),
      isFalse,
    );
    expect(isSignInCancellation(FirebaseAuthException(code: 'invalid-credential')), isFalse);
  });
}
