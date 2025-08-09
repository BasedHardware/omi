import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/platform/platform_service.dart';

class AuthService {
  static final AuthService _instance = AuthService._internal();
  static AuthService get instance => _instance;
  
  AuthService._internal();

  bool isSignedIn() => FirebaseAuth.instance.currentUser != null && !FirebaseAuth.instance.currentUser!.isAnonymous;

getFirebaseUser() {
  return FirebaseAuth.instance.currentUser;
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

Future<void> signOut() async {
  await FirebaseAuth.instance.signOut();
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

  Future<UserCredential?> authenticateWithProvider(String provider) async {
    try {
      final state = _generateState();
      const redirectUri = 'omi://auth/callback';
      
      debugPrint('Starting OAuth flow for provider: $provider');
      
      final authUrl = '${Env.apiBaseUrl}v1/auth/authorize'
          '?provider=$provider'
          '&redirect_uri=${Uri.encodeComponent(redirectUri)}'
          '&state=$state';
      
      debugPrint('Authorization URL: $authUrl');
      
      final result = await FlutterWebAuth2.authenticate(
        url: authUrl,
        callbackUrlScheme: 'omi',
        options: const FlutterWebAuth2Options(
          intentFlags: ephemeralIntentFlags,
        ),
      );
      
      debugPrint('Authentication result: $result');
      
      final uri = Uri.parse(result);
      final code = uri.queryParameters['code'];
      final returnedState = uri.queryParameters['state'];
      
      if (code == null) {
        throw Exception('No authorization code received');
      }
      
      if (returnedState != state) {
        throw Exception('Invalid state parameter');
      }
      
      // Exchange the code for OAuth credentials
      final oauthCredentials = await _exchangeCodeForOAuthCredentials(code, redirectUri);
      
      if (oauthCredentials == null) {
        throw Exception('Failed to exchange code for OAuth credentials');
      }
      
      // Sign in to Firebase with the OAuth credentials
      final credential = await _signInWithOAuthCredentials(oauthCredentials);
      
      // Update user profile and local storage after successful sign-in
      await _updateUserPreferences(credential, provider);
      
      debugPrint('Firebase authentication successful');
      return credential;
      
    } catch (e) {
      debugPrint('OAuth authentication error: $e');
      Logger.handle(e, StackTrace.current, message: 'Authentication failed');
      return null;
    }
  }

  Future<Map<String, dynamic>?> _exchangeCodeForOAuthCredentials(String code, String redirectUri) async {
    try {
      final response = await http.post(
        Uri.parse('${Env.apiBaseUrl}v1/auth/token'),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: {
          'grant_type': 'authorization_code',
          'code': code,
          'redirect_uri': redirectUri,
        },
      );
      
      debugPrint('Token exchange response status: ${response.statusCode}');
      debugPrint('Token exchange response body: ${response.body}');
      
      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        debugPrint('Token exchange failed: ${response.body}');
        return null;
      }
    } catch (e) {
      debugPrint('Token exchange error: $e');
      return null;
    }
  }

  Future<UserCredential> _signInWithOAuthCredentials(Map<String, dynamic> oauthCredentials) async {
    final provider = oauthCredentials['provider'];
    final idToken = oauthCredentials['id_token'];
    final accessToken = oauthCredentials['access_token'];
    
    debugPrint('Signing in with $provider OAuth credentials');
    
    if (provider == 'google') {
      final credential = GoogleAuthProvider.credential(
        idToken: idToken,
        accessToken: accessToken,
      );
      return await FirebaseAuth.instance.signInWithCredential(credential);
    } else if (provider == 'apple') {
      final credential = OAuthProvider('apple.com').credential(
        idToken: idToken,
        accessToken: accessToken,
      );
      return await FirebaseAuth.instance.signInWithCredential(credential);
    } else {
      throw Exception('Unsupported provider: $provider');
    }
  }

  Future<void> _updateUserPreferences(UserCredential result, String provider) async {
    try {
      final user = result.user;
      if (user == null) return;

      // Update UID and basic user info
      SharedPreferencesUtil().uid = user.uid;
      
      // Get user info from Firebase user and additional user info
      var email = user.email ?? '';
      var displayName = user.displayName ?? '';
      var givenName = '';
      var familyName = '';

      if (result.additionalUserInfo?.profile != null) {
        final profile = result.additionalUserInfo!.profile!;
        
        if (provider == 'google') {
          givenName = profile['given_name'] ?? '';
          familyName = profile['family_name'] ?? '';
          email = profile['email'] ?? email;
        } else if (provider == 'apple') {
          if (profile.containsKey('name')) {
            final name = profile['name'];
            if (name is Map) {
              givenName = name['firstName'] ?? '';
              familyName = name['lastName'] ?? '';
            }
          }
          email = profile['email'] ?? email;
        }
      }

      if (givenName.isEmpty && displayName.isNotEmpty) {
        var nameParts = displayName.split(' ');
        givenName = nameParts.isNotEmpty ? nameParts[0] : '';
        familyName = nameParts.length > 1 ? nameParts.sublist(1).join(' ') : '';
      }

      // Update SharedPreferences
      if (email.isNotEmpty) {
        SharedPreferencesUtil().email = email;
      }
      if (givenName.isNotEmpty) {
        SharedPreferencesUtil().givenName = givenName;
        SharedPreferencesUtil().familyName = familyName;
      }

      // Update Firebase user profile if needed
      if (displayName.isEmpty && givenName.isNotEmpty) {
        final fullName = familyName.isNotEmpty ? '$givenName $familyName' : givenName;
        try {
          await user.updateProfile(displayName: fullName);
          await user.reload();
        } catch (e) {
          debugPrint('Failed to update Firebase profile: $e');
        }
      }

      debugPrint('Updated user preferences:');
      debugPrint('Email: ${SharedPreferencesUtil().email}');
      debugPrint('Given Name: ${SharedPreferencesUtil().givenName}');
      debugPrint('Family Name: ${SharedPreferencesUtil().familyName}');
      debugPrint('UID: ${SharedPreferencesUtil().uid}');
      
    } catch (e) {
      debugPrint('Error updating user preferences: $e');
    }
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

  String _generateState() {
    final random = Random.secure();
    final bytes = Uint8List(32);
    for (int i = 0; i < 32; i++) {
      bytes[i] = random.nextInt(256);
    }
    return base64Url.encode(bytes);
  }

  Future<UserCredential?> linkWithProvider(String provider) async {
    try {
      final currentUser = FirebaseAuth.instance.currentUser;
      if (currentUser == null) {
        throw Exception('No user is currently signed in');
      }

      final state = _generateState();
      const redirectUri = 'omi://auth/callback';
      
      debugPrint('Starting OAuth linking flow for provider: $provider');
      
      final authUrl = '${Env.apiBaseUrl}v1/auth/authorize'
          '?provider=$provider'
          '&redirect_uri=${Uri.encodeComponent(redirectUri)}'
          '&state=$state';
      
      debugPrint('Authorization URL: $authUrl');
      
      final result = await FlutterWebAuth2.authenticate(
        url: authUrl,
        callbackUrlScheme: 'omi',
        options: const FlutterWebAuth2Options(
          intentFlags: ephemeralIntentFlags,
        ),
      );
      
      debugPrint('Authentication result: $result');
      
      final uri = Uri.parse(result);
      final code = uri.queryParameters['code'];
      final returnedState = uri.queryParameters['state'];
      
      if (code == null) {
        throw Exception('No authorization code received');
      }
      
      if (returnedState != state) {
        throw Exception('Invalid state parameter');
      }
      
      // Exchange the code for OAuth credentials
      final oauthCredentials = await _exchangeCodeForOAuthCredentials(code, redirectUri);
      
      if (oauthCredentials == null) {
        throw Exception('Failed to exchange code for OAuth credentials');
      }
      
      // Create Firebase credential
      final credential = await _createFirebaseCredential(oauthCredentials);
      
      try {
        // Link the credential to the current user
        final result = await currentUser.linkWithCredential(credential);
        
        // Update user preferences after successful linking
        await _updateUserPreferences(result, provider);
        
        debugPrint('Firebase account linking successful');
        return result;
      } catch (e) {
        if (e is FirebaseAuthException && e.code == 'credential-already-in-use') {
          // Handle existing credential case
          return await _handleExistingCredential(e);
        }
        rethrow;
      }
      
    } catch (e) {
      debugPrint('OAuth linking error: $e');
      Logger.handle(e, StackTrace.current, message: 'Account linking failed');
      rethrow;
    }
  }

  Future<AuthCredential> _createFirebaseCredential(Map<String, dynamic> oauthCredentials) async {
    final provider = oauthCredentials['provider'];
    final idToken = oauthCredentials['id_token'];
    final accessToken = oauthCredentials['access_token'];
    
    if (provider == 'google') {
      return GoogleAuthProvider.credential(
        idToken: idToken,
        accessToken: accessToken,
      );
    } else if (provider == 'apple') {
      return OAuthProvider('apple.com').credential(
        idToken: idToken,
        accessToken: accessToken,
      );
    } else {
      throw Exception('Unsupported provider: $provider');
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

  Future<UserCredential?> linkWithGoogle() async {
    return await linkWithProvider('google');
  }

  Future<UserCredential?> linkWithApple() async {
    return await linkWithProvider('apple');
  }
} 