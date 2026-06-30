import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/auth_provider.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
        return Column(
          children: [
            // Background image area - takes remaining space
            Expanded(
              child: Container(), // Just takes up space for background image
            ),

            // Bottom drawer card - wraps content
            Container(
              width: double.infinity,
              padding: EdgeInsets.fromLTRB(32, 26, 32, MediaQuery.of(context).padding.bottom + 8),
              decoration: const BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.only(topLeft: Radius.circular(40), topRight: Radius.circular(40)),
              ),
              child: SafeArea(
                top: false,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Loading indicator or spacing
                    SizedBox(
                      height: 20,
                      child: provider.loading
                          ? const Center(
                              child: CircularProgressIndicator(valueColor: AlwaysStoppedAnimation(Colors.white)),
                            )
                          : null,
                    ),

                    // Title text
                    Text(
                      context.l10n.speakTranscribeSummarize,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                        height: 1.2,
                        fontFamily: 'Manrope',
                      ),
                      textAlign: TextAlign.center,
                    ),

                    const SizedBox(height: 32),

                    // Sign in buttons
                    if (Platform.isIOS || Platform.isAndroid) ...[
                      SizedBox(
                        width: double.infinity,
                        height: 56,
                        child: OmiButton(
                          label: context.l10n.signInWithApple,
                          icon: FontAwesomeIcons.apple,
                          iconSize: 24,
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            provider.onAppleSignIn(widget.onSignIn);
                          },
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // Google sign in button
                    SizedBox(
                      width: double.infinity,
                      height: 56,
                      child: OmiButton(
                        label: context.l10n.signInWithGoogle,
                        icon: FontAwesomeIcons.google,
                        iconSize: 20,
                        onPressed: () {
                          HapticFeedback.mediumImpact();
                          provider.onGoogleSignIn(widget.onSignIn);
                        },
                      ),
                    ),

                    const SizedBox(height: 24),

                    // Privacy policy text (same as welcome page)
                    RichText(
                      textAlign: TextAlign.center,
                      text: TextSpan(
                        style:
                            TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 11, fontFamily: 'Manrope'),
                        children: [
                          TextSpan(text: context.l10n.byContinuingAgree),
                          TextSpan(
                            text: context.l10n.privacyPolicy,
                            style: const TextStyle(decoration: TextDecoration.underline),
                            recognizer: TapGestureRecognizer()..onTap = provider.openPrivacyPolicy,
                          ),
                          const TextSpan(text: ' & '),
                          TextSpan(
                            text: context.l10n.termsOfUse,
                            style: const TextStyle(decoration: TextDecoration.underline),
                            recognizer: TapGestureRecognizer()..onTap = provider.openTermsOfService,
                          ),
                          const TextSpan(text: '.'),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
