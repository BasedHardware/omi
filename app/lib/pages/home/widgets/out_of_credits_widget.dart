import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class OutOfCreditsWidget extends StatelessWidget {
  const OutOfCreditsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<UsageProvider>(
      builder: (context, usageProvider, child) {
        if (!usageProvider.isOutOfCredits) {
          return const SizedBox.shrink();
        }

        return Container(
          color: const Color(0xFF1F1F25),
          padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Text(
                  context.l10n.monthlyLimitReached,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 12),
              TextButton(
                onPressed: () {
                  MixpanelManager().paywallOpened('Out of Credits Banner');
                  routeToPage(context, const UsagePage());
                },
                child: Text(
                  context.l10n.checkUsage,
                  style: const TextStyle(color: Color(0xFFC4B5FD), fontWeight: FontWeight.bold, fontSize: 13),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
