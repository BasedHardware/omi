import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
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
      child: Consumer<AppProvider>(
        builder: (context, provider, child) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                title: Text(app.name, style: Theme.of(context).textTheme.labelLarge),
                leading: const Icon(Icons.apps),
                trailing: IconButton(
                  icon: const Icon(Icons.cancel_outlined),
                  onPressed: () {
                    Navigator.of(context).pop(true);
                  },
                ),
              ),
              Card(
                shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                child: ListTile(
                  title: Text(
                    context.l10n.keepItemPublic(context.l10n.itemApp),
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
                            context.l10n.makeItemPublicQuestion(context.l10n.itemApp),
                            context.l10n.makeItemPublicExplanation(context.l10n.itemApp.toLowerCase()),
                            okButtonText: context.l10n.confirm,
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
                            context.l10n.makeItemPrivateQuestion(context.l10n.itemApp),
                            context.l10n.makeItemPrivateExplanation(context.l10n.itemApp.toLowerCase()),
                            okButtonText: context.l10n.confirm,
                          ),
                        );
                      }
                    },
                  ),
                ),
              ),
              Card(
                shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                child: Column(
                  children: [
                    ListTile(
                      title: Text(context.l10n.manageApp),
                      leading: const Icon(Icons.edit),
                      onTap: () {
                        Navigator.pop(context);
                        routeToPage(context, UpdateAppPage(app: app));
                      },
                    ),
                    ListTile(
                      title: Text(context.l10n.deleteItemTitle(context.l10n.itemApp)),
                      leading: const Icon(Icons.delete),
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
                            context.l10n.deleteItemQuestion(context.l10n.itemApp),
                            context.l10n.deleteItemConfirmation(context.l10n.itemApp),
                            okButtonText: context.l10n.confirm,
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
        },
      ),
    );
  }
}
