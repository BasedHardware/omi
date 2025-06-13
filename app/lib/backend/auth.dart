import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:google_sign_in/google_sign_in.dart' as standard_google_sign_in;
import 'package:google_sign_in_all_platforms/google_sign_in_all_platforms.dart' as all_platforms_google_sign_in;
import 'package:omi/utils/platform/platform_service.dart';
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

final String _googleClientId = Env.googleClientId!;
final String _googleClientSecret = Env.googleClientSecret!;

// Custom HTML page for post-authentication redirect
const String _customPostAuthHtml = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Complete - Omi</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            min-height: 100vh;
            overflow: hidden;
            position: relative;
            background: linear-gradient(180deg, #8B5CF6 0%, #EC4899 50%, #F59E0B 100%);
        }
        
        /* Landscape background */
        .landscape {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 60%;
            z-index: 1;
            opacity: 0;
            animation: fadeIn 1s ease-out 0.1s forwards;
        }
        
        /* Mountains */
        .mountain-1 {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 80%;
            background: linear-gradient(45deg, #4C1D95 0%, #7C2D92 100%);
            clip-path: polygon(0% 100%, 20% 40%, 35% 60%, 50% 20%, 70% 50%, 85% 30%, 100% 70%, 100% 100%);
            opacity: 0;
            animation: slideInFromBottom 1.5s ease-out 0.2s forwards;
        }
        
        .mountain-2 {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 60%;
            background: linear-gradient(45deg, #6B21A8 0%, #BE185D 100%);
            clip-path: polygon(0% 100%, 15% 60%, 30% 40%, 45% 70%, 60% 20%, 75% 45%, 90% 35%, 100% 80%, 100% 100%);
            opacity: 0;
            animation: slideInFromBottom 1.5s ease-out 0.4s forwards;
        }
        
        .mountain-3 {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 40%;
            background: linear-gradient(45deg, #7C3AED 0%, #EC4899 100%);
            clip-path: polygon(0% 100%, 25% 50%, 40% 70%, 55% 30%, 70% 60%, 85% 40%, 100% 75%, 100% 100%);
            opacity: 0;
            animation: slideInFromBottom 1.5s ease-out 0.6s forwards;
        }
        

        
        /* Main content */
        .container {
            position: relative;
            z-index: 10;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            min-height: 100vh;
            text-align: center;
            padding: 2rem;
            padding-top: 20vh;
        }
        
        .success-icon {
            width: 80px;
            height: 80px;
            background: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            animation: float 3s ease-in-out infinite;
        }
        
        .success-icon svg {
            width: 40px;
            height: 40px;
            fill: #10B981;
        }
        
        h1 {
            font-size: 2.5rem;
            font-weight: 400;
            color: white;
            margin: 0;
            text-shadow: 0 2px 20px rgba(0, 0, 0, 0.2);
            opacity: 0;
            animation: fadeInUp 1s ease-out 0.5s forwards;
        }
        
        /* Close instruction */
        .close-instruction {
            display: flex;
            flex-direction: column;
            align-items: center;
            color: white;
            font-size: 16px;
            font-weight: 400;
            margin-top: 2rem;
            opacity: 0;
            animation: fadeInUp 1s ease-out 1.2s forwards;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
        }
        
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        @keyframes bounce {
            0%, 20%, 50%, 80%, 100% {
                transform: rotate(-25deg) translateY(0);
            }
            40% {
                transform: rotate(-25deg) translateY(-8px);
            }
            60% {
                transform: rotate(-25deg) translateY(-4px);
            }
        }
        
        /* Subtle particles */
        .particle {
            position: absolute;
            width: 3px;
            height: 3px;
            background: rgba(255, 255, 255, 0.7);
            border-radius: 50%;
            pointer-events: none;
            animation: twinkle 4s infinite linear;
        }
        
        @keyframes slideInFromBottom {
            from {
                opacity: 0;
                transform: translateY(100px);
            }
            to {
                opacity: 0.9;
                transform: translateY(0);
            }
        }
        
        @keyframes pulse {
            0%, 100% { 
                transform: scale(1);
                opacity: 1;
            }
            50% { 
                transform: scale(1.05);
                opacity: 0.8;
            }
        }
        
        @keyframes twinkle {
            0%, 100% { opacity: 0; transform: scale(0); }
            50% { opacity: 1; transform: scale(1); }
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            h1 {
                font-size: 2rem;
            }
            
            .success-icon {
                width: 70px;
                height: 70px;
            }
            
            .success-icon svg {
                width: 35px;
                height: 35px;
            }
            
            .close-instruction {
                font-size: 14px;
                margin-top: 1.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="landscape">
        <div class="mountain-1"></div>
        <div class="mountain-2"></div>
        <div class="mountain-3"></div>
    </div>
    

    
    <div class="container">
        <div class="success-icon">
            <svg viewBox="0 0 24 24">
                <path d="M9,20.42L2.79,14.21L5.21,11.79L9,15.58L18.79,5.79L21.21,8.21L9,20.42Z"/>
            </svg>
        </div>
        
        <h1>You're all signed in</h1>
        
        <div class="close-instruction">
            <span>Close this window to continue</span>
        </div>
    </div>
    
    <script>
        // Create subtle twinkling particles
        function createParticles() {
            for (let i = 0; i < 20; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.top = Math.random() * 50 + '%';
                particle.style.animationDelay = Math.random() * 4 + 's';
                document.body.appendChild(particle);
            }
        }
        
        createParticles();
        
        // Auto-close after 3 seconds as backup
        setTimeout(() => {
            try {
                window.close();
            } catch (e) {
                console.log('Cannot auto-close window');
            }
        }, 3000);
        
        // Try to close immediately if possible
        try {
            window.close();
        } catch (e) {
            console.log('Cannot auto-close window');
        }
    </script>
</body>
</html>
''';

// Create a single GoogleSignIn instance for all platforms to avoid assertion errors
all_platforms_google_sign_in.GoogleSignIn? _googleSignInAllPlatforms;

all_platforms_google_sign_in.GoogleSignIn _getGoogleSignInAllPlatforms() {
  return _googleSignInAllPlatforms ??= all_platforms_google_sign_in.GoogleSignIn(
    params: all_platforms_google_sign_in.GoogleSignInParams(
      clientId: _googleClientId,
      clientSecret: _googleClientSecret,
      scopes: [
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/userinfo.email',
      ],
      redirectPort: 5000,
      customPostAuthPage: _customPostAuthHtml,
    ),
  );
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
      accessToken: appleCredential.authorizationCode,
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

    // Platform-specific Google Sign In implementation
    if (kIsWeb || PlatformService.isDesktop) {
      // Use google_sign_in_all_platforms for Windows, macOS and Web
      return await _signInWithGoogleAllPlatforms();
    } else {
      // Use standard google_sign_in for iOS, Android
      return await _signInWithGoogleStandard();
    }
  } catch (e) {
    debugPrint('Failed to sign in with Google: $e');
    Logger.handle(e, null, message: 'An error occurred while signing in. Please try again later.');
    return null;
  }
}

/// Google Sign In using the standard google_sign_in package (iOS, Android)
Future<UserCredential?> _signInWithGoogleStandard() async {
  debugPrint('Using standard Google Sign In');

  // Trigger the authentication flow
  final standard_google_sign_in.GoogleSignInAccount? googleUser = await standard_google_sign_in.GoogleSignIn(
    scopes: ['profile', 'email'],
  ).signIn();
  debugPrint('Google User: $googleUser');

  // Obtain the auth details from the request
  final standard_google_sign_in.GoogleSignInAuthentication? googleAuth = await googleUser?.authentication;
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
  return _processGoogleSignInResult(result);
}

/// Google Sign In using google_sign_in_all_platforms (Windows, macOS, Web)
Future<UserCredential?> _signInWithGoogleAllPlatforms() async {
  debugPrint('Using Google Sign In All Platforms');

  if (_googleClientId.isEmpty) {
    Logger.error('Google Client ID not configured. Please configure _googleClientId and _googleClientSecret');
    return null;
  }

  // Initialize the all platforms Google Sign In with required params for Windows
  final googleSignIn = _getGoogleSignInAllPlatforms();

  // First, sign out to ensure we get fresh credentials (needed for windows)
  try {
    await googleSignIn.signOut();
    debugPrint('Signed out from Google (all platforms) to get fresh credentials');
  } catch (e) {
    debugPrint('Error signing out from Google: $e');
  }

  // Trigger the authentication flow
  final all_platforms_google_sign_in.GoogleSignInCredentials? credentials = await googleSignIn.signIn();

  if (credentials == null) {
    debugPrint('Google Sign In was cancelled by user or failed');
    return null;
  }

  // For all platforms package, we only get accessToken, so we need to make an API call to get user info
  // and create a custom token for Firebase (this is more complex)
  // For now, let's create a credential with just the access token
  final credential = GoogleAuthProvider.credential(
    accessToken: credentials.accessToken,
    idToken: credentials.idToken, // May be null
  );

  try {
    // Once signed in, return the UserCredential
    var result = await FirebaseAuth.instance.signInWithCredential(credential);
    return _processGoogleSignInResultAllPlatforms(result, credentials);
  } catch (e) {
    debugPrint('Firebase sign-in failed with all platforms credentials: $e');

    // Handle specific invalid credential error by retrying once with fresh auth
    if (e is FirebaseAuthException && e.code == 'invalid-credential') {
      debugPrint('Invalid credential error detected, attempting to retry with fresh authentication...');
      return await _retryGoogleSignInWithFreshAuth();
    }

    Logger.error('Failed to complete Google sign-in. Please try again.');
    return null;
  }
}

/// Retry Google Sign In with completely fresh authentication
Future<UserCredential?> _retryGoogleSignInWithFreshAuth() async {
  try {
    debugPrint('Retrying Google Sign In with fresh authentication');

    // Sign out from Firebase first
    await FirebaseAuth.instance.signOut();

    // Get a fresh GoogleSignIn instance
    final googleSignIn = _getGoogleSignInAllPlatforms();

    // Ensure complete sign out
    await googleSignIn.signOut();

    // Trigger fresh authentication flow
    final all_platforms_google_sign_in.GoogleSignInCredentials? credentials = await googleSignIn.signIn();

    if (credentials == null) {
      return null;
    }

    // Create new credential
    final credential = GoogleAuthProvider.credential(
      accessToken: credentials.accessToken,
      idToken: credentials.idToken,
    );

    // Attempt Firebase sign-in with fresh credential
    var result = await FirebaseAuth.instance.signInWithCredential(credential);
    return _processGoogleSignInResultAllPlatforms(result, credentials);
  } catch (e) {
    debugPrint('Retry with fresh authentication also failed: $e');
    Logger.error('Failed to complete Google sign-in after retry. Please try again later.');
    return null;
  }
}

/// Process the Google Sign In result for standard platforms and update user preferences
Future<UserCredential?> _processGoogleSignInResult(UserCredential result) async {
  var givenName = result.additionalUserInfo?.profile?['given_name'] ?? '';
  var familyName = result.additionalUserInfo?.profile?['family_name'] ?? '';
  var email = result.additionalUserInfo?.profile?['email'] ?? '';

  if (email != null) SharedPreferencesUtil().email = email;
  if (givenName != null) {
    SharedPreferencesUtil().givenName = givenName;
    SharedPreferencesUtil().familyName = familyName;
  }

  debugPrint('signInWithGoogle Email: ${SharedPreferencesUtil().email}');
  debugPrint('signInWithGoogle Name: ${SharedPreferencesUtil().givenName}');
  return result;
}

/// Process the Google Sign In result for all platforms and update user preferences
Future<UserCredential?> _processGoogleSignInResultAllPlatforms(UserCredential result, all_platforms_google_sign_in.GoogleSignInCredentials credentials) async {
  // For all platforms, we might need to fetch user info separately if not available in Firebase result
  var givenName = result.additionalUserInfo?.profile?['given_name'] ?? '';
  var familyName = result.additionalUserInfo?.profile?['family_name'] ?? '';
  var email = result.additionalUserInfo?.profile?['email'] ?? '';

  // If user info is not available, try to get it from the Firebase user
  if (email.isEmpty) {
    email = result.user?.email ?? '';
  }
  if (givenName.isEmpty) {
    var displayName = result.user?.displayName ?? '';
    var nameParts = displayName.split(' ');
    givenName = nameParts.isNotEmpty ? nameParts[0] : '';
    familyName = nameParts.length > 1 ? nameParts.sublist(1).join(' ') : '';
  }

  if (email.isNotEmpty) SharedPreferencesUtil().email = email;
  if (givenName.isNotEmpty) {
    SharedPreferencesUtil().givenName = givenName;
    SharedPreferencesUtil().familyName = familyName;
  }

  debugPrint('signInWithGoogle (All Platforms) Email: ${SharedPreferencesUtil().email}');
  debugPrint('signInWithGoogle (All Platforms) Name: ${SharedPreferencesUtil().givenName}');
  return result;
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
    debugPrint(e.toString());
    return SharedPreferencesUtil().authToken;
  }
}

Future<void> signOut() async {
  await FirebaseAuth.instance.signOut();
  try {
    // Platform-specific Google Sign Out
    if (kIsWeb || PlatformService.isDesktop) {
      // Use google_sign_in_all_platforms for Windows, macOS and Web
      final googleSignIn = _getGoogleSignInAllPlatforms();
      await googleSignIn.signOut();
    } else {
      // Use standard google_sign_in for iOS, Android
      await standard_google_sign_in.GoogleSignIn().signOut();
    }
  } catch (e) {
    debugPrint(e.toString());
  }
  // context.pushReplacementNamed('auth');
}

bool isSignedIn() => FirebaseAuth.instance.currentUser != null && !FirebaseAuth.instance.currentUser!.isAnonymous;

getFirebaseUser() {
  return FirebaseAuth.instance.currentUser;
}

Future<void> updateGivenName(String fullName) async {
  try {
    var user = FirebaseAuth.instance.currentUser;

    SharedPreferencesUtil().givenName = fullName.split(' ')[0];
    if (fullName.split(' ').length > 1) {
      SharedPreferencesUtil().familyName = fullName.split(' ').sublist(1).join(' ');
    }

    if (user == null) {
      debugPrint('Firebase user is null, skipping Firebase profile update');
      return;
    }

    // Try to update Firebase profile with platform-specific handling
    // Skip Firebase updateProfile on Windows due to known crashes and threading issues
    // https://github.com/firebase/flutterfire/issues/13340
    // https://github.com/firebase/flutterfire/issues/12725
    if (PlatformService.isWindows) {
      debugPrint('Skipping Firebase updateProfile on Windows due to known platform issues');
    } else {
      try {
        debugPrint('Attempting to update Firebase user profile...');

        // Web and other desktop platforms may still have issues, so use timeout
        if (kIsWeb || PlatformService.isDesktop) {
          debugPrint('Desktop/Web platform detected - attempting updateProfile with caution');

          // Try with a timeout to prevent hanging
          await user.updateProfile(displayName: fullName).timeout(
            const Duration(seconds: 5),
            onTimeout: () {
              debugPrint('updateProfile timed out on desktop platform');
              throw TimeoutException('updateProfile timed out', const Duration(seconds: 5));
            },
          );
        } else {
          await user.updateProfile(displayName: fullName);
        }
        await user.reload();
        user = FirebaseAuth.instance.currentUser;
      } catch (updateError) {
        debugPrint('Firebase updateProfile failed (this is expected on windows): $updateError');
      }
    }
  } catch (e) {
    debugPrint('Error in updateGivenName: $e');

    // Ensure SharedPreferences are updated even if everything else fails
    try {
      SharedPreferencesUtil().givenName = fullName.split(' ')[0];
      if (fullName.split(' ').length > 1) {
        SharedPreferencesUtil().familyName = fullName.split(' ').sublist(1).join(' ');
      }
      debugPrint('SharedPreferences updated despite error');
    } catch (prefError) {
      debugPrint('Failed to update SharedPreferences: $prefError');
    }
  }
}

Future<void> signInAnonymously() async {
  try {
    await FirebaseAuth.instance.signInAnonymously();
    var user = FirebaseAuth.instance.currentUser!;
    SharedPreferencesUtil().uid = user.uid;
    await getIdToken();
  } catch (e) {
    Logger.handle(e, null, message: 'An error occurred while signing in. Please try again later.');
  }
}

/// Platform-specific Google account linking with current Firebase user
Future<UserCredential?> linkWithGoogle() async {
  try {
    debugPrint('Linking Google account with current Firebase user');

    // Platform-specific Google Sign In implementation for linking
    if (kIsWeb || PlatformService.isDesktop) {
      // Use google_sign_in_all_platforms for Windows, macOS and Web
      return await _linkWithGoogleAllPlatforms();
    } else {
      // Use standard google_sign_in for iOS, Android
      return await _linkWithGoogleStandard();
    }
  } catch (e) {
    debugPrint('Failed to link with Google: $e');
    Logger.handle(e, null, message: 'Failed to link with Google, please try again.');
    rethrow;
  }
}

/// Link Google account using the standard google_sign_in package (iOS, Android)
Future<UserCredential?> _linkWithGoogleStandard() async {
  debugPrint('Using standard Google Sign In for linking');

  final standard_google_sign_in.GoogleSignInAccount? googleUser = await standard_google_sign_in.GoogleSignIn().signIn();
  if (googleUser == null) {
    return null;
  }

  final standard_google_sign_in.GoogleSignInAuthentication googleAuth = await googleUser.authentication;
  final credential = GoogleAuthProvider.credential(
    accessToken: googleAuth.accessToken,
    idToken: googleAuth.idToken,
  );

  try {
    return await FirebaseAuth.instance.currentUser?.linkWithCredential(credential);
  } catch (e) {
    if (e is FirebaseAuthException && e.code == 'credential-already-in-use') {
      // Handle existing credential case
      return await _handleExistingCredential(e);
    }
    rethrow;
  }
}

/// Link Google account using google_sign_in_all_platforms (Windows, macOS, Web)
Future<UserCredential?> _linkWithGoogleAllPlatforms() async {
  debugPrint('Using Google Sign In All Platforms for linking');

  if (_googleClientId.isEmpty) {
    Logger.error('Google Client ID not configured. Please configure _googleClientId and _googleClientSecret');
    return null;
  }

  final googleSignIn = _getGoogleSignInAllPlatforms();

  final all_platforms_google_sign_in.GoogleSignInCredentials? credentials = await googleSignIn.signIn();
  if (credentials == null) {
    return null;
  }

  final credential = GoogleAuthProvider.credential(
    accessToken: credentials.accessToken,
    idToken: credentials.idToken,
  );

  try {
    return await FirebaseAuth.instance.currentUser?.linkWithCredential(credential);
  } catch (e) {
    if (e is FirebaseAuthException && e.code == 'credential-already-in-use') {
      // Handle existing credential case
      return await _handleExistingCredential(e);
    }
    rethrow;
  }
}

/// Handle the case when credential is already in use
Future<UserCredential?> _handleExistingCredential(FirebaseAuthException e) async {
  // Get existing user credentials
  final existingCred = e.credential;
  final oldUserId = FirebaseAuth.instance.currentUser?.uid;

  // Sign out current anonymous user
  await FirebaseAuth.instance.signOut();

  // Sign in with existing account
  final result = await FirebaseAuth.instance.signInWithCredential(existingCred!);
  final newUserId = FirebaseAuth.instance.currentUser?.uid;
  await getIdToken();

  SharedPreferencesUtil().onboardingCompleted = false;
  SharedPreferencesUtil().uid = newUserId ?? '';
  SharedPreferencesUtil().email = FirebaseAuth.instance.currentUser?.email ?? '';
  SharedPreferencesUtil().givenName = FirebaseAuth.instance.currentUser?.displayName?.split(' ')[0] ?? '';

  return result;
}
