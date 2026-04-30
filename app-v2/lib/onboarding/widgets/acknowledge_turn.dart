import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class AcknowledgeTurn extends StatelessWidget {
  final String turnId;
  const AcknowledgeTurn({super.key, required this.turnId});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
      child: SizedBox(
        width: double.infinity,
        child: ElevatedButton(
          onPressed: () => context.read<OnboardingChatProvider>().reportWidgetCapture(context, turnId, true),
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.brandPrimary,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppStyles.radiusPill)),
          ),
          child: Text(l.onboardingAckLetsGo, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
        ),
      ),
    );
  }
}
