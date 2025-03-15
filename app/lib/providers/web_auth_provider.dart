import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/services/web_notification_service.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:url_launcher/url_launcher.dart';

/// Web-compatible authentication provider that doesn't use Firebase
class WebAuthenticationProvider extends BaseProvider {
  String? user;
  String? authToken;
  bool _loading = false;
  bool get loading => _loading;

  WebAuthenticationProvider() {
    debugPrint('Initializing WebAuthenticationProvider without Firebase');
  }

  bool isSignedIn() => false; // Always return false for web demo

  void setLoading(bool value) {
    _loading = value;
    notifyListeners();
  }

  Future<void> onGoogleSignIn(Function() onSignIn) async {
    if (!loading) {
      setLoadingState(true);
      // Simulate sign in
      await Future.delayed(const Duration(seconds: 1));
      // Mock successful sign in
      _mockSignIn(onSignIn);
      setLoadingState(false);
    }
  }

  Future<void> onAppleSignIn(Function() onSignIn) async {
    if (!loading) {
      setLoadingState(true);
      // Simulate sign in
      await Future.delayed(const Duration(seconds: 1));
      // Mock successful sign in
      _mockSignIn(onSignIn);
      setLoadingState(false);
    }
  }

  void _mockSignIn(Function() onSignIn) async {
    // Set mock user data
    SharedPreferencesUtil().uid = 'web-mock-user-${DateTime.now().millisecondsSinceEpoch}';
    SharedPreferencesUtil().email = 'web-user@example.com';
    SharedPreferencesUtil().givenName = 'Web';
    
    // Call the success callback
    onSignIn();
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

  // Mock methods for web demo
  Future<void> linkWithGoogle() async {
    setLoading(true);
    try {
      // Simulate linking
      await Future.delayed(const Duration(seconds: 1));
      AppSnackbar.showSnackbarSuccess('Successfully linked with Google');
    } catch (e) {
      debugPrint('Error linking with Google: $e');
      AppSnackbar.showSnackbarError('Failed to link with Google, please try again.');
    } finally {
      setLoading(false);
    }
  }

  Future<void> linkWithApple() async {
    setLoading(true);
    try {
      // Simulate linking
      await Future.delayed(const Duration(seconds: 1));
      AppSnackbar.showSnackbarSuccess('Successfully linked with Apple');
    } catch (e) {
      debugPrint('Error linking with Apple: $e');
      AppSnackbar.showSnackbarError('Failed to link with Apple, please try again.');
    } finally {
      setLoading(false);
    }
  }
}
