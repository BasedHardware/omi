import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/update_app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:provider/provider.dart';

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
                title: const Text(
                  'Keep App Public',
                  style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
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
                          'Make App Public?',
                          'If you make the app public, it can be used by everyone',
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
                          'Make App Private?',
                          'If you make the app private now, it will stop working for everyone and will be visible only to you',
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
                    title: const Text('Update App Details'),
                    leading: const Icon(Icons.edit),
                    onTap: () {
                      routeToPage(context, UpdateAppPage(app: app));
                    },
                  ),
                  ListTile(
                    title: const Text('Delete App'),
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
                          'Delete App',
                          'Are you sure you want to delete this app? This action cannot be undone.',
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
