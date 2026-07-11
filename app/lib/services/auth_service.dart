import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:app_links/app_links.dart';
import 'package:crypto/crypto.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

final class _FirebaseAuthTokenGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return null;
    return AuthUserSnapshot(uid: user.uid, email: user.email, displayName: user.displayName);
  }

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    final result = await FirebaseAuth.instance.currentUser?.getIdTokenResult(true);
    if (result == null) return null;
    return RefreshedAuthToken(token: result.token, expirationTime: result.expirationTime);
  }

  @override
  Future<void> signOut() => FirebaseAuth.instance.signOut();
}

class AuthService {
  static final AuthService _instance = AuthService._internal();
  static AuthService get instance => _instance;

  AuthService._internal()
      : _tokenGateway = _FirebaseAuthTokenGateway(),
        _refreshDelay = _defaultRefreshDelay,
        _recordTelemetry = _recordProductionTelemetry,
        _telemetryContextProvider = _productionTelemetryContext;

  @visibleForTesting
  AuthService.forTesting({
    required AuthTokenGateway tokenGateway,
    AuthRefreshDelay? refreshDelay,
    AuthTelemetryRecorder? recordTelemetry,
    AuthTelemetryContextProvider? telemetryContextProvider,
  })  : _tokenGateway = tokenGateway,
        _refreshDelay = refreshDelay ?? _defaultRefreshDelay,
        _recordTelemetry = recordTelemetry ?? ((eventName, properties) {}),
        _telemetryContextProvider = telemetryContextProvider ?? (() => const {});

  static const int _maxRefreshAttempts = 3;
  static const List<Duration> _refreshRetryDelays = [Duration(milliseconds: 200), Duration(milliseconds: 500)];
  static const Set<String> _terminalTokenErrorCodes = {
    'invalid-user-token',
    'user-disabled',
    'user-not-found',
    'user-token-expired',
  };

  static Future<void> _defaultRefreshDelay(Duration duration) => Future<void>.delayed(duration);

  final AuthTokenGateway _tokenGateway;
  final AuthRefreshDelay _refreshDelay;
  final AuthTelemetryRecorder _recordTelemetry;
  final AuthTelemetryContextProvider _telemetryContextProvider;
  final StreamController<AuthSessionExpiredEvent> _sessionExpiredController =
      StreamController<AuthSessionExpiredEvent>.broadcast(sync: true);
  Future<AuthTokenResult>? _refreshInFlight;
  Future<void>? _expireSessionInFlight;
  bool _sessionExpired = false;
  int _sessionGeneration = 0;
  String? _refreshUserUid;

  Stream<AuthSessionExpiredEvent> get sessionExpiredEvents => _sessionExpiredController.stream;

  static void _recordProductionTelemetry(String eventName, Map<String, dynamic> properties) {
    PlatformManager.instance.analytics.track(eventName, properties: properties);
  }

  static Map<String, dynamic> _productionTelemetryContext() => {
        'platform': PlatformManager.instance.platform,
        'app_version': PlatformManager.instance.appVersion,
        'release_channel': Env.isTestFlight ? 'testflight' : (F.env == Environment.prod ? 'app_store' : 'dev'),
      };

  bool isSignedIn() => FirebaseAuth.instance.currentUser != null && !FirebaseAuth.instance.currentUser!.isAnonymous;

  static const _pkceCodeVerifierLength = 64;
  static const _pkceCharset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';

  getFirebaseUser() {
    return FirebaseAuth.instance.currentUser;
  }

  /// Google Sign In using the standard google_sign_in package (iOS, Android)
  Future<UserCredential?> signInWithGoogleMobile() async {
    // Trigger the authentication flow
    final GoogleSignInAccount? googleUser = await GoogleSignIn(scopes: ['profile', 'email']).signIn();

    // Obtain the auth details from the request
    final GoogleSignInAuthentication? googleAuth = await googleUser?.authentication;
    if (googleAuth == null) {
      return null;
    }

    // Create a new credential
    if (googleAuth.accessToken == null && googleAuth.idToken == null) {
      return null;
    }
    final credential = GoogleAuthProvider.credential(accessToken: googleAuth.accessToken, idToken: googleAuth.idToken);

    // Once signed in, return the UserCredential
    final result = await FirebaseAuth.instance.signInWithCredential(credential);
    await _updateUserPreferences(result, 'google');
    return result;
  }

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

  Future<UserCredential?> signInWithAppleMobile() async {
    try {
      // Sign out the current user first
      Logger.debug('Signing out current user...');
      handleAuthUserChanged(null);
      await FirebaseAuth.instance.signOut();
      Logger.debug('User signed out successfully.');

      final rawNonce = generateNonce();
      final nonce = sha256ofString(rawNonce);

      Logger.debug('Requesting Apple credential...');
      final appleCredential = await SignInWithApple.getAppleIDCredential(
        scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
        nonce: nonce,
      );

      if (appleCredential.identityToken == null) {
        throw Exception('Apple Sign In failed - no identity token received.');
      }

      // Create an `OAuthCredential` from the credential returned by Apple.
      final oauthCredential = OAuthProvider("apple.com").credential(
        idToken: appleCredential.identityToken,
        rawNonce: rawNonce,
        accessToken: appleCredential.authorizationCode,
      );

      // Sign in the user with Firebase.
      Logger.debug('Attempting to sign in with Firebase...');
      UserCredential userCred = await FirebaseAuth.instance.signInWithCredential(oauthCredential);
      Logger.debug('Firebase sign-in successful.');

      // Extract name from Apple credential (only available on first sign-in)
      if (appleCredential.givenName != null && appleCredential.givenName!.isNotEmpty) {
        Logger.debug('Apple provided name: ${appleCredential.givenName} ${appleCredential.familyName ?? ""}');
        SharedPreferencesUtil().givenName = appleCredential.givenName!;
        if (appleCredential.familyName != null && appleCredential.familyName!.isNotEmpty) {
          SharedPreferencesUtil().familyName = appleCredential.familyName!;
        }

        // Update Firebase profile with the name
        final fullName = appleCredential.familyName != null && appleCredential.familyName!.isNotEmpty
            ? '${appleCredential.givenName} ${appleCredential.familyName}'
            : appleCredential.givenName!;
        try {
          await userCred.user?.updateProfile(displayName: fullName);
          await userCred.user?.reload();
        } catch (e) {
          Logger.debug('Failed to update Firebase profile with Apple name: $e');
        }
      }

      await _updateUserPreferences(userCred, 'apple');

      return userCred;
    } on FirebaseAuthException catch (e) {
      Logger.debug('FirebaseAuthException: ${e.code} - ${e.message}');
      if (e.code == 'invalid-credential') {
        Logger.debug('Please check Firebase console configuration for Apple Sign In.');
      }
      return null;
    } catch (e) {
      Logger.debug('Error during Apple Sign In: $e');
      Logger.handle(e, null, message: 'An error occurred while signing in. Please try again later.');
      return null;
    }
  }

  Future<void> signOut() async {
    _invalidateRefreshes();
    _clearCachedIdentityAndAuth();
    await _tokenGateway.signOut();
  }

  void _invalidateRefreshes() {
    _sessionGeneration++;
    _refreshInFlight = null;
  }

  void handleAuthUserChanged(String? uid) {
    if (_refreshUserUid == uid) return;
    _refreshUserUid = uid;
    _invalidateRefreshes();
  }

  void markAuthenticatedUser(String uid) {
    _refreshUserUid = uid;
    _sessionExpired = false;
    _invalidateRefreshes();
  }

  void _clearCachedAuth() {
    SharedPreferencesUtil().authToken = '';
    SharedPreferencesUtil().tokenExpirationTime = 0;
  }

  void _clearCachedIdentityAndAuth() {
    SharedPreferencesUtil().clearUserDisplayCache();
  }

  /// Compatibility for sign-in/onboarding callers that only need the token.
  /// Authenticated HTTP must use [refreshIdToken] so failure classes are kept.
  Future<String?> getIdToken() async {
    final result = await refreshIdToken();
    switch (result) {
      case AuthTokenSuccess(:final token):
        return token;
      case AuthTokenMissingToken():
        await expireSession(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken));
        break;
      case AuthTokenTerminalFailure(:final code):
        await expireSession(
          AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.terminalTokenFailure, code: code),
        );
        break;
      case AuthTokenMissingUser():
        break;
      case AuthTokenTransientFailure():
        break;
    }
    return null;
  }

  Future<AuthTokenResult> refreshIdToken() {
    if (_sessionExpired) {
      return Future<AuthTokenResult>.value(const AuthTokenMissingUser());
    }
    final currentUid = _tokenGateway.currentUser?.uid;
    if (_refreshUserUid != currentUid) {
      _refreshUserUid = currentUid;
      _invalidateRefreshes();
    }
    final inFlight = _refreshInFlight;
    if (inFlight != null) return inFlight;

    final generation = _sessionGeneration;
    final refresh = _refreshIdTokenWithRetries(generation, currentUid);
    _refreshInFlight = refresh;
    unawaited(
      refresh.then<void>(
        (result) {
          if (identical(_refreshInFlight, refresh)) _refreshInFlight = null;
        },
        onError: (Object error, StackTrace stackTrace) {
          if (identical(_refreshInFlight, refresh)) _refreshInFlight = null;
        },
      ),
    );
    return refresh;
  }

  Future<AuthTokenResult> _refreshIdTokenWithRetries(int generation, String? expectedUid) async {
    if (generation != _sessionGeneration) return const AuthTokenMissingUser();
    if (expectedUid == null || _tokenGateway.currentUser?.uid != expectedUid) {
      Logger.debug('refreshIdToken: currentUser is null');
      _clearCachedAuth();
      return const AuthTokenMissingUser();
    }

    AuthTokenResult? lastRetryableFailure;
    for (var attempt = 0; attempt < _maxRefreshAttempts; attempt++) {
      if (generation != _sessionGeneration) return const AuthTokenMissingUser();
      final result = await _refreshIdTokenOnce(generation, expectedUid);
      if (result is! AuthTokenTransientFailure && result is! AuthTokenMissingToken) {
        if (result is AuthTokenTerminalFailure) {
          _recordRefreshFailure(failureClass: 'terminal', code: result.code);
        }
        return result;
      }
      lastRetryableFailure = result;
      if (attempt < _refreshRetryDelays.length) {
        await _refreshDelay(_refreshRetryDelays[attempt]);
      }
    }
    if (lastRetryableFailure is AuthTokenTransientFailure) {
      _recordRefreshFailure(failureClass: lastRetryableFailure.failureClass, code: lastRetryableFailure.code);
    } else if (lastRetryableFailure is AuthTokenMissingToken) {
      _recordRefreshFailure(failureClass: 'missing_token');
    }
    return lastRetryableFailure!;
  }

  Future<AuthTokenResult> _refreshIdTokenOnce(int generation, String expectedUid) async {
    try {
      final refreshed = await _tokenGateway.forceRefresh();
      if (generation != _sessionGeneration || _tokenGateway.currentUser?.uid != expectedUid) {
        return const AuthTokenMissingUser();
      }
      final token = refreshed?.token;
      if (token == null || token.isEmpty) {
        Logger.debug('refreshIdToken: token refresh returned no token');
        return const AuthTokenMissingToken();
      }

      final user = _tokenGateway.currentUser;
      if (user == null || user.uid != expectedUid) {
        _clearCachedAuth();
        return const AuthTokenMissingUser();
      }

      SharedPreferencesUtil().uid = user.uid;
      SharedPreferencesUtil().tokenExpirationTime = refreshed?.expirationTime?.millisecondsSinceEpoch ?? 0;
      SharedPreferencesUtil().authToken = token;
      if (SharedPreferencesUtil().email.isEmpty) {
        SharedPreferencesUtil().email = user.email ?? '';
      }
      if (SharedPreferencesUtil().givenName.isEmpty) {
        final nameParts = user.displayName?.split(' ') ?? const <String>[];
        SharedPreferencesUtil().givenName = nameParts.isEmpty ? '' : nameParts.first;
        SharedPreferencesUtil().familyName = nameParts.length > 1 ? nameParts[1] : '';
      }
      _sessionExpired = false;
      return AuthTokenSuccess(token: token, expirationTime: refreshed?.expirationTime);
    } on FirebaseAuthException catch (e) {
      if (generation != _sessionGeneration) return const AuthTokenMissingUser();
      Logger.debug('refreshIdToken: FirebaseAuthException: ${e.code}');
      if (_terminalTokenErrorCodes.contains(e.code)) {
        _clearCachedAuth();
        return AuthTokenTerminalFailure(code: e.code);
      }
      return AuthTokenTransientFailure(failureClass: 'firebase_transient', code: e.code);
    } catch (e) {
      if (generation != _sessionGeneration) return const AuthTokenMissingUser();
      Logger.debug('refreshIdToken: token refresh failed transiently: ${e.runtimeType}');
      return const AuthTokenTransientFailure(failureClass: 'transient');
    }
  }

  void _recordRefreshFailure({required String failureClass, String? code}) {
    _recordTelemetry('auth_token_refresh_failed', {
      'failure_class': failureClass,
      'code': code ?? failureClass,
      ..._telemetryContextProvider(),
    });
  }

  void recordAuthenticatedRequest401({required bool recovered, required String outcome}) {
    _recordTelemetry('authenticated_request_401', {
      'recovered': recovered,
      'outcome': outcome,
      ..._telemetryContextProvider(),
    });
  }

  Future<void> expireSession(AuthSessionExpiredEvent event) {
    final inFlight = _expireSessionInFlight;
    if (_sessionExpired) return inFlight ?? Future<void>.value();

    _sessionExpired = true;
    _invalidateRefreshes();
    _clearCachedIdentityAndAuth();
    _sessionExpiredController.add(event);
    final expiration = _runSessionExpiration();
    _expireSessionInFlight = expiration;
    return expiration;
  }

  Future<void> _runSessionExpiration() async {
    try {
      await _tokenGateway.signOut();
    } catch (e) {
      // Local session state is already terminal and cleared. A platform sign-
      // out failure must not escape back into request handling or restore the
      // stale authenticated shell.
      Logger.debug('expireSession: Firebase sign-out failed: ${e.runtimeType}');
    } finally {
      _expireSessionInFlight = null;
    }
  }

  // Method channel for direct deep link delivery (fallback for app_links)
  static const _deepLinkChannel = MethodChannel('com.omi/deep_links');

  Future<UserCredential?> authenticateWithProvider(String provider) async {
    try {
      final state = _generateState();
      final codeVerifier = _generateCodeVerifier();
      final codeChallenge = _codeChallengeForVerifier(codeVerifier);
      const redirectUri = 'omi://auth/callback';

      Logger.debug('Starting OAuth flow for provider: $provider');

      final authUrl = Uri.parse('${Env.apiBaseUrl}v1/auth/authorize').replace(
        queryParameters: {
          'provider': provider,
          'redirect_uri': redirectUri,
          'state': state,
          'code_challenge': codeChallenge,
          'code_challenge_method': 'S256',
        },
      ).toString();

      Logger.debug('Authorization URL: $authUrl');

      // Set up listeners before launching URL
      final appLinks = AppLinks();
      late StreamSubscription linkSubscription;
      final completer = Completer<String>();

      // Listen via app_links
      linkSubscription = appLinks.uriLinkStream.listen(
        (Uri uri) {
          Logger.debug('Received callback URI via app_links: $uri');
          if (uri.scheme == 'omi' && uri.host == 'auth' && uri.path == '/callback') {
            if (!completer.isCompleted) {
              linkSubscription.cancel();
              completer.complete(uri.toString());
            }
          }
        },
        onError: (error) {
          Logger.debug('App link error: $error');
          if (!completer.isCompleted) {
            linkSubscription.cancel();
            completer.completeError(error);
          }
        },
      );

      // Also listen via direct method channel (fallback)
      _deepLinkChannel.setMethodCallHandler((call) async {
        if (call.method == 'onDeepLink') {
          final urlString = call.arguments as String;
          Logger.debug('Received callback URI via method channel: $urlString');
          final uri = Uri.parse(urlString);
          if (uri.scheme == 'omi' && uri.host == 'auth' && uri.path == '/callback') {
            if (!completer.isCompleted) {
              linkSubscription.cancel();
              _deepLinkChannel.setMethodCallHandler(null);
              completer.complete(urlString);
            }
          }
        }
      });

      // Now launch the URL
      final launched = await launchUrl(Uri.parse(authUrl), mode: LaunchMode.inAppBrowserView);

      if (!launched) {
        linkSubscription.cancel();
        _deepLinkChannel.setMethodCallHandler(null);
        throw Exception('Failed to launch authentication URL');
      }

      final result = await completer.future.timeout(
        const Duration(minutes: 5),
        onTimeout: () {
          linkSubscription.cancel();
          _deepLinkChannel.setMethodCallHandler(null);
          throw Exception('Authentication timeout');
        },
      );

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
      final oauthCredentials = await _exchangeCodeForOAuthCredentials(code, redirectUri, codeVerifier);

      if (oauthCredentials == null) {
        throw Exception('Failed to exchange code for OAuth credentials');
      }

      // Sign in to Firebase with the OAuth credentials
      final credential = await _signInWithOAuthCredentials(oauthCredentials);

      // Update user profile and local storage after successful sign-in
      await _updateUserPreferences(credential, provider);

      Logger.debug('Firebase authentication successful');
      return credential;
    } catch (e) {
      Logger.debug('OAuth authentication error: $e');
      Logger.handle(e, StackTrace.current, message: 'Authentication failed');
      return null;
    }
  }

  Future<Map<String, dynamic>?> _exchangeCodeForOAuthCredentials(
    String code,
    String redirectUri,
    String codeVerifier,
  ) async {
    try {
      final useCustomToken = Env.useAuthCustomToken;

      final response = await http.post(
        Uri.parse('${Env.apiBaseUrl}v1/auth/token'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'grant_type': 'authorization_code',
          'code': code,
          'redirect_uri': redirectUri,
          'use_custom_token': useCustomToken.toString(),
          'code_verifier': codeVerifier,
        },
      );

      Logger.debug('Token exchange response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        Logger.debug('Token exchange succeeded');
        return json.decode(response.body);
      } else {
        Logger.debug('Token exchange failed: ${response.body}');
        return null;
      }
    } catch (e) {
      Logger.debug('Token exchange error: $e');
      return null;
    }
  }

  Future<UserCredential> _signInWithOAuthCredentials(Map<String, dynamic> oauthCredentials) async {
    final provider = oauthCredentials['provider'];
    final useCustomToken = Env.useAuthCustomToken;
    final customToken = oauthCredentials['custom_token'];

    // Use custom token if enabled and available
    if (useCustomToken && customToken != null) {
      Logger.debug('Signing in with Firebase custom token from $provider');
      return await FirebaseAuth.instance.signInWithCustomToken(customToken);
    }

    // Fallback to OAuth credentials
    final idToken = oauthCredentials['id_token'];
    final accessToken = oauthCredentials['access_token'];

    Logger.debug('Signing in with $provider OAuth credentials');

    if (provider == 'google') {
      final credential = GoogleAuthProvider.credential(idToken: idToken, accessToken: accessToken);
      return await FirebaseAuth.instance.signInWithCredential(credential);
    } else if (provider == 'apple') {
      final credential = OAuthProvider('apple.com').credential(idToken: idToken, accessToken: accessToken);
      return await FirebaseAuth.instance.signInWithCredential(credential);
    } else {
      throw Exception('Unsupported provider: $provider');
    }
  }

  Future<void> _updateUserPreferences(UserCredential result, String provider) async {
    try {
      final user = result.user;
      if (user == null) return;
      markAuthenticatedUser(user.uid);

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
          Logger.debug('Failed to update Firebase profile: $e');
        }
      }

      Logger.debug('Updated user preferences:');
      Logger.debug('Email: ${SharedPreferencesUtil().email}');
      Logger.debug('Given Name: ${SharedPreferencesUtil().givenName}');
      Logger.debug('Family Name: ${SharedPreferencesUtil().familyName}');
      Logger.debug('UID: ${SharedPreferencesUtil().uid}');

      // Restore onboarding state from server
      await _restoreOnboardingState();
    } catch (e) {
      Logger.debug('Error updating user preferences: $e');
    }
  }

  /// Restore onboarding state from server. Call this on app startup when using cached credentials.
  Future<void> restoreOnboardingState() async {
    return _restoreOnboardingState();
  }

  Future<void> _restoreOnboardingState() async {
    try {
      final state = await getUserOnboardingState();
      if (state != null) {
        if (state['completed'] == true) {
          SharedPreferencesUtil().onboardingCompleted = true;
        }
        final acquisitionSource = state['acquisition_source'] as String? ?? '';
        if (acquisitionSource.isNotEmpty) {
          SharedPreferencesUtil().foundOmiSource = acquisitionSource;
        }
        // Restore language from server if not already set locally
        final serverLanguage = await getUserPrimaryLanguage();
        if (serverLanguage != null && serverLanguage.isNotEmpty) {
          SharedPreferencesUtil().userPrimaryLanguage = serverLanguage;
          SharedPreferencesUtil().hasSetPrimaryLanguage = true;
        }
      }
    } catch (e) {
      Logger.debug('restoreOnboardingState failed: $e');
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
        Logger.debug('Firebase user is null, skipping Firebase profile update');
        return;
      }

      // Try to update Firebase profile with platform-specific handling
      try {
        Logger.debug('Attempting to update Firebase user profile...');

        if (kIsWeb) {
          Logger.debug('Web platform detected - attempting updateProfile with caution');

          // Try with a timeout to prevent hanging
          await user.updateProfile(displayName: fullName).timeout(
            const Duration(seconds: 5),
            onTimeout: () {
              Logger.debug('updateProfile timed out on web platform');
              throw TimeoutException('updateProfile timed out', const Duration(seconds: 5));
            },
          );
        } else {
          await user.updateProfile(displayName: fullName);
        }
        await user.reload();
        user = FirebaseAuth.instance.currentUser;
      } catch (updateError) {
        Logger.debug('Firebase updateProfile failed: $updateError');
      }
    } catch (e) {
      Logger.debug('Error in updateGivenName: $e');

      // Ensure SharedPreferences are updated even if everything else fails
      try {
        SharedPreferencesUtil().givenName = fullName.split(' ')[0];
        if (fullName.split(' ').length > 1) {
          SharedPreferencesUtil().familyName = fullName.split(' ').sublist(1).join(' ');
        }
        Logger.debug('SharedPreferences updated despite error');
      } catch (prefError) {
        Logger.debug('Failed to update SharedPreferences: $prefError');
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

  String _generateCodeVerifier([int length = _pkceCodeVerifierLength]) {
    final random = Random.secure();
    return List.generate(length, (_) => _pkceCharset[random.nextInt(_pkceCharset.length)]).join();
  }

  String _codeChallengeForVerifier(String verifier) {
    final digest = sha256.convert(utf8.encode(verifier));
    return base64Url.encode(digest.bytes).replaceAll('=', '');
  }

  Future<UserCredential?> linkWithProvider(String provider) async {
    try {
      final currentUser = FirebaseAuth.instance.currentUser;
      if (currentUser == null) {
        throw Exception('No user is currently signed in');
      }

      final state = _generateState();
      final codeVerifier = _generateCodeVerifier();
      final codeChallenge = _codeChallengeForVerifier(codeVerifier);
      const redirectUri = 'omi://auth/callback';

      Logger.debug('Starting OAuth linking flow for provider: $provider');

      final authUrl = Uri.parse('${Env.apiBaseUrl}v1/auth/authorize').replace(
        queryParameters: {
          'provider': provider,
          'redirect_uri': redirectUri,
          'state': state,
          'code_challenge': codeChallenge,
          'code_challenge_method': 'S256',
        },
      ).toString();

      Logger.debug('Authorization URL: $authUrl');

      final launched = await launchUrl(Uri.parse(authUrl), mode: LaunchMode.inAppBrowserView);

      if (!launched) {
        throw Exception('Failed to launch authentication URL');
      }

      // Listen for the callback URL using app_links
      final appLinks = AppLinks();
      late StreamSubscription linkSubscription;
      final completer = Completer<String>();

      linkSubscription = appLinks.uriLinkStream.listen(
        (Uri uri) {
          Logger.debug('Received callback URI: $uri');
          if (uri.scheme == 'omi' && uri.host == 'auth' && uri.path == '/callback') {
            linkSubscription.cancel();
            completer.complete(uri.toString());
          }
        },
        onError: (error) {
          Logger.debug('App link error: $error');
          linkSubscription.cancel();
          completer.completeError(error);
        },
      );

      final result = await completer.future.timeout(
        const Duration(minutes: 5),
        onTimeout: () {
          linkSubscription.cancel();
          throw Exception('Authentication timeout');
        },
      );

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
      final oauthCredentials = await _exchangeCodeForOAuthCredentials(code, redirectUri, codeVerifier);

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

        Logger.debug('Firebase account linking successful');
        return result;
      } catch (e) {
        if (e is FirebaseAuthException && e.code == 'credential-already-in-use') {
          // Handle existing credential case
          return await _handleExistingCredential(e);
        }
        rethrow;
      }
    } catch (e) {
      Logger.debug('OAuth linking error: $e');
      Logger.handle(e, StackTrace.current, message: 'Account linking failed');
      rethrow;
    }
  }

  Future<AuthCredential> _createFirebaseCredential(Map<String, dynamic> oauthCredentials) async {
    final provider = oauthCredentials['provider'];
    final idToken = oauthCredentials['id_token'];
    final accessToken = oauthCredentials['access_token'];

    if (provider == 'google') {
      return GoogleAuthProvider.credential(idToken: idToken, accessToken: accessToken);
    } else if (provider == 'apple') {
      return OAuthProvider('apple.com').credential(idToken: idToken, accessToken: accessToken);
    } else {
      throw Exception('Unsupported provider: $provider');
    }
  }

  /// Handle the case when credential is already in use
  Future<UserCredential?> _handleExistingCredential(FirebaseAuthException e) async {
    // Get existing user credentials
    final existingCred = e.credential;

    // Sign out current anonymous user
    handleAuthUserChanged(null);
    await FirebaseAuth.instance.signOut();

    // Sign in with existing account
    final result = await FirebaseAuth.instance.signInWithCredential(existingCred!);
    final newUserId = FirebaseAuth.instance.currentUser?.uid;
    if (newUserId != null) markAuthenticatedUser(newUserId);
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
