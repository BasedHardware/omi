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
    final l10n = context.l10n;
    return OnboardingStep(
      card: OnboardingCard(
        crossAxisAlignment: CrossAxisAlignment.start,
        content: [
          OnboardingHeader(title: l10n.consentTitle, subtitle: l10n.consentSubtitle),
          const SizedBox(height: OmiSpacing.lg),
          // v2: what is stored, who processes it and what the person controls, as one grouped card.
          Container(
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.rowAll),
            child: Column(
              children: [
                _ConsentRow(glyph: OmiGlyphs.waveform, title: l10n.consentStoredTitle, body: l10n.consentStoredBody),
                const _ConsentDivider(),
                _ConsentRow(glyph: OmiGlyphs.cpu, title: l10n.consentProcessorsTitle, body: l10n.consentProcessorsBody),
                const _ConsentDivider(),
                _ConsentRow(glyph: OmiGlyphs.hand, title: l10n.consentControlTitle, body: l10n.consentControlBody),
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Wrap(
            spacing: OmiSpacing.md,
            children: [
              _ConsentLink(label: l10n.readPrivacyPolicy, recognizer: _privacyRecognizer),
              _ConsentLink(label: l10n.termsOfService, recognizer: _termsRecognizer),
            ],
          ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.md),
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

class _ConsentRow extends StatelessWidget {
  const _ConsentRow({required this.glyph, required this.title, required this.body});

  final String glyph;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 30,
            height: 30,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
            child: OmiGlyph(glyph, size: 17, color: OmiColors.textPrimary),
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: MergeSemantics(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.headline),
                  const SizedBox(height: 2),
                  OmiBalancedText(body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ConsentDivider extends StatelessWidget {
  const _ConsentDivider();

  @override
  Widget build(BuildContext context) => Divider(height: 0.5, thickness: 0.5, indent: 58, color: OmiColors.border);
}

/// A "Read the Privacy Policy ›" link: a 44pt-tall text button that opens the document.
class _ConsentLink extends StatelessWidget {
  const _ConsentLink({required this.label, required this.recognizer});

  final String label;
  final TapGestureRecognizer recognizer;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      link: true,
      label: label,
      excludeSemantics: true,
      onTap: recognizer.onTap,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: recognizer.onTap,
        child: Container(
          padding: OnboardingCard.textInset,
          alignment: Alignment.centerLeft,
          constraints: const BoxConstraints(minHeight: OmiSize.minTap),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(label, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(width: OmiSpacing.xxs),
              OmiGlyph(OmiGlyphs.chevronRight, size: 12, color: OmiColors.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}
