import 'package:flutter/material.dart';

import 'package:omi/pages/phone_calls/phone_setup_number_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class PhoneSetupIntroPage extends StatelessWidget {
  const PhoneSetupIntroPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton()),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
          child: Column(
            children: [
              const SizedBox(height: 40),
              // Hero icon
              const ExcludeSemantics(
                child: SizedBox(
                  width: 80,
                  height: 80,
                  child: DecoratedBox(
                    decoration: BoxDecoration(shape: BoxShape.circle, color: OmiColors.surface1),
                    child: Icon(Icons.phone, color: OmiColors.textPrimary, size: 36),
                  ),
                ),
              ),
              const SizedBox(height: OmiSpacing.xl),
              Semantics(
                header: true,
                child: Text(context.l10n.phoneCallsWithOmi, style: OmiType.title1, textAlign: TextAlign.center),
              ),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                context.l10n.phoneCallsSubtitle,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              // Step rows
              _StepRow(
                icon: Icons.phone_outlined,
                title: context.l10n.phoneSetupStep1Title,
                subtitle: context.l10n.phoneSetupStep1Subtitle,
              ),
              const SizedBox(height: OmiSpacing.md),
              _StepRow(
                icon: Icons.dialpad,
                title: context.l10n.phoneSetupStep2Title,
                subtitle: context.l10n.phoneSetupStep2Subtitle,
              ),
              const SizedBox(height: OmiSpacing.md),
              _StepRow(
                icon: Icons.people_outline,
                title: context.l10n.phoneSetupStep3Title,
                subtitle: context.l10n.phoneSetupStep3Subtitle,
              ),
              const Spacer(),
              OmiButton(
                label: context.l10n.phoneGetStarted,
                expand: true,
                onPressed: () {
                  OmiHaptics.medium();
                  routeToPage(context, const PhoneSetupNumberPage());
                },
              ),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                context.l10n.callRecordingConsentDisclaimer,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: OmiSpacing.md),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const _StepRow({required this.icon, required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        ExcludeSemantics(
          child: Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            child: Icon(icon, color: OmiColors.textPrimary, size: 20),
          ),
        ),
        const SizedBox(width: OmiSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
              const SizedBox(height: 2),
              Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
        ),
      ],
    );
  }
}
