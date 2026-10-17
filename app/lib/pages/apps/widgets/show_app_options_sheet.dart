import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// The owner's options for an app: visibility, edit, delete.
///
/// Content for [showAppOptionsSheet], which presents it in the shared sheet shell titled with the
/// app's name.
///
/// With [nativeTitle] it is the native sheet's body: the same rows and handlers in the native
/// presentation, falling back to this content in the shared sheet shell.
class ShowAppOptionsSheet extends StatelessWidget {
  final App app;
  final String? nativeTitle;
  const ShowAppOptionsSheet({super.key, required this.app, this.nativeTitle});

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

  void _manage(BuildContext context) {
    Navigator.pop(context);
    routeToPage(context, UpdateAppPage(app: app));
  }

  Widget _native(BuildContext context, AppProvider provider, String title) {
    final l10n = context.l10n;
    return IosNativeSurface(
      title: title,
      fallback: OmiSheetScaffold(title: title, child: ShowAppOptionsSheet(app: app)),
      toolbar: [
        NativeRow('app_options_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('app_options_visibility', [
          NativeRow('app_keep_public', l10n.keepItemPublic(l10n.itemApp),
              kind: 'toggle',
              value: provider.appPublicToggled,
              action: (value) => _setPublic(context, provider, value as bool)),
        ]),
        NativeSection('app_options_manage', [
          NativeRow('app_manage', l10n.manageApp,
              kind: 'navigation', symbol: 'pencil', action: (_) => _manage(context)),
          NativeRow('app_delete', l10n.deleteItemTitle(l10n.itemApp),
              symbol: 'trash', destructive: true, action: (_) => _delete(context, provider)),
        ]),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<AppProvider>(
      builder: (context, provider, child) {
        if (nativeTitle case final title?) return _native(context, provider, title);
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
                    onTap: () => _manage(context),
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
  return showOmiSheet(
    context: context,
    title: app.name,
    builder: (context) => ShowAppOptionsSheet(app: app),
    nativeBuilder: (context) => ShowAppOptionsSheet(app: app, nativeTitle: app.name),
  );
}
