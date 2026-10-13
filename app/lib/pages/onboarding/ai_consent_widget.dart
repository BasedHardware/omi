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

  /// The third-party AI services that receive audio and transcripts. Brand names, not translated.
  /// Keep in step with the privacy policy and the serving configuration (Apple 5.1.2(i): name who
  /// receives the data).
  static const _aiProviders = 'Deepgram, OpenAI';

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final small = OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.4);
    final link = small.copyWith(color: OmiColors.textPrimary, decoration: TextDecoration.underline);
    return OnboardingStep(
      card: OnboardingCard(
        crossAxisAlignment: CrossAxisAlignment.start,
        // Same bottom inset as the other steps, so Agree & Continue sits where every Continue does.
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.sm),
        content: [
          Semantics(header: true, child: Text(l10n.dataAndPrivacy, style: OmiType.title2)),
          const SizedBox(height: OmiSpacing.xs),
          Text(l10n.consentShortMessage, style: OmiType.subhead.copyWith(height: 1.4)),
          const SizedBox(height: OmiSpacing.md),
          Text(l10n.consentAiProviders(_aiProviders), style: small),
          const SizedBox(height: OmiSpacing.xxs),
          RichText(
            text: TextSpan(
              style: small,
              children: [
                TextSpan(text: l10n.privacyPolicy, style: link, recognizer: _privacyRecognizer),
                const TextSpan(text: '  ·  '),
                TextSpan(text: l10n.termsOfService, style: link, recognizer: _termsRecognizer),
              ],
            ),
          ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.md),
          // The way out sits above the main action, so the thumb lands on Agree & Continue.
          Align(
            alignment: Alignment.center,
            child: OmiButton.tertiary(
              key: const Key('ai_consent_use_different_account'),
              label: l10n.useDifferentAccount,
              size: OmiButtonSize.compact,
              onPressed: widget.onUseDifferentAccount,
            ),
          ),
          const SizedBox(height: OmiSpacing.xxs),
          OmiButton(
            key: const Key('ai_consent_agree'),
            label: l10n.agreeAndContinue,
            expand: true,
            onPressed: () {
              OmiHaptics.selection();
              widget.onAgree();
            },
          ),
        ],
      ),
    );
  }
}
