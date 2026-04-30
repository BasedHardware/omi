import 'package:flutter/material.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class ComingSoonStub extends StatelessWidget {
  final String tabLabel;
  final IconData icon;
  const ComingSoonStub({super.key, required this.tabLabel, required this.icon});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppStyles.spacingXL),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 56, color: AppColors.textQuaternary),
            const SizedBox(height: 16),
            Text(
              l.shellComingSoonTitle(tabLabel),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
            ),
            const SizedBox(height: 8),
            Text(
              l.shellComingSoonBody,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14, color: AppColors.textTertiary, height: 1.4),
            ),
          ],
        ),
      ),
    );
  }
}
