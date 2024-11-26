import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:provider/provider.dart';
import 'package:sign_in_button/sign_in_button.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;

  const AuthComponent({super.key, required this.onSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  @override
  Widget build(BuildContext context) {
    final customBackendUrl = SharedPreferencesUtil().customBackendUrl;

    return Consumer<AuthenticationProvider>(
      builder: (context, provider, child) {
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Center(
                child: SizedBox(
                  height: 24,
                  width: 24,
                  child: provider.loading
                      ? const CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation(Colors.white),
                        )
                      : null,
                ),
              ),
              SizedBox(height: MediaQuery.of(context).textScaleFactor > 1.0 ? 18 : 32),
              if (customBackendUrl.isEmpty)
                SignInButton(
                  Buttons.google,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  onPressed: () => provider.onGoogleSignIn(widget.onSignIn),
                ),
              if (customBackendUrl.isEmpty && Platform.isIOS)
                SignInWithAppleButton(
                  style: SignInWithAppleButtonStyle.whiteOutlined,
                  onPressed: () => provider.onAppleSignIn(widget.onSignIn),
                  height: 52,
                ),
              // if (customBackendUrl.isNotEmpty)
              //   ElevatedButton(
              //     onPressed: () {
              //     },
              //     child: Text('Sign In with Email'),
              //   ),
              // if (customBackendUrl.isNotEmpty) const SizedBox(height: 16),
              // if (customBackendUrl.isEmpty)
              //   TextButton(
              //     onPressed: () {},
              //     child: const Text('Sign Up'),
              //   ),
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
                      recognizer: TapGestureRecognizer()..onTap = provider.openTermsOfService,
                    ),
                    const TextSpan(text: ' and '),
                    TextSpan(
                      text: 'Privacy Policy',
                      style: const TextStyle(decoration: TextDecoration.underline),
                      recognizer: TapGestureRecognizer()..onTap = provider.openPrivacyPolicy,
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
