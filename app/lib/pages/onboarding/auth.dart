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

  const AuthComponent({super.key, required this.onSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, provider, child) {
        return OnboardingStep(
          card: OnboardingCard(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xxl, OmiSpacing.xl, OmiSpacing.xxl, OmiSpacing.xs),
            content: [
              // Loading indicator or spacing
              SizedBox(
                height: 20,
                child: provider.loading ? const Center(child: OmiSpinner(size: OmiSpinnerSize.small)) : null,
              ),

              // Title text
              MediaQuery.withClampedTextScaling(
                maxScaleFactor: 1.4,
                child: Text(
                  context.l10n.speakTranscribeSummarize,
                  style: TextStyle(
                    color: OmiColors.textPrimary,
                    fontSize: 32,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),
              ),

              const SizedBox(height: 32),
            ],
            footer: [
              // Sign in buttons
              if (!provider.isLocalDevProfile &&
                  (Theme.of(context).platform == TargetPlatform.iOS ||
                      Theme.of(context).platform == TargetPlatform.android)) ...[
                OmiButton(
                  key: const Key('auth_sign_in_apple'),
                  label: context.l10n.signInWithApple,
                  leading: const FaIcon(FontAwesomeIcons.apple),
                  expand: true,
                  maxLines: 3,
                  onPressed: () {
                    OmiHaptics.selection();
                    provider.onAppleSignIn(widget.onSignIn);
                  },
                ),
                const SizedBox(height: OmiSpacing.md),
              ],

              // Google sign in button
              if (!provider.isLocalDevProfile)
                OmiButton(
                  key: const Key('auth_sign_in_google'),
                  label: context.l10n.signInWithGoogle,
                  leading: const FaIcon(FontAwesomeIcons.google),
                  expand: true,
                  maxLines: 3,
                  onPressed: () {
                    OmiHaptics.selection();
                    provider.onGoogleSignIn(widget.onSignIn);
                  },
                ),

              // Local development sign-in. Only rendered for a local_dev
              // build: community builds cannot complete a real OAuth flow,
              // because provider OAuth clients are bound to the official
              // bundle id and a community build is signed with a suffixed
              // one. Never shown in a production-family build.
              if (provider.isLocalDevProfile) ...[
                const SizedBox(height: 12),
                ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: 56),
                  child: OutlinedButton(
                    key: const Key('auth_sign_in_local_dev'),
                    onPressed: () {
                      OmiHaptics.selection();
                      provider.onLocalDevSignIn(widget.onSignIn);
                    },
                    style: OutlinedButton.styleFrom(
                      foregroundColor: OmiColors.textPrimary,
                      side: BorderSide(color: OmiColors.textPrimary.withValues(alpha: 0.4)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                    ),
                    child: const Text(
                      'Sign in (local dev)',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
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
        );
      },
    );
  }
}
