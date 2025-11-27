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
          InkWell(
            onTap: () {
              Navigator.pop(context);
              MixpanelManager().pageOpened('Submit App');
              routeToPage(context, const AddAppPage());
            },
            borderRadius: BorderRadius.circular(16),
            child: Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F1F25),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(
                      Icons.apps,
                      color: Colors.white,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 16),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Create an App',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: Colors.black,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Create and share your app',
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.black54,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    color: Colors.black,
                    size: 24,
                  ),
                ],
              ),
            ),
          ),
          // const SizedBox(height: 12),
          // Card(
          //   elevation: 0,
          //   color: Theme.of(context).colorScheme.surfaceVariant.withOpacity(0.5),
          //   shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          //   child: ListTile(
          //     contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          //     leading: const Icon(Icons.person_outline, color: Colors.white),
          //     titleAlignment: ListTileTitleAlignment.center,
          //     title: Text('Create my Clone',
          //         style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white)),
          //     subtitle: Text('Create your digital clone', style: TextStyle(color: Colors.white.withOpacity(0.7))),
          //     onTap: () {
          //       Navigator.pop(context);
          //       MixpanelManager().pageOpened('Create Persona');
          //       // Set routing in provider and navigate to Persona Profile page
          //       Provider.of<PersonaProvider>(context, listen: false).setRouting(PersonaProfileRouting.create_my_clone);
          //       Navigator.of(context).push(
          //         MaterialPageRoute(
          //           builder: (context) => const PersonaProfilePage(),
          //           settings: const RouteSettings(
          //             arguments: 'from_settings',
          //           ),
          //         ),
          //       );
          //       // Provider.of<HomeProvider>(context, listen: false).setIndex(3);
          //       // Provider.of<HomeProvider>(context, listen: false).onSelectedIndexChanged!(3);
          //     },
          //   ),
          // ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
