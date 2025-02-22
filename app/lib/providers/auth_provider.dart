import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:friend_private/backend/http/api/apps.dart' as apps_api;

class AuthenticationProvider extends BaseProvider {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  User? user;
  String? authToken;
  bool _loading = false;
  bool get loading => _loading;

  AuthenticationProvider() {
    _auth.authStateChanges().distinct((p, n) => p?.uid == n?.uid).listen((User? user) {
      this.user = user;
      SharedPreferencesUtil().uid = user?.uid ?? '';
      SharedPreferencesUtil().email = user?.email ?? '';
      SharedPreferencesUtil().givenName = user?.displayName?.split(' ')[0] ?? '';
    });
    _auth.idTokenChanges().distinct((p, n) => p?.uid == n?.uid).listen((User? user) async {
      if (user == null) {
        debugPrint('User is currently signed out or the token has been revoked! ${user == null}');
        SharedPreferencesUtil().authToken = '';
        authToken = null;
      } else {
        debugPrint('User is signed in at ${DateTime.now()} with user ${user.uid}');
        try {
          if (SharedPreferencesUtil().authToken.isEmpty ||
              DateTime.now().millisecondsSinceEpoch > SharedPreferencesUtil().tokenExpirationTime) {
            authToken = await getIdToken();
          }
        } catch (e) {
          authToken = null;
          debugPrint('Failed to get token: $e');
        }
      }
      notifyListeners();
    });
  }

  bool isSignedIn() => _auth.currentUser != null && !_auth.currentUser!.isAnonymous;

  void setLoading(bool value) {
    _loading = value;
    notifyListeners();
  }

  Future<void> onGoogleSignIn(Function() onSignIn) async {
    if (!loading) {
      setLoadingState(true);
      await signInWithGoogle();
      if (isSignedIn()) {
        _signIn(onSignIn);
      } else {
        AppSnackbar.showSnackbarError('Failed to sign in with Google, please try again.');
      }
      setLoadingState(false);
    }
  }

  Future<void> onAppleSignIn(Function() onSignIn) async {
    if (!loading) {
      setLoadingState(true);
      await signInWithApple();
      if (isSignedIn()) {
        _signIn(onSignIn);
      } else {
        AppSnackbar.showSnackbarError('Failed to sign in with Apple, please try again.');
      }
      setLoadingState(false);
    }
  }

  Future<String?> _getIdToken() async {
    try {
      final token = await getIdToken();
      NotificationService.instance.saveNotificationToken();

      debugPrint('Token: $token');
      return token;
    } catch (e, stackTrace) {
      AppSnackbar.showSnackbarError('Failed to retrieve firebase token, please try again.');

      CrashReporting.reportHandledCrash(e, stackTrace, level: NonFatalExceptionLevel.error);

      return null;
    }
  }

  void _signIn(Function() onSignIn) async {
    String? token = await _getIdToken();

    if (token != null) {
      User user;
      try {
        user = FirebaseAuth.instance.currentUser!;
      } catch (e, stackTrace) {
        AppSnackbar.showSnackbarError('Unexpected error signing in, Firebase error, please try again.');

        CrashReporting.reportHandledCrash(e, stackTrace, level: NonFatalExceptionLevel.error);
        return;
      }
      String newUid = user.uid;
      SharedPreferencesUtil().uid = newUid;
      MixpanelManager().identify();
      onSignIn();
    } else {
      AppSnackbar.showSnackbarError('Unexpected error signing in, please try again');
    }
  }

  void openTermsOfService() {
    _launchUrl('https://basedhardware.com/terms');
  }

  void openPrivacyPolicy() {
    _launchUrl('https://www.omi.me/pages/privacy');
  }

  void _launchUrl(String url) async {
    if (!await launchUrl(Uri.parse(url))) throw 'Could not launch $url';
  }

  Future<void> linkWithGoogle() async {
    setLoading(true);
    try {
      final GoogleSignInAccount? googleUser = await GoogleSignIn().signIn();
      if (googleUser == null) {
        setLoading(false);
        return;
      }

      final GoogleSignInAuthentication googleAuth = await googleUser.authentication;
      final credential = GoogleAuthProvider.credential(
        accessToken: googleAuth.accessToken,
        idToken: googleAuth.idToken,
      );

      try {
        await FirebaseAuth.instance.currentUser?.linkWithCredential(credential);
      } catch (e) {
        if (e is FirebaseAuthException && e.code == 'credential-already-in-use') {
          // Get existing user credentials
          final existingCred = e.credential;
          final oldUserId = FirebaseAuth.instance.currentUser?.uid;

          // Sign out current anonymous user
          await FirebaseAuth.instance.signOut();

          // Sign in with existing account
          await FirebaseAuth.instance.signInWithCredential(existingCred!);
          final newUserId = FirebaseAuth.instance.currentUser?.uid;
          await getIdToken();

          SharedPreferencesUtil().onboardingCompleted = false;
          SharedPreferencesUtil().uid = newUserId ?? '';
          SharedPreferencesUtil().email = FirebaseAuth.instance.currentUser?.email ?? '';
          SharedPreferencesUtil().givenName = FirebaseAuth.instance.currentUser?.displayName?.split(' ')[0] ?? '';
          if (oldUserId != null && newUserId != null) {
            await migrateAppOwnerId(oldUserId);
          }
          return;
        }
        AppSnackbar.showSnackbarError('Failed to link with Google, please try again.');
        rethrow;
      }
    } catch (e) {
      print('Error linking with Google: $e');
      AppSnackbar.showSnackbarError('Failed to link with Google, please try again.');
      rethrow;
    } finally {
      setLoading(false);
    }
  }

  Future<void> linkWithApple() async {
    setLoading(true);
    try {
      final appleProvider = AppleAuthProvider();
      try {
        await FirebaseAuth.instance.currentUser?.linkWithProvider(appleProvider);
      } catch (e) {
        if (e is FirebaseAuthException && e.code == 'credential-already-in-use') {
          // Get existing user credentials
          final existingCred = e.credential;
          final oldUserId = FirebaseAuth.instance.currentUser?.uid;

          // Sign out current anonymous user
          await FirebaseAuth.instance.signOut();

          // Sign in with existing account
          await FirebaseAuth.instance.signInWithCredential(existingCred!);
          final newUserId = FirebaseAuth.instance.currentUser?.uid;
          await getIdToken();

          SharedPreferencesUtil().onboardingCompleted = false;
          SharedPreferencesUtil().uid = newUserId ?? '';
          SharedPreferencesUtil().email = FirebaseAuth.instance.currentUser?.email ?? '';
          SharedPreferencesUtil().givenName = FirebaseAuth.instance.currentUser?.displayName?.split(' ')[0] ?? '';
          if (oldUserId != null && newUserId != null) {
            await migrateAppOwnerId(oldUserId);
          }
          return;
        }
        AppSnackbar.showSnackbarError('Failed to link with Apple, please try again.');
        rethrow;
      }
    } catch (e) {
      print('Error linking with Apple: $e');
      AppSnackbar.showSnackbarError('Failed to link with Apple, please try again.');
      rethrow;
    } finally {
      setLoading(false);
    }
  }

  Future<bool> migrateAppOwnerId(String oldId) async {
    return await apps_api.migrateAppOwnerId(oldId);
  }
}
