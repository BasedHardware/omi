import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';

class ShowAppOptionsSheet extends StatelessWidget {
  final App app;
  const ShowAppOptionsSheet({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      child: Consumer<AppProvider>(builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: Text(
                app.name,
                style: Theme.of(context).textTheme.labelLarge,
              ),
              leading: const Icon(Icons.apps),
              trailing: IconButton(
                icon: const Icon(Icons.cancel_outlined),
                onPressed: () {
                  Navigator.of(context).pop(true);
                },
              ),
            ),
            Card(
              shape: const RoundedRectangleBorder(
                borderRadius: BorderRadius.all(Radius.circular(8)),
              ),
              child: ListTile(
                title: Text(
                  app.isNotPersona() ? 'Keep App Public' : 'Keep Persona Public',
                  style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                ),
                trailing: Switch(
                  value: provider.appPublicToggled,
                  onChanged: (value) {
                    if (value) {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            provider.toggleAppPublic(app.id, value);
                            Navigator.pop(context);
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          app.isNotPersona() ? 'Make App Public?' : 'Make Persona Public?',
                          'If you make the ${app.isNotPersona() ? 'app' : 'persona'} public, it can be used by everyone',
                          okButtonText: 'Confirm',
                        ),
                      );
                    } else {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            provider.toggleAppPublic(app.id, value);
                            Navigator.pop(context);
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          app.isNotPersona() ? 'Make App Private?' : 'Make Persona Private?',
                          'If you make the ${app.isNotPersona() ? 'app' : 'persona'} private now, it will stop working for everyone and will be visible only to you',
                          okButtonText: 'Confirm',
                        ),
                      );
                    }
                  },
                ),
              ),
            ),
            Card(
              shape: const RoundedRectangleBorder(
                borderRadius: BorderRadius.all(Radius.circular(8)),
              ),
              child: Column(
                children: [
                  ListTile(
                    title: Text(app.isNotPersona() ? 'Manage App' : 'Update Persona Details'),
                    leading: const Icon(Icons.edit),
                    onTap: () {
                      Navigator.pop(context);
                      if (app.isNotPersona()) {
                        routeToPage(context, UpdateAppPage(app: app));
                      } else {
                        Navigator.pop(context);
                        // Set routing in provider and navigate to Persona Profile page
                        Provider.of<PersonaProvider>(context, listen: false)
                            .setRouting(PersonaProfileRouting.create_my_clone);
                        Provider.of<HomeProvider>(context, listen: false).setIndex(3);
                        Provider.of<HomeProvider>(context, listen: false).onSelectedIndexChanged!(3);
                      }
                    },
                  ),
                  ListTile(
                    title: Text('Delete ${app.isNotPersona() ? 'App' : 'Persona'}'),
                    leading: const Icon(
                      Icons.delete,
                    ),
                    onTap: () {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            provider.deleteApp(app.id);
                            Navigator.pop(context);
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          'Delete ${app.isNotPersona() ? 'App' : 'Persona'}?',
                          'Are you sure you want to delete this ${app.isNotPersona() ? 'App' : 'Persona'}? This action cannot be undone.',
                          okButtonText: 'Confirm',
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 40),
          ],
        );
      }),
    );
  }
}
