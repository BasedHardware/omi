import 'dart:async';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import 'package:omi/utils/analytics/registry/events.g.dart';

SignInStartedProvider? signInProvider(String provider) {
  return switch (provider) {
    'apple' => SignInStartedProvider.apple,
    'google' => SignInStartedProvider.google,
    _ => null,
  };
}

SignInFailedProvider? signInFailedProvider(String provider) {
  return switch (provider) {
    'apple' => SignInFailedProvider.apple,
    'google' => SignInFailedProvider.google,
    _ => null,
  };
}

/// Closed class for `Sign In Failed`. Raw exception text never leaves this function.
SignInFailedErrorClass classifySignInFailure(Object error) {
  if (error is SignInWithAppleAuthorizationException) {
    return error.code == AuthorizationErrorCode.canceled
        ? SignInFailedErrorClass.cancelled
        : SignInFailedErrorClass.credential;
  }
  if (error is FirebaseAuthException) {
    return switch (error.code) {
      'network-request-failed' || 'network-error' => SignInFailedErrorClass.network,
      'invalid-credential' ||
      'user-disabled' ||
      'user-not-found' ||
      'wrong-password' ||
      'invalid-verification-code' =>
        SignInFailedErrorClass.credential,
      'operation-not-allowed' ||
      'app-not-authorized' ||
      'invalid-api-key' ||
      'configuration-not-found' =>
        SignInFailedErrorClass.configuration,
      _ => SignInFailedErrorClass.unknown,
    };
  }
  if (error is SocketException || error is TimeoutException || error is HttpException) {
    return SignInFailedErrorClass.network;
  }
  return SignInFailedErrorClass.unknown;
}
