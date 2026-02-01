import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/ui/atoms/omi_choice_chip.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';

class DesktopNotificationScopesChipsWidget extends StatelessWidget {
  const DesktopNotificationScopesChipsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      final scopes = provider.getNotificationScopes();

      if (scopes.isEmpty) {
        return Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  FontAwesomeIcons.bell,
                  color: ResponsiveHelper.textTertiary,
                  size: 24,
                ),
                const SizedBox(height: 8),
                Text(
                  context.l10n.noNotificationScopesAvailable,
                  style: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        );
      }

      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: scopes.map((scope) {
          final isSelected = provider.isScopesSelected(scope);
          return OmiChoiceChip(
            label: scope.getLocalizedTitle(context),
            selected: isSelected,
            onTap: () => provider.addOrRemoveScope(scope),
          );
        }).toList(),
      );
    });
  }
}
