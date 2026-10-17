import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/variants/yinka/widgets/onboarding_card.dart';
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
  static const _aiProviders = 'Deepgram & OpenAI';

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final p = OnboardingHero.palette;
    final body = OmiType.callout.copyWith(color: p.textSecondary, height: 1.45);
    final fine = OmiType.caption.copyWith(color: p.textTertiary, height: 1.3);
    final link = fine.copyWith(color: p.textSecondary, decoration: TextDecoration.underline);
    return OnboardingHeroStep(
      headline: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Semantics(
            header: true,
            child: Text(
              l10n.dataAndPrivacy,
              style: OmiType.title1.copyWith(color: p.textPrimary),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 320),
            child: Text(l10n.consentShortMessage, style: body, textAlign: TextAlign.center),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            l10n.consentAiProviders(_aiProviders),
            key: const Key('ai_consent_providers'),
            style: OmiType.footnote.copyWith(color: p.textTertiary),
            textAlign: TextAlign.center,
          ),
        ],
      ),
      buttons: [
        OnboardingHeroButton(
          key: const Key('ai_consent_agree'),
          label: l10n.agreeAndContinue,
          onPressed: () {
            OmiHaptics.selection();
            widget.onAgree();
          },
        ),
        // Signed in with the wrong account: back to sign-in without agreeing first. A plain TextButton:
        // OmiButton paints its label in the app theme's colour, which is near-black in light mode and
        // would vanish on the film.
        SizedBox(
          height: 48,
          child: TextButton(
            key: const Key('ai_consent_use_different_account'),
            onPressed: widget.onUseDifferentAccount,
            style: TextButton.styleFrom(
              foregroundColor: p.textSecondary,
              shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
            ),
            child: Text(
              l10n.useDifferentAccount,
              style: OmiType.callout.copyWith(color: p.textSecondary, fontWeight: FontWeight.w600),
            ),
          ),
        ),
      ],
      // One quiet line where it fits; long translations wrap to a second line.
      legal: Text.rich(
        TextSpan(
          style: fine,
          children: [
            TextSpan(text: l10n.byContinuingYouAgree),
            TextSpan(text: l10n.termsOfUse, style: link, recognizer: _termsRecognizer),
            TextSpan(text: l10n.and),
            TextSpan(text: l10n.privacyPolicy, style: link, recognizer: _privacyRecognizer),
            const TextSpan(text: '.'),
          ],
        ),
        textAlign: TextAlign.center,
      ),
    );
  }
}
