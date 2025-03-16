import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/add_app_provider.dart';

class NotificationScopesChipsWidget extends StatelessWidget {
  const NotificationScopesChipsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      return ListView(
        shrinkWrap: true,
        scrollDirection: Axis.horizontal,
        children: [
          provider.getNotificationScopes().isEmpty
              ? const SizedBox.shrink()
              : Wrap(
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
                            borderRadius: BorderRadius.circular(20),
                          ),
                          onSelected: (bool selected) {
                            provider.addOrRemoveScope(scope);
                          },
                        ),
                      )
                      .toList(),
                ),
        ],
      );
    });
  }
}
