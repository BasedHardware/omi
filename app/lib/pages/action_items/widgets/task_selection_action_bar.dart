import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Bottom-anchored selection action bar for the action items page.
/// Same visual language as `MergeActionBar` for the conversations page —
/// dark sheet with rounded top corners, slide-up animation, single primary
/// pill action.
///
/// Mounted at the home page's outer Stack so it paints above the bottom
/// nav bar (mirrors `MergeActionBar`); in the native shell the Tasks page
/// mounts it over its own Flutter fallback instead. Selection state lives in
/// `ActionItemsProvider`. Bulk delete confirms (it cannot be undone); single
/// deletes elsewhere are immediate with Undo.
class TaskSelectionActionBar extends StatefulWidget {
  const TaskSelectionActionBar({super.key});

  @override
  State<TaskSelectionActionBar> createState() => _TaskSelectionActionBarState();
}

class _TaskSelectionActionBarState extends State<TaskSelectionActionBar> with SingleTickerProviderStateMixin {
  late final AnimationController _animationController;
  late final Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(vsync: this, duration: OmiMotion.standardDuration);
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _animationController, curve: Curves.easeOutCubic));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, _) {
        final isActive = provider.isSelectionMode;
        final taskCount = provider.selectedCount;
        final canExport = taskCount > 0;

        if (isActive) {
          _animationController.forward();
        } else {
          _animationController.reverse();
        }

        return IgnorePointer(
          ignoring: !isActive,
          child: SlideTransition(
            position: _slideAnimation,
            child: Container(
              decoration: BoxDecoration(
                color: OmiColors.surface1,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(OmiRadius.lg)),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 20, offset: const Offset(0, -4)),
                ],
              ),
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 16, 20, 16),
                  child: Row(
                    children: [
                      OmiButton.tertiary(
                        label: context.l10n.cancel,
                        onPressed: () {
                          OmiHaptics.light();
                          provider.endSelection();
                        },
                      ),
                      const Spacer(),
                      // Destructive secondary: bulk delete. Icon-only on purpose so Export stays
                      // the visual primary; the count lives on that button.
                      OmiIconButton(
                        icon: const Icon(Icons.delete_outline_rounded),
                        label: context.l10n.deleteSelected,
                        isDestructive: true,
                        onPressed: canExport ? () => confirmAndDeleteSelectedTasks(context, provider) : null,
                      ),
                      const SizedBox(width: 8),
                      OmiButton(
                        icon: Icons.ios_share_rounded,
                        size: OmiButtonSize.compact,
                        label: canExport ? '${context.l10n.exportButton} · $taskCount' : context.l10n.exportButton,
                        onPressed: canExport ? () => exportSelectedTasks(context, provider) : null,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Exports the selected tasks to the connected task app. Users connect one task app at a time; with
/// none connected, the error offers Connect, which opens the task integrations settings. The provider
/// skips already-exported tasks, reports progress, success or a partial result, and exits selection.
Future<void> exportSelectedTasks(BuildContext context, ActionItemsProvider provider) async {
  OmiHaptics.light();

  final integrations = Provider.of<TaskIntegrationProvider>(context, listen: false);
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

  await provider.bulkExportSelected(context, connected.first);
}

/// Bulk delete cannot be undone: confirm every time (docs/ux-contract.md §4). A failed delete puts
/// the tasks and the selection back and says so (the provider owns that rollback).
Future<void> confirmAndDeleteSelectedTasks(BuildContext context, ActionItemsProvider provider) async {
  OmiHaptics.light();
  final l10n = context.l10n;
  final confirmed = await showOmiConfirm(
    context,
    title: l10n.deleteTasksTitle(provider.selectedCount),
    message: l10n.thisActionCannotBeUndone,
    confirmLabel: l10n.delete,
    destructive: true,
  );
  if (!confirmed || !context.mounted) return;
  await provider.deleteSelectedItems(context: context);
}
