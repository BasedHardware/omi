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
          Text(context.l10n.grantPermissions, style: OmiType.title1, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            context.l10n.permissionsSetupDescription,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.xl),
          OnboardingPermissionsPanel(source: source),
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
