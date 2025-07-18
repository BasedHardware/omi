import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_choice_chip.dart';

import '../../../../pages/apps/providers/add_app_provider.dart';

class DesktopCapabilitiesChipsWidget extends StatelessWidget {
  const DesktopCapabilitiesChipsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      if (provider.capabilities.isEmpty) {
        return Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  FontAwesomeIcons.cogs,
                  color: ResponsiveHelper.textTertiary,
                  size: 24,
                ),
                SizedBox(height: 8),
                Text(
                  'Loading capabilities...',
                  style: TextStyle(
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
        children: provider.capabilities.map((cap) {
          final selected = provider.isCapabilitySelected(cap);
          return OmiChoiceChip(
            label: cap.title,
            selected: selected,
            onTap: () => provider.addOrRemoveCapability(cap),
          );
        }).toList(),
      );
    });
  }
}
