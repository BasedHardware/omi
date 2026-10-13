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
}
