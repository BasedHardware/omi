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
    // The providers read as part of the same statement: same size and colour.
    final body = OmiType.subhead.copyWith(height: 1.4);
    final fine = OmiType.caption.copyWith(color: OmiColors.textTertiary, height: 1.3);
    final link = fine.copyWith(color: OmiColors.textSecondary, decoration: TextDecoration.underline);
    // The other steps end their button `OmiSpacing.sm` above the safe area; this one keeps that
    // height and puts the agreement line in the space below it.
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final belowButton = bottomInset + OmiSpacing.sm < 40 ? 40.0 : bottomInset + OmiSpacing.sm;
    return OnboardingStep(
      card: OnboardingCard(
        crossAxisAlignment: CrossAxisAlignment.start,
        reserveBottomInset: false,
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.xl, 0),
        content: [
          Semantics(header: true, child: Text(l10n.dataAndPrivacy, style: OmiType.title2)),
          const SizedBox(height: OmiSpacing.xs),
          Text(l10n.consentShortMessage, style: body),
          const SizedBox(height: OmiSpacing.xs),
          Text(l10n.consentAiProviders(_aiProviders), style: body),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const Key('ai_consent_agree'),
            label: l10n.continueButton,
            expand: true,
            onPressed: () {
              OmiHaptics.selection();
              widget.onAgree();
            },
          ),
          SizedBox(
            height: belowButton,
            child: Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs),
              // One quiet line where it fits; long translations wrap to a second line.
              child: Text.rich(
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
            ),
          ),
        ],
      ),
    );
  }
}
