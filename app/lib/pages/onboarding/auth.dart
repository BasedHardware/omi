import 'dart:io';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/widgets/sign_in_button.dart';
import 'package:provider/provider.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;

  const AuthComponent({super.key, required this.onSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  @override
  Widget build(BuildContext context) {
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
              if (Platform.isIOS) ...[
                SignInButton.withApple(
                  title: 'Sign in with Apple',
                  onTap: () async {
                    final user = FirebaseAuth.instance.currentUser;
                    if (user != null && user.isAnonymous && SharedPreferencesUtil().hasPersonaCreated) {
                      await provider.linkWithApple();
                      if (mounted) {
                        SharedPreferencesUtil().hasOmiDevice = true;
                        SharedPreferencesUtil().verifiedPersonaId = null;
                        widget.onSignIn();
                      }
                    } else {
                      provider.onAppleSignIn(widget.onSignIn);
                    }
                  },
                ),
                const SizedBox(height: 12),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Expanded(
                      child: Container(
                        height: 2,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(2),
                          gradient: LinearGradient(
                            colors: [
                              const Color(0xfff1f1f1).withOpacity(0),
                              const Color(0xfff1f1f1).withOpacity(0.7),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Text(
                      'OR',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Container(
                        height: 2,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(2),
                          gradient: LinearGradient(
                            colors: [
                              const Color(0xfff1f1f1).withOpacity(0.7),
                              const Color(0xfff1f1f1).withOpacity(0),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 12),
              SignInButton.withGoogle(
                title: 'Sign in with Google',
                onTap: () async {
                  final user = FirebaseAuth.instance.currentUser;
                  if (user != null && user.isAnonymous && SharedPreferencesUtil().hasPersonaCreated) {
                    await provider.linkWithGoogle();
                    if (mounted) {
                      SharedPreferencesUtil().hasOmiDevice = true;
                      SharedPreferencesUtil().verifiedPersonaId = null;
                      widget.onSignIn();
                    }
                  } else {
                    provider.onGoogleSignIn(widget.onSignIn);
                  }
                },
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
