import 'package:flutter/material.dart';
import 'package:friend_private/pages/apps/add_app.dart';
import 'package:friend_private/pages/persona/add_persona.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';

class CreateOptionsSheet extends StatelessWidget {
  const CreateOptionsSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'What would you like to create?',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: Theme.of(context).colorScheme.onSurface,
                ),
          ),
          const SizedBox(height: 24),
          Card(
            elevation: 0,
            color: Theme.of(context).colorScheme.surfaceVariant.withOpacity(0.5),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: Icon(Icons.apps, color: Colors.white),
              title:
                  Text('Submit an App', style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle: Text('Create and share your app with the community',
                  style: TextStyle(color: Colors.white.withOpacity(0.7))),
              onTap: () {
                Navigator.pop(context);
                MixpanelManager().pageOpened('Submit App');
                routeToPage(context, const AddAppPage());
              },
            ),
          ),
          const SizedBox(height: 12),
          Card(
            elevation: 0,
            color: Theme.of(context).colorScheme.surfaceVariant.withOpacity(0.5),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: Icon(Icons.person_outline, color: Colors.white),
              title:
                  Text('Create Persona', style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle: Text('Create your digital clone for personalized interactions',
                  style: TextStyle(color: Colors.white.withOpacity(0.7))),
              onTap: () {
                Navigator.pop(context);
                MixpanelManager().pageOpened('Create Persona');
                routeToPage(context, const AddPersonaPage());
              },
            ),
          ),
        ],
      ),
    );
  }
}
