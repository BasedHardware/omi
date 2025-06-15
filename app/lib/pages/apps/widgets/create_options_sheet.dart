import 'package:flutter/material.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';

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
                  fontWeight: FontWeight.w400,
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
              titleAlignment: ListTileTitleAlignment.center,
              leading: const Icon(Icons.apps, color: Colors.white),
              title:
                  Text('Create an App', style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle: Text('Create and share your app', style: TextStyle(color: Colors.white.withOpacity(0.7))),
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
              leading: const Icon(Icons.person_outline, color: Colors.white),
              titleAlignment: ListTileTitleAlignment.center,
              title: Text('Create my Clone',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle: Text('Create your digital clone', style: TextStyle(color: Colors.white.withOpacity(0.7))),
              onTap: () {
                Navigator.pop(context);
                MixpanelManager().pageOpened('Create Persona');
                // Set routing in provider and navigate to Persona Profile page
                Provider.of<PersonaProvider>(context, listen: false).setRouting(PersonaProfileRouting.create_my_clone);
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const PersonaProfilePage(),
                    settings: const RouteSettings(
                      arguments: 'from_settings',
                    ),
                  ),
                );
                // Provider.of<HomeProvider>(context, listen: false).setIndex(3);
                // Provider.of<HomeProvider>(context, listen: false).onSelectedIndexChanged!(3);
              },
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
