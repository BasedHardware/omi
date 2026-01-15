import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import '../providers/add_app_provider.dart';

class NotificationScopesChipsWidget extends StatelessWidget {
  const NotificationScopesChipsWidget({super.key});

  Widget _buildScopeButton(NotificationScope scope, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 44,
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.grey.withOpacity(0.3),
            width: 1,
          ),
        ),
        child: Center(
          child: Text(
            scope.title,
            style: TextStyle(
              color: isSelected ? Colors.black : Colors.white,
              fontSize: 14,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      if (provider.getNotificationScopes().isEmpty) {
        return const SizedBox.shrink();
      }

      final scopes = provider.getNotificationScopes();
      final rows = <Widget>[];

      for (int i = 0; i < scopes.length; i += 2) {
        rows.add(
          Padding(
            padding: EdgeInsets.only(left: 8.0, bottom: i + 2 < scopes.length ? 10 : 0),
            child: Row(
              children: [
                Expanded(
                  child: _buildScopeButton(scopes[i], provider.isScopesSelected(scopes[i]), () {
                    provider.addOrRemoveScope(scopes[i]);
                  }),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: i + 1 < scopes.length
                      ? _buildScopeButton(scopes[i + 1], provider.isScopesSelected(scopes[i + 1]), () {
                          provider.addOrRemoveScope(scopes[i + 1]);
                        })
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        );
      }

      return Column(children: rows);
    });
  }
}
