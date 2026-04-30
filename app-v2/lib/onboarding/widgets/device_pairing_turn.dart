import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Phase 1 stub. Real BLE pairing arrives in a later phase together with the
/// native Pigeon bridge. For now we offer "pair later" / "skip for now".
class DevicePairingTurn extends StatelessWidget {
  final String turnId;
  const DevicePairingTurn({super.key, required this.turnId});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final provider = context.read<OnboardingChatProvider>();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          _StubChip(
            label: l.onboardingChipPairLater,
            onTap: () => provider.reportWidgetCapture(context, turnId, 'connect later'),
          ),
          _StubChip(
            label: l.onboardingChipSkipForNow,
            onTap: () => provider.skipCurrent(context),
            secondary: true,
          ),
        ],
      ),
    );
  }
}

class _StubChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  final bool secondary;
  const _StubChip({required this.label, required this.onTap, this.secondary = false});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppStyles.radiusPill),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: secondary ? Colors.transparent : AppColors.backgroundSecondary,
          borderRadius: BorderRadius.circular(AppStyles.radiusPill),
          border: Border.all(color: Colors.white.withValues(alpha: secondary ? 0.18 : 0.08)),
        ),
        child: Text(label,
            style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: secondary ? AppColors.textTertiary : AppColors.textPrimary)),
      ),
    );
  }
}
