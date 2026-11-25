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

SignInFailureDetailProvider? signInFailureDetailProvider(String provider) {
  return switch (provider) {
    'apple' => SignInFailureDetailProvider.apple,
    'google' => SignInFailureDetailProvider.google,
    _ => null,
  };
}

/// `Sign In Failed` with its closed class, then `Sign In Failure Detail` with the
/// provider's own code whenever an error object exists. Unknown providers emit nothing.
List<RegisteredEvent> signInFailureEvents(String provider, {Object? error, bool cancelled = false}) {
  final failed = signInFailedProvider(provider);
  final detail = signInFailureDetailProvider(provider);
  if (failed == null || detail == null) return const [];
  return [
    SignInFailed(
      provider: failed,
      errorClass: cancelled || error == null ? SignInFailedErrorClass.cancelled : classifySignInFailure(error),
    ),
    if (error != null) SignInFailureDetail(provider: detail, errorCode: classifySignInFailureCode(error)),
  ];
}

/// Apple returned a credential without an identity token.
class AppleIdentityTokenMissing implements Exception {
  const AppleIdentityTokenMissing();
}

/// True only when the user dismissed the provider sheet themselves.
bool isSignInCancellation(Object error) =>
    error is SignInWithAppleAuthorizationException && error.code == AuthorizationErrorCode.canceled;

/// Closed class for `Sign In Failed`. Raw exception text never leaves this function.
SignInFailedErrorClass classifySignInFailure(Object error) {
  if (error is SignInWithAppleAuthorizationException) {
    return error.code == AuthorizationErrorCode.canceled
        ? SignInFailedErrorClass.cancelled
        : SignInFailedErrorClass.credential;
  }
  if (error is AppleIdentityTokenMissing) return SignInFailedErrorClass.credential;
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

/// Closed code for `Sign In Failure Detail`: the Apple or Firebase error code,
/// never the raw message. Firebase only puts the server reason for
/// `invalid-credential` in the message, so three known reasons are split out.
SignInFailureDetailErrorCode classifySignInFailureCode(Object error) {
  if (error is SignInWithAppleAuthorizationException) {
    return switch (error.code) {
      AuthorizationErrorCode.canceled => SignInFailureDetailErrorCode.appleCanceled,
      AuthorizationErrorCode.failed => SignInFailureDetailErrorCode.appleFailed,
      AuthorizationErrorCode.invalidResponse => SignInFailureDetailErrorCode.appleInvalidResponse,
      AuthorizationErrorCode.notHandled => SignInFailureDetailErrorCode.appleNotHandled,
      AuthorizationErrorCode.notInteractive => SignInFailureDetailErrorCode.appleNotInteractive,
      AuthorizationErrorCode.unknown => SignInFailureDetailErrorCode.appleUnknown,
      AuthorizationErrorCode.credentialExport => SignInFailureDetailErrorCode.appleCredentialExport,
      AuthorizationErrorCode.credentialImport => SignInFailureDetailErrorCode.appleCredentialImport,
      AuthorizationErrorCode.matchedExcludedCredential => SignInFailureDetailErrorCode.appleMatchedExcludedCredential,
    };
  }
  if (error is SignInWithAppleNotSupportedException) return SignInFailureDetailErrorCode.appleNotSupported;
  if (error is SignInWithAppleCredentialsException) return SignInFailureDetailErrorCode.appleCredentialsError;
  if (error is UnknownSignInWithAppleException) return SignInFailureDetailErrorCode.applePlatformError;
  if (error is AppleIdentityTokenMissing) return SignInFailureDetailErrorCode.appleMissingIdentityToken;
  if (error is FirebaseAuthException) {
    final message = (error.message ?? '').toLowerCase();
    return switch (error.code) {
      'invalid-credential' when message.contains('audience') =>
        SignInFailureDetailErrorCode.firebaseInvalidCredentialAudience,
      'invalid-credential' when message.contains('stale') =>
        SignInFailureDetailErrorCode.firebaseInvalidCredentialStale,
      'invalid-credential' when message.contains('oauth response') =>
        SignInFailureDetailErrorCode.firebaseInvalidIdpResponse,
      'invalid-credential' => SignInFailureDetailErrorCode.firebaseInvalidCredential,
      'missing-or-invalid-nonce' => SignInFailureDetailErrorCode.firebaseMissingOrInvalidNonce,
      'account-exists-with-different-credential' =>
        SignInFailureDetailErrorCode.firebaseAccountExistsWithDifferentCredential,
      'credential-already-in-use' => SignInFailureDetailErrorCode.firebaseCredentialAlreadyInUse,
      'email-already-in-use' => SignInFailureDetailErrorCode.firebaseEmailAlreadyInUse,
      'operation-not-allowed' => SignInFailureDetailErrorCode.firebaseOperationNotAllowed,
      'admin-restricted-operation' => SignInFailureDetailErrorCode.firebaseAdminRestrictedOperation,
      'user-disabled' => SignInFailureDetailErrorCode.firebaseUserDisabled,
      'app-not-authorized' => SignInFailureDetailErrorCode.firebaseAppNotAuthorized,
      'invalid-api-key' => SignInFailureDetailErrorCode.firebaseInvalidApiKey,
      'too-many-requests' => SignInFailureDetailErrorCode.firebaseTooManyRequests,
      'network-request-failed' || 'network-error' => SignInFailureDetailErrorCode.firebaseNetworkRequestFailed,
      'internal-error' => SignInFailureDetailErrorCode.firebaseInternalError,
      _ => SignInFailureDetailErrorCode.firebaseOther,
    };
  }
  if (error is TimeoutException) return SignInFailureDetailErrorCode.timeout;
  if (error is SocketException || error is HttpException) return SignInFailureDetailErrorCode.network;
  return SignInFailureDetailErrorCode.other;
}
