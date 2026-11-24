import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;

  /// Host tests cannot set [Platform.isIOS]; this renders the Apple button there.
  @visibleForTesting
  final bool? debugShowAppleSignIn;

  const AuthComponent({super.key, required this.onSignIn, this.debugShowAppleSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  final _buttonsTop = GlobalKey();
  late final VoidCallback _releaseFeedbackClearance;

  @override
  void initState() {
    super.initState();
    // Sign-in errors are shown from the provider on the global navigator, so they float above the
    // buttons through the root clearance rather than a page OmiFeedbackClearance.
    _releaseFeedbackClearance = OmiFeedback.claimBottomClearance(_clearSignInButtons);
  }

  @override
  void dispose() {
    _releaseFeedbackClearance();
    super.dispose();
  }

  /// Lifts toasts above the sign-in buttons, measured when the toast is shown: text size and
  /// scrolling move them.
  double _clearSignInButtons(BuildContext context) {
    final marker = _buttonsTop.currentContext?.findRenderObject();
    if (marker is! RenderBox || !marker.attached) return 0;
    final media = MediaQuery.of(context);
    final bottom = media.size.height - media.viewPadding.bottom;
    return math.max(0, bottom - marker.localToGlobal(Offset.zero).dy);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, provider, child) {
        return OnboardingStep(
          card: OnboardingCard(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xxl, 26, OmiSpacing.xxl, OmiSpacing.xs),
            content: [
              // Loading indicator or spacing
              SizedBox(
                height: 20,
                child: provider.loading ? const Center(child: OmiSpinner(size: OmiSpinnerSize.small)) : null,
              ),

              // Title text
              Text(
                context.l10n.speakTranscribeSummarize,
                // A 32 pt headline past 1.5x breaks "Transcribe." mid-word; the buttons below carry
                // the text size instead.
                textScaler: MediaQuery.textScalerOf(context).clamp(maxScaleFactor: 1.5),
                style: TextStyle(
                  color: OmiColors.textPrimary,
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  height: 1.2,
                  fontFamily: 'Manrope',
                ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 32),
            ],
            // The buttons stay pinned under the scrolling title at every text size. Their labels stop
            // growing at 2x so both buttons and the legal line fit on a small phone.
            footer: [
              MediaQuery.withClampedTextScaling(
                maxScaleFactor: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Where the sign-in buttons start; toasts float above it.
                    SizedBox(key: _buttonsTop, width: double.infinity),

                    // Sign in buttons
                    if (!provider.isLocalDevProfile &&
                        (widget.debugShowAppleSignIn ?? (Platform.isIOS || Platform.isAndroid))) ...[
                      ConstrainedBox(
                        constraints: const BoxConstraints(minWidth: double.infinity, minHeight: 56),
                        child: ElevatedButton(
                          onPressed: () {
                            OmiHaptics.selection();
                            provider.onAppleSignIn(widget.onSignIn);
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: OmiColors.accent,
                            foregroundColor: OmiColors.onAccent,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                          ),
                          child: Padding(
                            // Wrapped labels keep space above and below; one line still fits in 56 pt.
                            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const FaIcon(FontAwesomeIcons.apple, size: 24),
                                const SizedBox(width: 8),
                                Flexible(
                                  child: Text(
                                    context.l10n.signInWithApple,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                      fontFamily: 'Manrope',
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // Google sign in button
                    if (!provider.isLocalDevProfile)
                      ConstrainedBox(
                        constraints: const BoxConstraints(minWidth: double.infinity, minHeight: 56),
                        child: ElevatedButton(
                          onPressed: () {
                            OmiHaptics.selection();
                            provider.onGoogleSignIn(widget.onSignIn);
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: OmiColors.accent,
                            foregroundColor: OmiColors.onAccent,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                          ),
                          child: Padding(
                            // Wrapped labels keep space above and below; one line still fits in 56 pt.
                            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const FaIcon(FontAwesomeIcons.google, size: 20),
                                const SizedBox(width: 8),
                                Flexible(
                                  child: Text(
                                    context.l10n.signInWithGoogle,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                        fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),

                    // Local development sign-in. Only rendered for a local_dev
                    // build: community builds cannot complete a real OAuth flow,
                    // because provider OAuth clients are bound to the official
                    // bundle id and a community build is signed with a suffixed
                    // one. Never shown in a production-family build.
                    if (provider.isLocalDevProfile) ...[
                      const SizedBox(height: 12),
                      ConstrainedBox(
                        constraints: const BoxConstraints(minWidth: double.infinity, minHeight: 56),
                        child: OutlinedButton(
                          onPressed: () {
                            OmiHaptics.selection();
                            provider.onLocalDevSignIn(widget.onSignIn);
                          },
                          style: OutlinedButton.styleFrom(
                            foregroundColor: OmiColors.textPrimary,
                            side: BorderSide(color: OmiColors.textPrimary.withValues(alpha: 0.4)),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                          ),
                          child: const Padding(
                            padding: EdgeInsets.symmetric(vertical: OmiSpacing.sm),
                            child: Text(
                              'Sign in (local dev)',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                            ),
                          ),
                        ),
                      ),
                    ],

                    const SizedBox(height: 24),

                    // Privacy policy text (same as welcome page)
                    RichText(
                      textAlign: TextAlign.center,
                      text: TextSpan(
                        style: TextStyle(
                          color: OmiColors.textPrimary.withValues(alpha: 0.6),
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
            ],
          ),
        );
      },
    );
  }
}
