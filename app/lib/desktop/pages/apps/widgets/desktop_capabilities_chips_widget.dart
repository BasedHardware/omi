import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

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
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  FontAwesomeIcons.cogs,
                  color: ResponsiveHelper.textTertiary,
                  size: 24,
                ),
                const SizedBox(height: 8),
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
        children: provider.capabilities.map((capability) {
          final isSelected = provider.isCapabilitySelected(capability);

          return Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => provider.addOrRemoveCapability(capability),
              borderRadius: BorderRadius.circular(16),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: isSelected ? ResponsiveHelper.purplePrimary.withOpacity(0.15) : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: isSelected ? ResponsiveHelper.purplePrimary.withOpacity(0.4) : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                    width: 1,
                  ),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          ),
                        ]
                      : [],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Check icon for selected state
                    if (isSelected) ...[
                      Icon(
                        FontAwesomeIcons.check,
                        color: ResponsiveHelper.purplePrimary,
                        size: 14,
                      ),
                      const SizedBox(width: 8),
                    ],

                    // Capability title
                    Text(
                      capability.title,
                      style: TextStyle(
                        color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textPrimary,
                        fontSize: 14,
                        fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }).toList(),
      );
    });
  }
}
