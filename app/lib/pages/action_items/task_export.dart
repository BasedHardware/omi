import 'package:flutter/widgets.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Exports one task to the connected task app, the way the selection bar exports several: the same
/// provider path, so the connect nudge, skip-if-exported and the outcome snackbar behave the same.
/// Used by the row's long-press menu.
Future<void> exportTaskToConnectedApp(BuildContext context, ActionItemWithMetadata item) async {
  OmiHaptics.light();
  final integrations = context.read<TaskIntegrationProvider>();
  // Opened straight onto a task, the first integrations load may still be in flight.
  await integrations.ensureLoaded();
  if (!context.mounted) return;
  // The app chosen in Task Integrations wins; any other connected app is only a fallback.
  final connected = [
    if (integrations.isAppConnected(integrations.selectedApp)) integrations.selectedApp,
    ...TaskIntegrationApp.values.where((app) => app != integrations.selectedApp && integrations.isAppConnected(app)),
  ];
  if (connected.isEmpty) {
    OmiFeedback.error(
      context,
      context.l10n.connectTaskAppToExport,
      actionLabel: context.l10n.connectAction,
      onAction: () => routeToPage(context, const TaskIntegrationsPage()),
    );
    return;
  }
  await context.read<ActionItemsProvider>().exportItems(context, [item], connected.first);
}
