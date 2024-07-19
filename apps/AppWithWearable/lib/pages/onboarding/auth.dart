import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/features/backups.dart';
import 'package:sign_in_button/sign_in_button.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:url_launcher/url_launcher.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;

  const AuthComponent({super.key, required this.onSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  bool loading = false;

  changeLoadingState() => setState(() => loading = !loading);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Center(
            child: SizedBox(
              height: 24,
              width: 24,
              child: loading
                  ? const CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation(Colors.white),
                    )
                  : null,
            ),
          ),
          const SizedBox(height: 32),
          !Platform.isIOS
              ? SignInButton(
                  Buttons.google,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  onPressed: loading
                      ? () {}
                      : () async {
                          changeLoadingState();
                          await signInWithGoogle();
                          _signIn();
                        },
                )
              : SignInWithAppleButton(
                  style: SignInWithAppleButtonStyle.whiteOutlined,
                  onPressed: loading
                      ? () {}
                      : () async {
                          changeLoadingState();
                          await signInWithApple();
                          _signIn();
                        },
                  height: 52,
                ),
          const SizedBox(height: 16),
          RichText(
            textAlign: TextAlign.center,
            text: TextSpan(
              style: const TextStyle(color: Colors.white, fontSize: 12),
              children: [
                const TextSpan(text: 'By Signing in, you agree to our\n'),
                TextSpan(
                  text: 'Terms of service',
                  style: const TextStyle(decoration: TextDecoration.underline),
                  recognizer: TapGestureRecognizer()..onTap = () => _launchUrl('https://basedhardware.com/terms'),
                ),
                const TextSpan(text: ' and '),
                TextSpan(
                  text: 'Privacy Policy',
                  style: const TextStyle(decoration: TextDecoration.underline),
                  recognizer: TapGestureRecognizer()
                    ..onTap = () {
                      _launchUrl('https://basedhardware.com/privacy-policy');
                    },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _signIn() async {
    var token = await getIdToken();
    print('Token: $token');
    if (token != null) {
      User user = FirebaseAuth.instance.currentUser!;
      String prevUid = SharedPreferencesUtil().uid;
      String newUid = user.uid;
      if (prevUid.isNotEmpty && prevUid != newUid) {
        // executeBackupWithUid(uid: newUid); this will anyway be called in home
        MixpanelManager().migrateUser(newUid);
        await migrateUserServer(prevUid, newUid);
        SharedPreferencesUtil().uid = newUid;
      } else {
        await retrieveBackup(newUid);
        SharedPreferencesUtil().uid = newUid;
        MixpanelManager().identify();
      }
      widget.onSignIn();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Unexpected error signing in, please try again.'),
      ));
    }
    changeLoadingState();
  }

  void _launchUrl(String url) async {
    if (!await launchUrl(Uri.parse(url))) throw 'Could not launch $url';
  }
}
