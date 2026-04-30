import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';

/// The text-input turn doesn't render anything in the chat list — capture
/// happens via the bottom prompt input. This widget is a small spacer that
/// hints "type below".
class TextInputTurn extends StatelessWidget {
  final String turnId;
  const TextInputTurn({super.key, required this.turnId});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS, horizontal: AppStyles.spacingS),
      child: Row(
        children: [
          Icon(Icons.south, size: 16, color: AppColors.textTertiary.withValues(alpha: 0.6)),
          const SizedBox(width: 8),
          Text(
            'Reply below to continue',
            style: TextStyle(fontSize: 13, color: AppColors.textTertiary.withValues(alpha: 0.7)),
          ),
        ],
      ),
    );
  }
}
