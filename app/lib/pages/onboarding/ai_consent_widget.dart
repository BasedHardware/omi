import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The data-and-AI consent step. Agree continues; "Use a Different Account" signs out and goes
/// back to sign-in, so someone on the wrong account (or who does not consent) is never stuck here.
class AiConsentWidget extends StatefulWidget {
  final VoidCallback onAgree;
  final FutureOr<void> Function() onUseDifferentAccount;

  const AiConsentWidget({super.key, required this.onAgree, required this.onUseDifferentAccount});

  @override
  State<AiConsentWidget> createState() => _AiConsentWidgetState();
}

class _AiConsentWidgetState extends State<AiConsentWidget> {
  final TapGestureRecognizer _privacyRecognizer = TapGestureRecognizer();
  final TapGestureRecognizer _termsRecognizer = TapGestureRecognizer();

  @override
  void initState() {
    super.initState();
    final provider = context.read<AuthenticationProvider>();
    _privacyRecognizer.onTap = provider.openPrivacyPolicy;
    _termsRecognizer.onTap = provider.openTermsOfService;
  }

  @override
  void dispose() {
    _privacyRecognizer.dispose();
    _termsRecognizer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final linkStyle = OmiType.footnote.copyWith(color: OmiColors.textPrimary, decoration: TextDecoration.underline);
    return OnboardingStep(
      card: OnboardingCard(
        crossAxisAlignment: CrossAxisAlignment.start,
        content: [
          Semantics(header: true, child: Text(context.l10n.dataAndPrivacy, style: OmiType.title1)),
          const SizedBox(height: OmiSpacing.md),
          Text(context.l10n.consentDataMessage, style: OmiType.subhead.copyWith(height: 1.5)),
          const SizedBox(height: OmiSpacing.md),
          RichText(
            text: TextSpan(
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.4),
              children: [
                TextSpan(text: context.l10n.yourDataIsProtected),
                TextSpan(text: context.l10n.privacyPolicy, style: linkStyle, recognizer: _privacyRecognizer),
                TextSpan(text: context.l10n.and),
                TextSpan(text: context.l10n.termsOfService, style: linkStyle, recognizer: _termsRecognizer),
                const TextSpan(text: '.'),
              ],
            ),
          ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const Key('ai_consent_agree'),
            label: context.l10n.agreeAndContinue,
            expand: true,
            onPressed: () {
              OmiHaptics.selection();
              widget.onAgree();
            },
          ),
          const SizedBox(height: OmiSpacing.xxs),
          OmiButton.tertiary(
            key: const Key('ai_consent_use_different_account'),
            label: context.l10n.useDifferentAccount,
            expand: true,
            onPressed: widget.onUseDifferentAccount,
          ),
        ],
      ),
    );
  }
}
