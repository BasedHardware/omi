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
/// Used by the row's long-press menu and by the task page.
Future<void> exportTaskToConnectedApp(BuildContext context, ActionItemWithMetadata item) async {
  OmiHaptics.light();
  final integrations = context.read<TaskIntegrationProvider>();
  final connected = TaskIntegrationApp.values.where(integrations.isAppConnected).toList(growable: false);
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
