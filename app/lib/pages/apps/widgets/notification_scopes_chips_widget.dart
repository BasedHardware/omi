import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/add_app_provider.dart';

class NotificationScopesChipsWidget extends StatelessWidget {
  const NotificationScopesChipsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      return !provider.isCapabilitySelectedById('proactive_notification')
          ? const SizedBox.shrink()
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Notification Scopes',
                  style: TextStyle(color: Colors.white, fontSize: 16),
                ),
                SizedBox(
                  height: 40,
                  child: Wrap(
                    spacing: 12,
                    children: provider
                        .getNotificationScopes()
                        .map(
                          (scope) => ChoiceChip(
                            label: Text(scope.title),
                            selected: provider.isScopesSelected(scope),
                            showCheckmark: true,
                            backgroundColor: Colors.transparent,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            onSelected: (bool selected) {
                              provider.addOrRemoveScope(scope);
                            },
                          ),
                        )
                        .toList(),
                  ),
                ),
                const SizedBox(
                  height: 30,
                ),
              ],
            );
    });
  }
}
