import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:url_launcher/url_launcher.dart';

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
                    'Import',
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                  ),
                ),
                // List of action items
                Column(
                  children: [
                    ...provider.getActionTypes().map((actionType) {
                      final isSelected = provider.actions.any((action) => action['action'] == actionType.id);

                      return Container(
                        margin: const EdgeInsets.only(bottom: 8.0),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade800,
                          borderRadius: BorderRadius.circular(8.0),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Action selector
                            ListTile(
                              title: Text(actionType.title),
                              subtitle: Text('Allow this app to ${actionType.title.toLowerCase()}'),
                              trailing: Switch(
                                value: isSelected,
                                onChanged: (value) {
                                  if (value) {
                                    provider.addSpecificAction(actionType.id);
                                  } else {
                                    provider.removeActionByType(actionType.id);
                                  }
                                },
                              ),
                            ),

                            // Description
                            if (isSelected)
                              Padding(
                                padding: const EdgeInsets.fromLTRB(16.0, 0, 16.0, 16.0),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      actionType.id == 'create_conversation'
                                          ? 'Extend user conversations by making a POST request to the OMI System.'
                                          : 'Enable this action for your app.',
                                      style: TextStyle(
                                        color: Colors.grey.shade400,
                                        fontSize: 14,
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    GestureDetector(
                                      onTap: () {
                                        if (actionType.docUrl != null) {
                                          launchUrl(Uri.parse(actionType.docUrl!));
                                        } else {
                                          launchUrl(Uri.parse('https://docs.omi.me/actions/${actionType.id}'));
                                        }
                                      },
                                      child: Text(
                                        'Learn more.',
                                        style: TextStyle(
                                          color: Colors.blue.shade300,
                                          fontSize: 14,
                                          decoration: TextDecoration.underline,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      );
                    }).toList(),

                    // Add button for future actions
                    if (provider.getActionTypes().length > 1)
                      Padding(
                        padding: const EdgeInsets.only(top: 8.0),
                        child: Text(
                          'Select multiple actions as needed for your app.',
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 12,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
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
