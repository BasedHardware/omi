import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

class AuthenticationProvider extends BaseProvider {
  Future<void> onGoogleSignIn(Function() onSignIn) async {
    if (!loading) {
      setLoadingState(true);
      await signInWithGoogle();
      _signIn(onSignIn);
      setLoadingState(false);
    }
  }

  Future<void> onAppleSignIn(Function() onSignIn) async {
    if (!loading) {
      setLoadingState(true);
      await signInWithApple();
      _signIn(onSignIn);
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
    _launchUrl('https://basedhardware.com/privacy-policy');
  }

  void _launchUrl(String url) async {
    if (!await launchUrl(Uri.parse(url))) throw 'Could not launch $url';
  }
}
