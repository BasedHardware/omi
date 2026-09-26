import 'package:flutter/material.dart';

import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// First-run permissions step. Each permission is allowed from its own row; Continue only moves
/// on, whatever the reader allowed (docs/ux-contract.md §15).
class PermissionsWidget extends StatelessWidget {
  final VoidCallback goNext;
  final OnboardingPermissionsSource? source;

  const PermissionsWidget({super.key, required this.goNext, this.source});

  @override
  Widget build(BuildContext context) {
    return OnboardingStep(
      card: OnboardingCard(
        content: [
          OnboardingHeader(title: context.l10n.permissionsFewTitle, subtitle: context.l10n.permissionsFewSubtitle),
          const SizedBox(height: OmiSpacing.lg),
          OnboardingPermissionsPanel(source: source),
          const SizedBox(height: OmiSpacing.md),
          Padding(
            padding: OnboardingCard.textInset,
            child: Text(
              context.l10n.permissionsContinueNote,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.xs),
          OmiButton(
            key: const Key('onboarding_permissions_continue'),
            label: context.l10n.continueButton,
            expand: true,
            onPressed: () {
              OmiHaptics.selection();
              goNext();
            },
          ),
        ],
      ),
    );
  }
}
