import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/ai_interjection_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AiInterjectionIndicator extends StatelessWidget {
  const AiInterjectionIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AiInterjectionProvider>(
      builder: (context, provider, child) {
        if (!provider.enabled) return const SizedBox.shrink();

        return Container(
          key: const Key('ai_interjection_indicator'),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: provider.isInterjecting
                ? Colors.green.withValues(alpha: 0.15)
                : Colors.grey.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: provider.isInterjecting ? Colors.green : Colors.grey,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                provider.isInterjecting ? context.l10n.aiThinking : context.l10n.aiListening,
                style: TextStyle(
                  color: provider.isInterjecting ? Colors.green : Colors.grey,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
