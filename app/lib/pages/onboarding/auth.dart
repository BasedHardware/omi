import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/utils/platform/platform_manager.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/variants/yinka/widgets/onboarding_card.dart';
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
  void initState() {
    super.initState();
    // Sign-in is the first onboarding screen now (the Get started page is gone): the funnel's
    // welcome step starts here.
    PlatformManager.instance.analytics.onboardingWelcomeShown();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, provider, child) {
        final p = OnboardingHero.palette;
        final legalStyle = OmiType.caption.copyWith(color: p.textTertiary, height: 1.3);
        return OnboardingHeroStep(
          headline: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // The omi wordmark is the headline; the promise sits under it, quieter.
              Semantics(
                header: true,
                label: 'Omi',
                child: Assets.images.logoTextWhite.image(
                  key: const Key('onboarding_wordmark'),
                  height: 56,
                  color: p.textPrimary,
                ),
              ),
              const SizedBox(height: OmiSpacing.sm),
              Text(
                context.l10n.speakTranscribeSummarize,
                style: OmiType.title3.copyWith(color: p.textSecondary, fontWeight: FontWeight.w500),
                textAlign: TextAlign.center,
              ),
              SizedBox(
                height: 28,
                child: provider.loading ? const Center(child: OmiSpinner(size: OmiSpinnerSize.small)) : null,
              ),
            ],
          ),
          buttons: [
            if (!provider.isLocalDevProfile && (Platform.isIOS || Platform.isAndroid)) ...[
              OnboardingHeroButton(
                label: context.l10n.signInWithApple,
                icon: const FaIcon(FontAwesomeIcons.apple),
                onPressed: () {
                  OmiHaptics.selection();
                  provider.onAppleSignIn(widget.onSignIn);
                },
              ),
              const SizedBox(height: OmiSpacing.sm),
            ],
            if (!provider.isLocalDevProfile)
              OnboardingHeroButton(
                label: context.l10n.signInWithGoogle,
                icon: const FaIcon(FontAwesomeIcons.google),
                onPressed: () {
                  OmiHaptics.selection();
                  provider.onGoogleSignIn(widget.onSignIn);
                },
              ),
            // Local development sign-in. Only rendered for a local_dev build: community builds cannot
            // complete a real OAuth flow, because provider OAuth clients are bound to the official
            // bundle id and a community build is signed with a suffixed one. Never shown in a
            // production-family build.
            if (provider.isLocalDevProfile)
              OnboardingHeroButton(
                label: 'Sign in (local dev)', // omi-ux-allow: hardcoded-text -- local_dev builds only
                outlined: true,
                onPressed: () {
                  OmiHaptics.selection();
                  provider.onLocalDevSignIn(widget.onSignIn);
                },
              ),
          ],
          legal: Text.rich(
            TextSpan(
              style: legalStyle,
              children: [
                TextSpan(text: context.l10n.byContinuingAgree),
                TextSpan(
                  text: context.l10n.privacyPolicy,
                  style: legalStyle.copyWith(color: p.textSecondary, decoration: TextDecoration.underline),
                  recognizer: TapGestureRecognizer()..onTap = provider.openPrivacyPolicy,
                ),
                const TextSpan(text: ' & '),
                TextSpan(
                  text: context.l10n.termsOfUse,
                  style: legalStyle.copyWith(color: p.textSecondary, decoration: TextDecoration.underline),
                  recognizer: TapGestureRecognizer()..onTap = provider.openTermsOfService,
                ),
                const TextSpan(text: '.'),
              ],
            ),
            textAlign: TextAlign.center,
          ),
        );
      },
    );
  }
}
