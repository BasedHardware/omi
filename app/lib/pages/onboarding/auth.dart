import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/env/env.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/local_emulator_auth.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;

  const AuthComponent({super.key, required this.onSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  void _onLocalEmulatorSignIn(AuthenticationProvider provider) {
    HapticFeedback.mediumImpact();
    provider.onLocalEmulatorSignIn(widget.onSignIn);
  }

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

            Container(
              width: double.infinity,
              padding: EdgeInsets.fromLTRB(32, 26, 32, MediaQuery.of(context).padding.bottom + 8),
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
                        child: _HoldForLocalEmulator(
                          key: const Key('appleSignIn'),
                          enabled: localEmulatorSignInEnabled(Env.profile),
                          onHoldComplete: () => _onLocalEmulatorSignIn(provider),
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            provider.onAppleSignIn(widget.onSignIn);
                          },
                          child: _AuthSignInButtonFace(
                            icon: const FaIcon(FontAwesomeIcons.apple, size: 24, color: Colors.black),
                            label: context.l10n.signInWithApple,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // Google sign in button
                    SizedBox(
                      width: double.infinity,
                      height: 56,
                      child: _HoldForLocalEmulator(
                        key: const Key('googleSignIn'),
                        enabled: localEmulatorSignInEnabled(Env.profile),
                        onHoldComplete: () => _onLocalEmulatorSignIn(provider),
                        onPressed: () {
                          HapticFeedback.mediumImpact();
                          provider.onGoogleSignIn(widget.onSignIn);
                        },
                        child: _AuthSignInButtonFace(
                          icon: const FaIcon(FontAwesomeIcons.google, size: 20, color: Colors.black),
                          label: context.l10n.signInWithGoogle,
                        ),
                      ),
                    ),

                    const SizedBox(height: 24),

                    // Privacy policy text (same as welcome page)
                    RichText(
                      textAlign: TextAlign.center,
                      text: TextSpan(
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.6),
                          fontSize: 11,
                          fontFamily: 'Manrope',
                        ),
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

/// Static Apple/Google face — no InkWell, splash, overlay, or elevation.
class _AuthSignInButtonFace extends StatelessWidget {
  final Widget icon;
  final String label;

  const _AuthSignInButtonFace({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(28),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          icon,
          const SizedBox(width: 8),
          Text(
            label,
            style: const TextStyle(
              color: Colors.black,
              fontSize: 18,
              fontWeight: FontWeight.w600,
              fontFamily: 'Manrope',
            ),
          ),
        ],
      ),
    );
  }
}

/// Holds a pointer for [kLocalEmulatorSignInHoldDuration] before firing Alice.
///
/// Uses [LongPressGestureRecognizer] with that duration so Flutter's default
/// ~500ms long-press cannot win the arena. A Material button splash used to
/// look like the hold completed in ~2s; this child has no press animation.
class _HoldForLocalEmulator extends StatelessWidget {
  final bool enabled;
  final VoidCallback onHoldComplete;
  final VoidCallback onPressed;
  final Widget child;

  const _HoldForLocalEmulator({
    super.key,
    required this.enabled,
    required this.onHoldComplete,
    required this.onPressed,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return RawGestureDetector(
      behavior: HitTestBehavior.opaque,
      gestures: <Type, GestureRecognizerFactory>{
        TapGestureRecognizer: GestureRecognizerFactoryWithHandlers<TapGestureRecognizer>(
          () => TapGestureRecognizer(debugOwner: this),
          (TapGestureRecognizer instance) {
            instance.onTap = onPressed;
          },
        ),
        if (enabled)
          LongPressGestureRecognizer: GestureRecognizerFactoryWithHandlers<LongPressGestureRecognizer>(
            () => LongPressGestureRecognizer(
              debugOwner: this,
              duration: kLocalEmulatorSignInHoldDuration,
            ),
            (LongPressGestureRecognizer instance) {
              instance.onLongPress = onHoldComplete;
            },
          ),
      },
      child: child,
    );
  }
}
