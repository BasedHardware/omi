import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class ActionsWidget extends StatelessWidget {
  const ActionsWidget({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        if (!provider.isCapabilitySelectedById('external_integration')) {
          return const SizedBox.shrink();
        }

        return Column(
          children: [
            const SizedBox(height: 12),
            Container(
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: BorderRadius.circular(12.0),
              ),
              padding: const EdgeInsets.all(14.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0, bottom: 16.0),
                    child: Text(
                      'Actions',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
                  ListView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: provider.availableActions.length,
                    itemBuilder: (context, index) {
                      final action = provider.availableActions[index];
                      final isSelected = provider.isActionSelected(action);
                      
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8.0),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade800,
                          borderRadius: BorderRadius.circular(8.0),
                        ),
                        child: ListTile(
                          title: Text(
                            action.title ?? action.action,
                            style: const TextStyle(color: Colors.white),
                          ),
                          subtitle: action.description != null 
                            ? Text(
                                action.description!,
                                style: TextStyle(color: Colors.grey.shade400),
                              )
                            : null,
                          trailing: Checkbox(
                            value: isSelected,
                            onChanged: (value) {
                              provider.toggleAction(action);
                            },
                            shape: const CircleBorder(),
                          ),
                        ),
                      );
                    },
                  ),
                  if (provider.selectedActions.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: Text(
                        'Select actions your app can perform',
                        style: TextStyle(color: Colors.grey.shade500),
                      ),
                    ),
                  const SizedBox(height: 8),
                  GestureDetector(
                    onTap: () {
                      launchUrl(Uri.parse('https://omi.me/apps/actions'));
                    },
                    child: Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: Text(
                        'Learn more about actions',
                        style: TextStyle(
                          color: Colors.blue.shade300,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}
