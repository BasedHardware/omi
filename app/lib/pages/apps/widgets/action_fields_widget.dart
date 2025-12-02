import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';

class ActionFieldsWidget extends StatelessWidget {
  const ActionFieldsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        // Only show if external integration is selected and actions are available
        if (!provider.isCapabilitySelectedById('external_integration') || provider.getActionTypes().isEmpty) {
          return const SizedBox.shrink();
        }

        return Column(
          children: [
            const SizedBox(height: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(left: 8.0, bottom: 12.0),
                  child: Text(
                    'Permissions',
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                  ),
                ),
                // List of action items
                Column(
                  children: [
                    ...provider.getActionTypes().map((actionType) {
                      final isSelected = provider.actions.any((action) => action['action'] == actionType.id);

                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12.0),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                actionType.title,
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w500,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                            Switch(
                              value: isSelected,
                              onChanged: (value) {
                                if (value) {
                                  provider.addSpecificAction(actionType.id);
                                } else {
                                  provider.removeActionByType(actionType.id);
                                }
                              },
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  ],
                ),
              ],
            ),
          ],
        );
      },
    );
  }
}
