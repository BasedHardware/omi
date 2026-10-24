import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Tasks' one page action: a bare "⋯" beside the Home / Tasks switcher. It holds selection,
/// grouping, the completed view and export, so the shell header stays the same on both pages.
class TasksMoreMenu extends StatelessWidget {
  const TasksMoreMenu({super.key});

  static const buttonKey = ValueKey('tasks_more_button');

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ActionItemsProvider>();
    final l10n = context.l10n;
    final showingCompleted = provider.showCompletedView;
    final groupByProject = provider.groupByProject;
    final hasItems = provider.actionItems.isNotEmpty;
    final allSelected = hasItems && provider.selectedCount == provider.actionItems.length;

    return PullDownButton(
      itemBuilder: (context) => [
        if (hasItems) ...[
          PullDownMenuItem(
            title: l10n.selectActionItems,
            iconWidget: const Icon(Icons.check_box_outlined, size: 18),
            onTap: () {
              OmiHaptics.light();
              primaryFocus?.unfocus();
              provider.startSelection();
            },
          ),
          PullDownMenuItem(
            title: allSelected ? l10n.deselectAllTasksMenu : l10n.selectAllTasksMenu,
            iconWidget: Icon(allSelected ? Icons.deselect_rounded : Icons.select_all_rounded, size: 18),
            onTap: () {
              OmiHaptics.light();
              primaryFocus?.unfocus();
              if (allSelected) {
                provider.clearSelection();
              } else {
                if (!provider.isSelectionMode) provider.startSelection();
                provider.selectAllItems();
              }
            },
          ),
        ],
        if (context.read<ReviewProvider?>()?.isOn ?? false)
          PullDownMenuItem(
            title: groupByProject ? l10n.tasksGroupByDate : l10n.tasksGroupByProject,
            iconWidget: Icon(groupByProject ? Icons.event_outlined : Icons.folder_outlined, size: 18),
            onTap: () {
              OmiHaptics.light();
              final review = context.read<ReviewProvider?>();
              if (!groupByProject && review != null && review.projects.isEmpty) review.loadProjects();
              provider.toggleGroupByProject();
            },
          ),
        PullDownMenuItem(
          title: showingCompleted ? l10n.hideCompletedTasks : l10n.showCompletedTasks,
          iconWidget: Icon(showingCompleted ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 18),
          onTap: () {
            OmiHaptics.light();
            provider.toggleShowCompletedView();
          },
        ),
        PullDownMenuItem(
          title: l10n.taskIntegrations,
          iconWidget: const Icon(Icons.ios_share_rounded, size: 18),
          onTap: () {
            PlatformManager.instance.analytics.exportTasksBannerClicked();
            routeToPage(context, const TaskIntegrationsPage());
          },
        ),
      ],
      buttonBuilder: (context, showMenu) => OmiIconButton(
        key: buttonKey,
        icon: const Icon(Icons.more_horiz_rounded),
        label: l10n.moreOptions,
        color: OmiColors.textSecondary,
        onPressed: () {
          OmiHaptics.selection();
          showMenu();
        },
      ),
    );
  }
}
