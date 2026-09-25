import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// The owner's options for an app: visibility, edit, delete.
///
/// Content for [showAppOptionsSheet], which presents it in the shared sheet shell titled with the
/// app's name.
class ShowAppOptionsSheet extends StatelessWidget {
  final App app;
  const ShowAppOptionsSheet({super.key, required this.app});

  Future<void> _setPublic(BuildContext context, AppProvider provider, bool value) async {
    final l10n = context.l10n;
    final item = l10n.itemApp;
    final confirmed = await showOmiConfirm(
      context,
      title: value ? l10n.makeItemPublicQuestion(item) : l10n.makeItemPrivateQuestion(item),
      message: value
          ? l10n.makeItemPublicExplanation(item.toLowerCase())
          : l10n.makeItemPrivateExplanation(item.toLowerCase()),
      confirmLabel: value ? l10n.makePublic : l10n.makePrivate,
    );
    if (!confirmed) return;
    await provider.toggleAppPublic(app.id, value);
    if (context.mounted) Navigator.of(context).pop();
  }

  Future<void> _delete(BuildContext context, AppProvider provider) async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.deleteItemQuestion(l10n.itemApp),
      message: l10n.deleteItemConfirmation(l10n.itemApp),
      confirmLabel: l10n.delete,
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    provider.deleteApp(app.id);
    // Close the sheet and the deleted app's page.
    Navigator.of(context)
      ..pop()
      ..pop();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<AppProvider>(
      builder: (context, provider, child) {
        return Padding(
          padding: const EdgeInsets.only(bottom: OmiSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              OmiSettingsGroup(
                children: [
                  OmiSettingsRow.toggle(
                    title: l10n.keepItemPublic(l10n.itemApp),
                    value: provider.appPublicToggled,
                    onChanged: (value) => _setPublic(context, provider, value),
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.md),
              OmiSettingsGroup(
                children: [
                  OmiSettingsRow(
                    leading: const Icon(Icons.edit),
                    title: l10n.manageApp,
                    onTap: () {
                      Navigator.pop(context);
                      routeToPage(context, UpdateAppPage(app: app));
                    },
                  ),
                  OmiSettingsRow(
                    leading: const Icon(Icons.delete_outline),
                    title: l10n.deleteItemTitle(l10n.itemApp),
                    isDestructive: true,
                    onTap: () => _delete(context, provider),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Shows the owner's options for [app] in the shared sheet shell.
Future<void> showAppOptionsSheet(BuildContext context, App app) {
  return showOmiSheet(context: context, title: app.name, builder: (context) => ShowAppOptionsSheet(app: app));
}
