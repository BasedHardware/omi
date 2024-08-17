import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

/// Generates a cryptographically secure random nonce, to be included in a
/// credential request.
String generateNonce([int length = 32]) {
  const charset = '0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._';
  final random = Random.secure();
  return List.generate(length, (_) => charset[random.nextInt(charset.length)]).join();
}

/// Returns the sha256 hash of [input] in hex notation.
String sha256ofString(String input) {
  final bytes = utf8.encode(input);
  final digest = sha256.convert(bytes);
  return digest.toString();
}

Future<UserCredential> signInWithApple() async {
  // To prevent replay attacks with the credential returned from Apple, we
  // include a nonce in the credential request. When signing in with
  // Firebase, the nonce in the id token returned by Apple, is expected to
  // match the sha256 hash of `rawNonce`.
  final rawNonce = generateNonce();
  final nonce = sha256ofString(rawNonce);
  // Request credential for the currently signed in Apple account.
  final appleCredential = await SignInWithApple.getAppleIDCredential(
    scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
    nonce: nonce,
  );

  // will be null if it's not first signIn
  if (appleCredential.email != null) {
    SharedPreferencesUtil().email = appleCredential.email!;
  }
  if (appleCredential.givenName != null) {
    SharedPreferencesUtil().givenName = appleCredential.givenName!;
    SharedPreferencesUtil().familyName = appleCredential.familyName ?? '';
  }

  // Create an `OAuthCredential` from the credential returned by Apple.
  final oauthCredential = OAuthProvider("apple.com").credential(
    idToken: appleCredential.identityToken,
    rawNonce: rawNonce,
  );

  // Sign in the user with Firebase. If the nonce we generated earlier does
  // not match the nonce in `appleCredential.identityToken`, sign in will fail.
  UserCredential userCred = await FirebaseAuth.instance.signInWithCredential(oauthCredential);
  var user = FirebaseAuth.instance.currentUser!;
  if (appleCredential.givenName != null) {
    user.updateProfile(displayName: SharedPreferencesUtil().fullName);
  } else {
    var nameParts = user.displayName?.split(' ');
    SharedPreferencesUtil().givenName = nameParts?[0] ?? '';
    SharedPreferencesUtil().familyName = nameParts?[nameParts.length - 1] ?? '';
  }
  if (SharedPreferencesUtil().email.isEmpty) {
    SharedPreferencesUtil().email = user.email ?? '';
  }

  debugPrint('signInWithApple Name: ${SharedPreferencesUtil().fullName}');
  debugPrint('signInWithApple Email: ${SharedPreferencesUtil().email}');
  return userCred;
}

Future<UserCredential?> signInWithGoogle() async {
  try {
    print('Signing in with Google');
    // Trigger the authentication flow
    final GoogleSignInAccount? googleUser = await GoogleSignIn().signIn();
    print('Google User: $googleUser');
    // Obtain the auth details from the request
    final GoogleSignInAuthentication? googleAuth = await googleUser?.authentication;
    print('Google Auth: $googleAuth');

    // Create a new credential
    // TODO: store email + name, need to?
    final credential = GoogleAuthProvider.credential(
      accessToken: googleAuth?.accessToken,
      idToken: googleAuth?.idToken,
    );

    // Once signed in, return the UserCredential
    var result = await FirebaseAuth.instance.signInWithCredential(credential);
    var givenName = result.additionalUserInfo?.profile?['given_name'] ?? '';
    var familyName = result.additionalUserInfo?.profile?['family_name'] ?? '';
    var email = result.additionalUserInfo?.profile?['email'] ?? '';
    if (email != null) SharedPreferencesUtil().email = email;
    if (givenName != null) {
      SharedPreferencesUtil().givenName = givenName;
      SharedPreferencesUtil().familyName = familyName;
    }
    // TODO: test subsequent signIn
    debugPrint('signInWithGoogle Email: ${SharedPreferencesUtil().email}');
    debugPrint('signInWithGoogle Name: ${SharedPreferencesUtil().givenName}');
    return result;
  } catch (e) {
    debugPrint('Failed to sign in with Google: $e');
    return null;
  }
}

listenAuthTokenChanges() {
  FirebaseAuth.instance.idTokenChanges().listen((User? user) async {
    // SharedPreferencesUtil().authToken = '123:/';
    if (user == null) {
      debugPrint('User is currently signed out or the token has been revoked!');
      SharedPreferencesUtil().authToken = '';
    } else {
      // debugPrint('User is signed in!'); // FIXME, triggered too many times.
      try {
        if (SharedPreferencesUtil().authToken.isEmpty ||
            DateTime.now().millisecondsSinceEpoch > SharedPreferencesUtil().tokenExpirationTime) {
          await getIdToken();
        }
      } catch (e) {
        debugPrint('Failed to get token: $e');
      }
    }
  });
}

Future<String?> getIdToken() async {
  try {
    IdTokenResult? newToken = await FirebaseAuth.instance.currentUser?.getIdTokenResult(true);
    if (newToken?.token != null) {
      SharedPreferencesUtil().uid = FirebaseAuth.instance.currentUser!.uid;
      SharedPreferencesUtil().tokenExpirationTime = newToken?.expirationTime?.millisecondsSinceEpoch ?? 0;
      SharedPreferencesUtil().authToken = newToken?.token ?? '';
    }
    return newToken?.token;
  } catch (e) {
    print(e);
    return SharedPreferencesUtil().authToken;
  }
}

Future<void> signOut(BuildContext context) async {
  await FirebaseAuth.instance.signOut();
  try {
    await GoogleSignIn().signOut();
  } catch (e) {
    debugPrint(e.toString());
  }
  // context.pushReplacementNamed('auth');
}

bool isSignedIn() => FirebaseAuth.instance.currentUser != null;
