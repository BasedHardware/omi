import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
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
            context.l10n.whatWouldYouLikeToCreate,
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
              title: Text(context.l10n.createAnApp,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle:
                  Text(context.l10n.createAndShareYourApp, style: TextStyle(color: Colors.white.withOpacity(0.7))),
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
              title: Text(context.l10n.createMyClone,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle:
                  Text(context.l10n.createYourDigitalClone, style: TextStyle(color: Colors.white.withOpacity(0.7))),
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
              leading: const Icon(Icons.cable, color: Colors.white),
              titleAlignment: ListTileTitleAlignment.center,
              title: Text(context.l10n.addMcpServer,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
              subtitle:
                  Text(context.l10n.connectExternalAiTools, style: TextStyle(color: Colors.white.withOpacity(0.7))),
              onTap: () {
                Navigator.pop(context);
                MixpanelManager().pageOpened('Add MCP Server');
                routeToPage(context, const AddMcpServerPage());
              },
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
