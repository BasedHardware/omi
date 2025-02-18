import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:twitter_login/twitter_login.dart';
import 'package:friend_private/services/twitter_api_service.dart';

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

Future<UserCredential?> signInWithApple() async {
  try {
    // Sign out the current user first
    debugPrint('Signing out current user...');
    await FirebaseAuth.instance.signOut();
    debugPrint('User signed out successfully.');

    final rawNonce = generateNonce();
    final nonce = sha256ofString(rawNonce);

    debugPrint('Requesting Apple credential...');
    final appleCredential = await SignInWithApple.getAppleIDCredential(
      scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
      nonce: nonce,
    );

    debugPrint('Apple credential received.');
    debugPrint('Email: ${appleCredential.email ?? "null"}');
    debugPrint('Given Name: ${appleCredential.givenName ?? "null"}');
    debugPrint('Family Name: ${appleCredential.familyName ?? "null"}');
    debugPrint('Identity Token: ${appleCredential.identityToken != null ? 'Present' : 'Null'}');
    debugPrint('Authorization Code: ${appleCredential.authorizationCode.isNotEmpty ? 'Present' : 'Null'}');

    if (appleCredential.identityToken == null) {
      throw Exception('Apple Sign In failed - no identity token received.');
    }

    // Create an `OAuthCredential` from the credential returned by Apple.
    final oauthCredential = OAuthProvider("apple.com").credential(
      idToken: appleCredential.identityToken,
      rawNonce: rawNonce,
    );

    debugPrint('OAuth Credential created.');
    debugPrint('Provider ID: ${oauthCredential.providerId}');
    debugPrint('Sign-in method: ${oauthCredential.signInMethod}');
    debugPrint('Access Token: ${oauthCredential.accessToken ?? "null"}');
    debugPrint('ID Token: ${oauthCredential.idToken ?? "null"}');

    // Sign in the user with Firebase.
    debugPrint('Attempting to sign in with Firebase...');
    UserCredential userCred = await FirebaseAuth.instance.signInWithCredential(oauthCredential);
    debugPrint('Firebase sign-in successful.');

    // Update user profile and local storage
    var user = FirebaseAuth.instance.currentUser!;
    debugPrint('Firebase User ID: ${user.uid}');
    debugPrint('Firebase User Email: ${user.email ?? "null"}');
    debugPrint('Firebase User Display Name: ${user.displayName ?? "null"}');

    if (appleCredential.email != null) {
      SharedPreferencesUtil().email = appleCredential.email!;
    }
    if (appleCredential.givenName != null) {
      SharedPreferencesUtil().givenName = appleCredential.givenName!;
      SharedPreferencesUtil().familyName = appleCredential.familyName ?? '';
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
  } on FirebaseAuthException catch (e) {
    debugPrint('FirebaseAuthException: ${e.code} - ${e.message}');
    if (e.code == 'invalid-credential') {
      debugPrint('Please check Firebase console configuration for Apple Sign In.');
    }
    return null;
  } catch (e) {
    debugPrint('Error during Apple Sign In: $e');
    Logger.handle(e, null, message: 'An error occurred while signing in. Please try again later.');
    return null;
  }
}

Future<UserCredential?> signInWithGoogle() async {
  try {
    debugPrint('Signing in with Google');
    // Trigger the authentication flow
    final GoogleSignInAccount? googleUser = await GoogleSignIn(scopes: ['profile', 'email']).signIn();
    debugPrint('Google User: $googleUser');

    // Obtain the auth details from the request
    final GoogleSignInAuthentication? googleAuth = await googleUser?.authentication;
    debugPrint('Google Auth: $googleAuth');
    if (googleAuth == null) {
      debugPrint('Failed to sign in with Google: googleAuth is NULL');
      Logger.error('An error occurred while signing in. Please try again later. (Error: 40001)');
      return null;
    }

    // Create a new credential
    if (googleAuth.accessToken == null && googleAuth.idToken == null) {
      debugPrint('Failed to sign in with Google: accessToken, idToken are NULL');
      Logger.error('An error occurred while signing in. Please try again later. (Error: 40002)');
      return null;
    }
    final credential = GoogleAuthProvider.credential(
      accessToken: googleAuth.accessToken,
      idToken: googleAuth.idToken,
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
    Logger.handle(e, null, message: 'An error occurred while signing in. Please try again later.');
    return null;
  }
}

Future<String?> getIdToken() async {
  try {
    IdTokenResult? newToken = await FirebaseAuth.instance.currentUser?.getIdTokenResult(true);
    if (newToken?.token != null) {
      var user = FirebaseAuth.instance.currentUser!;
      SharedPreferencesUtil().uid = user.uid;
      SharedPreferencesUtil().tokenExpirationTime = newToken?.expirationTime?.millisecondsSinceEpoch ?? 0;
      SharedPreferencesUtil().authToken = newToken?.token ?? '';
      if (SharedPreferencesUtil().email.isEmpty) {
        SharedPreferencesUtil().email = user.email ?? '';
      }

      if (SharedPreferencesUtil().givenName.isEmpty) {
        SharedPreferencesUtil().givenName = user.displayName?.split(' ')[0] ?? '';
        if ((user.displayName?.split(' ').length ?? 0) > 1) {
          SharedPreferencesUtil().familyName = user.displayName?.split(' ')[1] ?? '';
        } else {
          SharedPreferencesUtil().familyName = '';
        }
      }
    }
    return newToken?.token;
  } catch (e) {
    print(e);
    return SharedPreferencesUtil().authToken;
  }
}

Future<void> signOut() async {
  await FirebaseAuth.instance.signOut();
  try {
    await GoogleSignIn().signOut();
  } catch (e) {
    debugPrint(e.toString());
  }
  // context.pushReplacementNamed('auth');
}

bool isSignedIn() => FirebaseAuth.instance.currentUser != null;

getFirebaseUser() {
  return FirebaseAuth.instance.currentUser;
}

// update user given name
Future<void> updateGivenName(String fullName) async {
  var user = FirebaseAuth.instance.currentUser;
  if (user != null) {
    await user.updateProfile(displayName: fullName);
  }
}

Future<UserCredential?> signInWithTwitter() async {
  try {
    final twitterLogin = TwitterLogin(
      apiKey: 'hlSXpzpGbuD39MXhUxgRBBQBY',
      apiSecretKey: 'MwcBCAnZhdo0QXcSIpasxJM8bGEZSrtGNG5WyVU6xSUsp8J83L',
      redirectURI: 'omiapp://',
    );

    final authResult = await twitterLogin.login();
    switch (authResult.status) {
      case TwitterLoginStatus.loggedIn:
      
        final twitterAuthCredential = TwitterAuthProvider.credential(
          accessToken: authResult.authToken!,
          secret: authResult.authTokenSecret!,
        );

        // Store Twitter tokens
        SharedPreferencesUtil().twitterAccessToken = authResult.authToken!;
        SharedPreferencesUtil().twitterAccessTokenSecret = authResult.authTokenSecret!;

        // First complete Firebase authentication
        final userCredential = await FirebaseAuth.instance.signInWithCredential(twitterAuthCredential);
        
        // Update user profile in SharedPreferences
        if (userCredential.user != null) {
          SharedPreferencesUtil().uid = userCredential.user!.uid;
          if (userCredential.user!.email != null) {
            SharedPreferencesUtil().email = userCredential.user!.email!;
          }
          if (userCredential.user!.displayName != null) {
            var nameParts = userCredential.user!.displayName!.split(' ');
            SharedPreferencesUtil().givenName = nameParts[0];
            SharedPreferencesUtil().familyName = nameParts.length > 1 ? nameParts[1] : '';
          }
          if (authResult.user?.screenName != null) {
            SharedPreferencesUtil().twitterHandle = authResult.user!.screenName;
          }

          // Now that auth is complete, try to fetch DM events
          try {
            final twitterService = TwitterApiService();
            final dmEvents = await twitterService.getDMEvents();
            print('DM events fetched successfully: ${dmEvents['data']}');
          } catch (e) {
            print('Failed to fetch DM events: $e');
          }
        }
        
        return userCredential;
      case TwitterLoginStatus.cancelledByUser:
        print('Twitter login cancelled by user');
        return null;
      case TwitterLoginStatus.error:
        print('Twitter login error: ${authResult.errorMessage}');
        return null;
      default:
        print('Twitter login unknown error');
        return null;
    }
  } on FirebaseAuthException catch (e) {
    print('Firebase auth error: ${e.message}');
    return null;
  } catch (e) {
    print('Unexpected error during Twitter sign in: $e');
    return null;
  }
}
