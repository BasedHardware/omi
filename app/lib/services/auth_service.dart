import 'package:omi/services/pending_work/pending_work_store.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:app_links/app_links.dart';
import 'package:crypto/crypto.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/services/onboarding_sync_runtime.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/utils/auth/sign_in_failure.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

final class _FirebaseAuthTokenGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return null;
    return AuthUserSnapshot(
      uid: user.uid,
      email: user.email,
      displayName: user.displayName,
      isAnonymous: user.isAnonymous,
    );
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

/// Source-bound proof captured before a credential-collision sign-in replaces
/// the anonymous Firebase user.
final class AnonymousSourceMigration {
  const AnonymousSourceMigration({required this.uid, required this.token});

  final String uid;
  final String token;
}

/// The outcome of linking an external provider.
///
/// An anonymous credential collision can establish the destination account.
/// Its source proof is captured before the switch and returned in [anonymousSourceMigration].
final class ProviderLinkResult {
  const ProviderLinkResult({required this.destinationUid, this.destinationSession, this.anonymousSourceMigration});

  final String? destinationUid;
  final AuthSessionSnapshot? destinationSession;
  final AnonymousSourceMigration? anonymousSourceMigration;
}

/// The selected provider identity already belongs to a separate account.
final class ProviderLinkConflict implements Exception {
  const ProviderLinkConflict();
}

/// A pending provider authorization can be retired until Firebase receives the link.
final class ProviderLinkAuthorization extends ChangeNotifier {
  final _cancelled = Completer<void>();
  bool _dispatched = false;

  bool get _isCancelled => _cancelled.isCompleted;
  bool get canCancel => !_dispatched && !_isCancelled;

  void cancel() {
    if (!canCancel) return;
    _cancelled.complete();
    notifyListeners();
  }

  Future<T?> _untilCancelled<T>(Future<T?> pending) => Future.any([pending, _cancelled.future.then<T?>((_) => null)]);

  bool _dispatch() {
    if (!canCancel) return false;
    _dispatched = true;
    notifyListeners();
    return true;
  }
}

/// Captures an anonymous source proof before [establishDestination] can replace
/// FirebaseAuth.currentUser, then returns both sides of the completed collision.
@visibleForTesting
Future<ProviderLinkResult> resolveProviderCredentialCollision({
  required String sourceUid,
  required bool sourceIsAnonymous,
  required Future<String?> Function() captureSourceToken,
  required Future<String?> Function() establishDestination,
}) async {
  final sourceToken = sourceIsAnonymous ? await captureSourceToken() : null;
  final anonymousSourceMigration =
      sourceToken == null ? null : AnonymousSourceMigration(uid: sourceUid, token: sourceToken);
  final destinationUid = await establishDestination();
  return ProviderLinkResult(destinationUid: destinationUid, anonymousSourceMigration: anonymousSourceMigration);
}

class AuthService {
  static final AuthService _instance = AuthService._internal();
  static AuthService get instance => _instance;

  AuthService._internal()
      : _tokenGateway = _FirebaseAuthTokenGateway(),
        _refreshAttemptTimeout = _defaultRefreshAttemptTimeout,
        _refreshDelay = _defaultRefreshDelay,
        _recordTelemetry = _recordProductionTelemetry,
        _telemetryContextProvider = _productionTelemetryContext,
        _prepareSiriSignOut = SiriIntegration.current.prepareForSignOut,
        _siriPreparationTimeout = const Duration(seconds: 2),
        _firebaseAuthOverride = null,
        _authorizeProviderLinkOverride = null;

  @visibleForTesting
  AuthService.forTesting({
    required AuthTokenGateway tokenGateway,
    AuthRefreshDelay? refreshDelay,
    Duration? refreshAttemptTimeout,
    AuthTelemetryRecorder? recordTelemetry,
    AuthTelemetryContextProvider? telemetryContextProvider,
    Future<void> Function()? prepareSiriSignOut,
    Duration siriPreparationTimeout = const Duration(seconds: 2),
    FirebaseAuth? firebaseAuth,
    Future<AuthCredential> Function(String provider)? authorizeProviderLink,
  })  : _tokenGateway = tokenGateway,
        _refreshAttemptTimeout = refreshAttemptTimeout ?? _defaultRefreshAttemptTimeout,
        _refreshDelay = refreshDelay ?? _defaultRefreshDelay,
        _recordTelemetry = recordTelemetry ?? ((eventName, properties) {}),
        _telemetryContextProvider = telemetryContextProvider ?? (() => const {}),
        _prepareSiriSignOut = prepareSiriSignOut ?? (() async {}),
        _siriPreparationTimeout = siriPreparationTimeout,
        _firebaseAuthOverride = firebaseAuth,
        _authorizeProviderLinkOverride = authorizeProviderLink;

  /// Replaces the production Firebase token gateway on the **singleton** for
  /// the local hermetic journey lane (SCA-488).
  ///
  /// The gateway is an external-I/O boundary — installing a synthetic one
  /// fakes Firebase token I/O, never a product decision: every caller
  /// (`getIdToken`, refresh retries, session expiry) keeps running its real
  /// logic against the gateway. The full-stack simulator lane does NOT use
  /// this: it signs in through real FirebaseAuth against the local Auth
  /// emulator. Debug-only and local_dev-profile-gated; assertions fail in
  /// production-family builds instead of installing.
  static void installLocalHarnessTokenGateway(AuthTokenGateway gateway) {
    assert(kDebugMode, 'local-harness token gateway is a debug-only seam');
    assert(Env.profile == AppEnvironmentProfile.localDev, 'local-harness token gateway requires the local_dev profile');
    _instance._tokenGateway = gateway;
  }

  static const int _maxRefreshAttempts = 3;

  /// Per-attempt ceiling on the Firebase forced token refresh.
  ///
  /// `forceRefresh()` can hang indefinitely rather than fail: measured on
  /// iPhone 17 Pro / iOS 27.0 against a Firebase Auth emulator on a non-loopback
  /// host, it never returned at all. Because `shared.dart` refreshes on the way
  /// into *every* authenticated request, an unbounded stall here silently freezes
  /// all backend traffic app-wide — no error, no timeout, nothing to report.
  ///
  /// A timed-out attempt is reported as a transient failure, which the retry loop
  /// below and every existing caller already handle.
  static const Duration _defaultRefreshAttemptTimeout = Duration(seconds: 8);
  static const List<Duration> _refreshRetryDelays = [Duration(milliseconds: 200), Duration(milliseconds: 500)];
  static const Set<String> _terminalTokenErrorCodes = {
    'invalid-user-token',
    'user-disabled',
    'user-not-found',
    'user-token-expired',
  };

  static Future<void> _defaultRefreshDelay(Duration duration) => Future<void>.delayed(duration);

  // Non-final solely for the debug-gated local-harness seam above; every
  // production construction still assigns exactly once in the constructor.
  AuthTokenGateway _tokenGateway;
  final Duration _refreshAttemptTimeout;
  final AuthRefreshDelay _refreshDelay;
  final AuthTelemetryRecorder _recordTelemetry;
  final AuthTelemetryContextProvider _telemetryContextProvider;
  final Future<void> Function() _prepareSiriSignOut;
  final Duration _siriPreparationTimeout;
  final FirebaseAuth? _firebaseAuthOverride;
  final Future<AuthCredential> Function(String provider)? _authorizeProviderLinkOverride;
  FirebaseAuth get _firebaseAuth => _firebaseAuthOverride ?? FirebaseAuth.instance;

  Future<void> _prepareSiriBestEffort() async {
    try {
      await _prepareSiriSignOut().timeout(_siriPreparationTimeout);
    } catch (error) {
      // The auth boundary must complete even when the optional native bridge
      // is unavailable. A successfully persisted marker remains for launch
      // maintenance; the auth-state callback still attempts the wipe.
      Logger.debug('Siri sign-out preparation deferred: ${error.runtimeType}');
    }
  }

  final StreamController<AuthSessionExpiredEvent> _sessionExpiredController =
      StreamController<AuthSessionExpiredEvent>.broadcast(sync: true);
  final StreamController<int> _sessionGenerationController = StreamController<int>.broadcast(sync: true);
  Future<AuthTokenResult>? _refreshInFlight;
  Future<void>? _expireSessionInFlight;
  Object? _expirationOwner;
  bool _sessionExpired = false;
  int _sessionGeneration = 0;
  String? _refreshUserUid;

  Stream<AuthSessionExpiredEvent> get sessionExpiredEvents => _sessionExpiredController.stream;

  Stream<int> get sessionGenerationEvents => _sessionGenerationController.stream;

  AuthSessionSnapshot? captureSessionSnapshot({String? expectedUid}) {
    handleAuthUserChanged(_tokenGateway.currentUser?.uid);
    final user = _tokenGateway.currentUser;
    if (_sessionExpired || user == null || user.isAnonymous) return null;
    if (expectedUid != null && user.uid != expectedUid) return null;
    return AuthSessionSnapshot(ownerUid: user.uid, generation: _sessionGeneration);
  }

  bool isSessionSnapshotCurrent(AuthSessionSnapshot snapshot) {
    final user = _tokenGateway.currentUser;
    return !_sessionExpired &&
        user != null &&
        !user.isAnonymous &&
        user.uid == snapshot.ownerUid &&
        _sessionGeneration == snapshot.generation;
  }

  static void _recordProductionTelemetry(String eventName, Map<String, dynamic> properties) {
    PlatformManager.instance.analytics.track(eventName, properties: properties);
  }

  static Map<String, dynamic> _productionTelemetryContext() => {
        'platform': PlatformManager.instance.platform,
        'app_version': PlatformManager.instance.appVersion,
        'release_channel': Env.isTestFlight ? 'testflight' : (F.env == Environment.prod ? 'app_store' : 'dev'),
      };

  /// Routes through the token gateway so the declared Firebase I/O seam
  /// covers identity reads too: the production gateway still answers from
  /// FirebaseAuth; the local hermetic harness answers from its synthetic
  /// principal. No behavior change for real builds.
  bool isSignedIn() {
    final user = _tokenGateway.currentUser;
    return user != null && !user.isAnonymous;
  }

  static const _pkceCodeVerifierLength = 64;
  static const _pkceCharset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';

  getFirebaseUser() {
    return _firebaseAuth.currentUser;
  }

  Future<AuthCredential?> _requestGoogleMobileCredential() async {
    final googleUser = await GoogleSignIn(scopes: ['profile', 'email']).signIn();
    final googleAuth = await googleUser?.authentication;
    if (googleAuth == null || (googleAuth.accessToken == null && googleAuth.idToken == null)) return null;
    return GoogleAuthProvider.credential(accessToken: googleAuth.accessToken, idToken: googleAuth.idToken);
  }

  /// Google Sign In using the standard google_sign_in package (iOS, Android).
  Future<UserCredential?> signInWithGoogleMobile() async {
    final credential = await _requestGoogleMobileCredential();
    if (credential == null) return null;
    final result = await runAccountMutation(() => _firebaseAuth.signInWithCredential(credential));
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

  Future<({AuthCredential credential, AuthorizationCredentialAppleID apple})> _requestAppleMobileCredential() async {
    final rawNonce = generateNonce();
    final nonce = sha256ofString(rawNonce);

    Logger.debug('Requesting Apple credential...');
    final appleCredential = await SignInWithApple.getAppleIDCredential(
      scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
      nonce: nonce,
    );

    if (appleCredential.identityToken == null) {
      throw const AppleIdentityTokenMissing();
    }

    final credential = OAuthProvider("apple.com").credential(
      idToken: appleCredential.identityToken,
      rawNonce: rawNonce,
      accessToken: appleCredential.authorizationCode,
    );
    return (credential: credential, apple: appleCredential);
  }

  /// Throws the Apple or Firebase error unchanged so the caller can tell a
  /// cancel from a real failure and report its code.
  Future<UserCredential> signInWithAppleMobile() async {
    // Sign out the current user first.
    await signOutForAccountSwitch();
    final (credential: credential, apple: appleCredential) = await _requestAppleMobileCredential();

    // Sign in the user with Firebase.
    Logger.debug('Attempting to sign in with Firebase...');
    UserCredential userCred = await runAccountMutation(() => _firebaseAuth.signInWithCredential(credential));
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
  }

  Future<void> _accountMutationTail = Future<void>.value();

  /// Firebase sign-out acts on the global session, including while its Future
  /// is pending. Every sign-in must wait until that mutation has completed.
  Future<T> runAccountMutation<T>(Future<T> Function() mutation) {
    final pending = _accountMutationTail.then((_) => mutation());
    _accountMutationTail = pending.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return pending;
  }

  Future<void> signOut() => runAccountMutation(() async {
        await _prepareSiriBestEffort();
        _invalidateRefreshes();
        _clearCachedIdentityAndAuth();
        await _tokenGateway.signOut();
      });

  /// Credential collision and provider switching preserve their existing
  /// non-Siri cache behavior, while fencing native Siri before Firebase exits.
  Future<void> signOutForAccountSwitch() => runAccountMutation(() async {
        await _prepareSiriBestEffort();
        handleAuthUserChanged(null);
        await _tokenGateway.signOut();
      });

  void _invalidateRefreshes() {
    PendingWorkStore.instance.reset();
    _sessionGeneration++;
    _refreshInFlight = null;
    _sessionGenerationController.add(_sessionGeneration);
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
        _scheduleLocalDevRecovery();
        break;
    }
    return null;
  }

  bool _localDevRecoveryInFlight = false;

  /// Recover a local-development session by minting a new token instead of
  /// refreshing the old one.
  ///
  /// Local dev has an escape hatch production does not: the harness mints a fresh
  /// custom token on demand, so a session can be *replaced* rather than
  /// refreshed. That matters because `getIdTokenResult(true)` is not reliable
  /// against the Auth emulator — measured on iPhone 17 Pro / iOS 27.0 the forced
  /// refresh never returned, while `signInWithCustomToken` against the same
  /// emulator succeeded every time.
  ///
  /// Scheduled rather than awaited, and deliberately off the current call stack.
  /// An earlier version awaited it inline from [getIdToken] and **deadlocked on
  /// device**: the recovery re-enters sign-in from inside the refresh call stack,
  /// and the probe showed it entering `signInWithLocalDevToken()` and never
  /// returning — no HTTP request ever left the app — while the identical call
  /// from the sign-in button succeeds. The caller therefore gets its failure
  /// immediately, and the *next* request picks up the re-minted session.
  ///
  /// Deliberately narrow: `local_dev` only, only after a transient refresh
  /// failure, and re-entrancy guarded. Production is untouched — a failed refresh
  /// must stay a failed refresh there, because silently re-authenticating would
  /// hide exactly the signal an expired or revoked session is meant to give.
  void _scheduleLocalDevRecovery() {
    if (Env.profile != AppEnvironmentProfile.localDev) return;
    if (_localDevRecoveryInFlight) return;
    _localDevRecoveryInFlight = true;

    unawaited(
      Future<void>.delayed(Duration.zero, () async {
        try {
          Logger.debug('local-dev: refresh failed, re-minting a session out of band');
          final credential = await signInWithLocalDevToken();
          final user = credential?.user;
          if (user == null) return;
          // Unforced: sign-in just populated a fresh token, so read the cached one
          // rather than re-entering the forced-refresh path that just failed.
          final token = await user.getIdToken();
          if (token == null || token.isEmpty) return;
          SharedPreferencesUtil().authToken = token;
          _sessionExpired = false;
          markAuthenticatedUser(user.uid);
          Logger.debug('local-dev: session re-minted; the next request will use it');
        } catch (e) {
          Logger.debug('local-dev: re-mint failed: $e');
        } finally {
          _localDevRecoveryInFlight = false;
        }
      }),
    );
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
      final refreshed = await _tokenGateway.forceRefresh().timeout(_refreshAttemptTimeout);
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
    } on TimeoutException {
      if (generation != _sessionGeneration) return const AuthTokenMissingUser();
      Logger.debug('refreshIdToken: forceRefresh timed out after $_refreshAttemptTimeout');
      // Distinct class so a stalled refresh is distinguishable in telemetry from
      // one that actually failed — they have very different causes.
      return const AuthTokenTransientFailure(failureClass: 'refresh_timeout');
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

    final ownerUid = _tokenGateway.currentUser?.uid;
    final owner = Object();
    _expirationOwner = owner;
    _sessionExpired = true;
    _invalidateRefreshes();
    final generation = _sessionGeneration;
    _clearCachedIdentityAndAuth();
    _sessionExpiredController.add(event);
    final expiration = _runSessionExpiration(ownerUid, generation, owner);
    _expireSessionInFlight = expiration;
    return expiration;
  }

  Future<void> _runSessionExpiration(String? ownerUid, int generation, Object owner) async {
    await _prepareSiriBestEffort();
    try {
      await runAccountMutation(() async {
        if (_sessionGeneration != generation ||
            _tokenGateway.currentUser?.uid != ownerUid ||
            !identical(_expirationOwner, owner)) return;
        await _tokenGateway.signOut();
      });
    } catch (e) {
      // Local session state is already terminal and cleared. A platform sign-
      // out failure must not escape back into request handling or restore the
      // stale authenticated shell.
      Logger.debug('expireSession: Firebase sign-out failed: ${e.runtimeType}');
    } finally {
      if (identical(_expirationOwner, owner)) {
        _expireSessionInFlight = null;
        _expirationOwner = null;
      }
    }
  }

  Future<UserCredential?> authenticateWithProvider(String provider) async {
    try {
      final oauthCredentials = await _requestOAuthCredentials(provider, useCustomToken: Env.useAuthCustomToken);
      if (oauthCredentials == null) return null;
      final credential = await _signInWithOAuthCredentials(oauthCredentials);
      await _updateUserPreferences(credential, provider);
      Logger.debug('Firebase authentication successful');
      return credential;
    } catch (e, stackTrace) {
      Logger.handle(e, stackTrace, message: 'Authentication failed');
      return null;
    }
  }

  Future<Map<String, dynamic>?> _requestOAuthCredentials(
    String provider, {
    required bool useCustomToken,
    bool selectAccount = false,
    ProviderLinkAuthorization? authorization,
  }) async {
    final state = _generateState();
    final codeVerifier = _generateCodeVerifier();
    final redirectUri = Env.authRedirectUri;
    final callbackScheme = Env.authCallbackScheme;
    final authUrl = Uri.parse('${Env.authApiBaseUrl}v1/auth/authorize').replace(queryParameters: {
      'provider': provider,
      'redirect_uri': redirectUri,
      'state': state,
      'code_challenge': _codeChallengeForVerifier(codeVerifier),
      'code_challenge_method': 'S256',
      if (selectAccount) 'select_account': 'true',
    });

    final callback = Completer<Uri>();
    // A platform stream error can arrive while the browser is still launching.
    callback.future.ignore();
    final subscription = AppLinks().uriLinkStream.listen(
      (uri) {
        if (!callback.isCompleted &&
            uri.scheme == callbackScheme &&
            uri.host == 'auth' &&
            uri.path == '/callback' &&
            uri.queryParameters['state'] == state) {
          callback.complete(uri);
        }
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!callback.isCompleted) callback.completeError(error, stackTrace);
      },
    );

    try {
      if (authorization?._isCancelled == true) return null;
      final launch = launchUrl(authUrl, mode: LaunchMode.inAppBrowserView);
      final launched = await (authorization?._untilCancelled(launch) ?? launch);
      if (launched == null) return null;
      if (!launched) throw StateError('Failed to launch authentication URL');
      final pendingCallback = authorization?._untilCancelled(callback.future) ?? callback.future;
      final uri = await pendingCallback.timeout(const Duration(minutes: 5));
      if (uri == null || authorization?._isCancelled == true) return null;
      final code = uri.queryParameters['code'];
      if (code == null) throw StateError('No authorization code received');
      final exchange = _exchangeCodeForOAuthCredentials(
        code,
        redirectUri,
        codeVerifier,
        useCustomToken: useCustomToken,
      );
      final credentials = await (authorization?._untilCancelled(exchange) ?? exchange);
      if (authorization?._isCancelled == true) return null;
      if (credentials == null || credentials['provider'] != provider) {
        throw StateError('Failed to exchange provider authorization code');
      }
      return credentials;
    } finally {
      await subscription.cancel();
    }
  }

  Future<Map<String, dynamic>?> _exchangeCodeForOAuthCredentials(
    String code,
    String redirectUri,
    String codeVerifier, {
    required bool useCustomToken,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('${Env.authApiBaseUrl}v1/auth/token'),
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
        Logger.debug('Token exchange failed: HTTP ${response.statusCode}');
        return null;
      }
    } catch (e) {
      Logger.debug('Token exchange error: $e');
      return null;
    }
  }

  /// Sign in against a local dev harness with no OAuth provider involved.
  ///
  /// Community builds cannot complete a real OAuth flow: Google and Apple issue
  /// OAuth clients against the official bundle id, and a community build is
  /// deliberately signed with a suffixed one. The backend mints a Firebase custom
  /// token against the local Auth emulator instead, and this reuses the same
  /// custom-token sign-in the OAuth path ends with.
  ///
  /// The real gate is server-side and structural (the endpoint 404s unless the
  /// backend is bound to an Auth emulator). The profile check here is only to
  /// keep the call from being made at all outside local development.
  Future<UserCredential?> signInWithLocalDevToken({String uid = 'local-dev-user'}) async {
    if (Env.profile != AppEnvironmentProfile.localDev) {
      throw StateError('Local development sign-in is only available in the local_dev profile.');
    }

    final response = await http.post(
      Uri.parse('${Env.authApiBaseUrl}v1/auth/local-dev/custom-token'),
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: {'uid': uid},
    ).timeout(
      const Duration(seconds: 8),
      onTimeout: () => throw StateError(
        'Cannot reach the local development server. Connect the iPhone to the same Wi-Fi as the Mac and build with OMI_DEV_HOST set to the Mac address.',
      ),
    );

    if (response.statusCode == 404) {
      throw StateError(
        'This backend has no local-dev sign-in endpoint. It is only registered when the '
        'backend runs against a Firebase Auth emulator — check the harness is up.',
      );
    }
    if (response.statusCode != 200) {
      throw Exception('Local development sign-in failed: HTTP ${response.statusCode}');
    }

    final decoded = json.decode(response.body) as Map<String, dynamic>;
    final customToken = decoded['custom_token'] as String?;
    if (customToken == null || customToken.isEmpty) {
      throw Exception('Local development sign-in returned no custom token');
    }

    // Check reachability before the side-effecting Firebase sign-in. Timing out
    // signInWithCustomToken would not cancel it: a late success could create a
    // session after the UI has already reported failure.
    try {
      await http
          .get(Uri(scheme: 'http', host: Env.firebaseAuthEmulatorHost, port: Env.firebaseAuthEmulatorPort))
          .timeout(const Duration(seconds: 8));
    } catch (_) {
      throw StateError(
        'Cannot reach the local Firebase Auth emulator. Connect the iPhone to the same Wi-Fi as the Mac and build with OMI_DEV_HOST set to the Mac address.',
      );
    }

    final credential = await runAccountMutation(() => _firebaseAuth.signInWithCustomToken(customToken));
    await _updateUserPreferences(credential, 'local_dev');
    Logger.debug('Local development sign-in successful');
    return credential;
  }

  Future<UserCredential> _signInWithOAuthCredentials(Map<String, dynamic> oauthCredentials) async {
    final provider = oauthCredentials['provider'];
    final useCustomToken = Env.useAuthCustomToken;
    final customToken = oauthCredentials['custom_token'];

    // Use custom token if enabled and available
    if (useCustomToken && customToken != null) {
      Logger.debug('Signing in with Firebase custom token from $provider');
      return await runAccountMutation(() => _firebaseAuth.signInWithCustomToken(customToken));
    }

    // Fallback to OAuth credentials
    final idToken = oauthCredentials['id_token'];
    final accessToken = oauthCredentials['access_token'];

    Logger.debug('Signing in with $provider OAuth credentials');

    if (provider == 'google') {
      final credential = GoogleAuthProvider.credential(idToken: idToken, accessToken: accessToken);
      return await runAccountMutation(() => _firebaseAuth.signInWithCredential(credential));
    } else if (provider == 'apple') {
      final credential = OAuthProvider('apple.com').credential(idToken: idToken, accessToken: accessToken);
      return await runAccountMutation(() => _firebaseAuth.signInWithCredential(credential));
    } else {
      throw Exception('Unsupported provider: $provider');
    }
  }

  Future<void> _updateUserPreferences(UserCredential result, String provider,
      {AuthSessionSnapshot? expectedOwner}) async {
    try {
      final user = result.user;
      if (user == null) return;
      if (expectedOwner != null) {
        _requireLinkOwner(expectedOwner);
      } else {
        markAuthenticatedUser(user.uid);
      }

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
          await runAccountMutation(() async {
            if (expectedOwner != null) _requireLinkOwner(expectedOwner);
            await user.updateProfile(displayName: fullName);
            if (expectedOwner != null) _requireLinkOwner(expectedOwner);
            await user.reload();
          });
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
      if (expectedOwner != null) _requireLinkOwner(expectedOwner);
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
      OnboardingSyncRuntime.wake();
      final session = captureSessionSnapshot();
      if (session == null) return;
      final pendingSourceAtStart = OnboardingSyncRuntime.hasPendingAcquisitionSource;
      final localSourceAtStart = SharedPreferencesUtil().foundOmiSource;
      final state = await getUserOnboardingState();
      if (state != null && isSessionSnapshotCurrent(session)) {
        if (state['completed'] == true) {
          SharedPreferencesUtil().onboardingCompleted = true;
        }
        final acquisitionSource = state['acquisition_source'] as String? ?? '';
        // A GET started before an upload acknowledgement can carry the older
        // survey answer even after the outbox has cleared. Do not restore it.
        if (acquisitionSource.isNotEmpty &&
            !pendingSourceAtStart &&
            !OnboardingSyncRuntime.hasPendingAcquisitionSource &&
            SharedPreferencesUtil().foundOmiSource == localSourceAtStart) {
          SharedPreferencesUtil().foundOmiSource = acquisitionSource;
        }
        // Restore language from server if not already set locally
        final serverLanguage = await getUserPrimaryLanguage();
        if (serverLanguage != null && serverLanguage.isNotEmpty && isSessionSnapshotCurrent(session)) {
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
      var user = _firebaseAuth.currentUser;

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
        user = _firebaseAuth.currentUser;
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

  AuthSessionSnapshot _captureLinkOwner(User user, String? expectedOwnerUid) {
    if (expectedOwnerUid != null && expectedOwnerUid != user.uid) {
      throw StateError('Account changed before provider linking');
    }
    handleAuthUserChanged(user.uid);
    final owner = AuthSessionSnapshot(ownerUid: user.uid, generation: _sessionGeneration);
    _requireLinkOwner(owner);
    return owner;
  }

  void _requireLinkOwner(AuthSessionSnapshot owner) {
    if (_sessionExpired || _tokenGateway.currentUser?.uid != owner.ownerUid || _sessionGeneration != owner.generation) {
      throw StateError('Account changed during provider linking');
    }
  }

  Future<ProviderLinkResult?> linkWithProvider(
    String provider, {
    String? expectedOwnerUid,
    ProviderLinkAuthorization? authorization,
  }) async {
    final user = _firebaseAuth.currentUser;
    if (user == null) throw StateError('No user is currently signed in');
    final owner = _captureLinkOwner(user, expectedOwnerUid);
    if (authorization != null && !authorization.canCancel) return null;
    final credential = await _authorizeProviderLink(provider, authorization);
    if (credential == null) return null;
    return _linkOwnedProvider(owner, user, provider, credential, authorization: authorization);
  }

  Future<AuthCredential?> _authorizeProviderLink(String provider, ProviderLinkAuthorization? authorization) async {
    final authorize = _authorizeProviderLinkOverride;
    if (authorize != null) {
      final pending = authorize(provider);
      return authorization?._untilCancelled(pending) ?? pending;
    }
    if (provider == 'google' &&
        !kIsWeb &&
        (defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.android) &&
        !Env.useWebAuth) {
      final pending = _requestGoogleMobileCredential();
      return authorization?._untilCancelled(pending) ?? pending;
    }
    if (provider == 'apple' && !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS && !Env.useWebAuth) {
      final pending = _requestAppleMobileCredential().then((result) => result.credential);
      return authorization?._untilCancelled(pending) ?? pending;
    }
    // Minting a custom Firebase token signs in on the server. Linking only needs the provider credential.
    final oauthCredentials = await _requestOAuthCredentials(
      provider,
      useCustomToken: false,
      selectAccount: provider == 'google',
      authorization: authorization,
    );
    return oauthCredentials == null ? null : _createFirebaseCredential(oauthCredentials);
  }

  Future<ProviderLinkResult?> _linkOwnedProvider(
    AuthSessionSnapshot owner,
    User sourceUser,
    String provider,
    AuthCredential providerCredential, {
    ProviderLinkAuthorization? authorization,
  }) async {
    final outcome = await runAccountMutation(() async {
      if (authorization?._isCancelled == true) return null;
      _requireLinkOwner(owner);
      // Capture proof before the native link can fail or replace currentUser.
      final sourceIsAnonymous = sourceUser.isAnonymous;
      final sourceToken = sourceIsAnonymous ? await sourceUser.getIdToken() : null;
      _requireLinkOwner(owner);
      late UserCredential credential;
      ProviderLinkResult result;
      var collision = false;
      try {
        if (authorization != null && !authorization._dispatch()) return null;
        credential = await sourceUser.linkWithCredential(providerCredential);
        _requireLinkOwner(owner);
        if (credential.user?.uid != owner.ownerUid) throw StateError('Unexpected linked account');
        result = ProviderLinkResult(destinationUid: credential.user?.uid);
      } on FirebaseAuthException catch (error) {
        _requireLinkOwner(owner);
        if (!sourceIsAnonymous &&
            const {
              'credential-already-in-use',
              'account-exists-with-different-credential',
              'email-already-in-use',
            }.contains(error.code)) {
          throw const ProviderLinkConflict();
        }
        final destinationCredential = error.credential;
        if (error.code != 'credential-already-in-use' || destinationCredential == null) rethrow;
        collision = true;
        result = await resolveProviderCredentialCollision(
          sourceUid: owner.ownerUid,
          sourceIsAnonymous: sourceIsAnonymous,
          captureSourceToken: () async => sourceToken,
          establishDestination: () async {
            _requireLinkOwner(owner);
            await _prepareSiriBestEffort();
            _requireLinkOwner(owner);
            // Already holding the mutation slot: do not call queued wrappers.
            handleAuthUserChanged(null);
            await _tokenGateway.signOut();
            credential = await _firebaseAuth.signInWithCredential(destinationCredential);
            return credential.user?.uid;
          },
        );
      }
      final destination = credential.user;
      if (destination == null || _tokenGateway.currentUser?.uid != destination.uid) {
        throw StateError('Linked account is no longer current');
      }
      // Adding a sign-in method to an established account keeps the live
      // session and its owner generation, even if the provider issues new tokens.
      if (sourceIsAnonymous) markAuthenticatedUser(destination.uid);
      return (
        credential: credential,
        result: result,
        collision: collision,
        sourceWasAnonymous: sourceIsAnonymous,
        owner: AuthSessionSnapshot(ownerUid: destination.uid, generation: _sessionGeneration)
      );
    });
    if (outcome == null) return null;
    _requireLinkOwner(outcome.owner);
    if (outcome.collision) {
      await getIdToken();
      _requireLinkOwner(outcome.owner);
      final user = outcome.credential.user!;
      SharedPreferencesUtil().onboardingCompleted = false;
      SharedPreferencesUtil().uid = user.uid;
      SharedPreferencesUtil().email = user.email ?? '';
      SharedPreferencesUtil().givenName = user.displayName?.split(' ')[0] ?? '';
    } else if (outcome.sourceWasAnonymous) {
      await _updateUserPreferences(outcome.credential, provider, expectedOwner: outcome.owner);
    }
    _requireLinkOwner(outcome.owner);
    return ProviderLinkResult(
      destinationUid: outcome.result.destinationUid,
      destinationSession: outcome.owner,
      anonymousSourceMigration: outcome.result.anonymousSourceMigration,
    );
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

  Future<ProviderLinkResult?> linkWithGoogle({
    String? expectedOwnerUid,
    ProviderLinkAuthorization? authorization,
  }) {
    return linkWithProvider('google', expectedOwnerUid: expectedOwnerUid, authorization: authorization);
  }

  Future<ProviderLinkResult?> linkWithApple({
    String? expectedOwnerUid,
    ProviderLinkAuthorization? authorization,
  }) {
    return linkWithProvider('apple', expectedOwnerUid: expectedOwnerUid, authorization: authorization);
  }
}
