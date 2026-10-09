import 'package:flutter/material.dart';

import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/entities/entity_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// [items] grouped by project, in display order: a task's workstream is its project when [projects]
/// knows it, otherwise it joins the no-project group (a null id), which always comes last. Projects run
/// largest first, ties by name ignoring case; within one, soonest due first, undated after, then the
/// user's own order. The classic sliver list and the native projection both show exactly this.
List<(String?, List<ActionItemWithMetadata>)> groupTasksByProject(
  List<ActionItemWithMetadata> items,
  Map<String, EntityRef> projects,
) {
  final groups = <String?, List<ActionItemWithMetadata>>{};
  for (final item in items) {
    final id = item.workstreamId;
    groups.putIfAbsent(projects.containsKey(id) ? id : null, () => []).add(item);
  }
  // Within a project: soonest due first, undated after, then the user's own order.
  for (final group in groups.values) {
    group.sort((a, b) {
      final ad = a.dueAt, bd = b.dueAt;
      if (ad != null && bd != null && ad != bd) return ad.compareTo(bd);
      if ((ad == null) != (bd == null)) return ad == null ? 1 : -1;
      return a.sortOrder.compareTo(b.sortOrder);
    });
  }
  final ordered = groups.keys.whereType<String>().toList()
    ..sort((a, b) {
      final bySize = groups[b]!.length.compareTo(groups[a]!.length);
      return bySize != 0 ? bySize : projects[a]!.name.toLowerCase().compareTo(projects[b]!.name.toLowerCase());
    });
  return [
    for (final id in [...ordered, if (groups.containsKey(null)) null]) (id, groups[id]!)
  ];
}

/// Tasks grouped under the project each belongs to (a task's workstream is its project), largest
/// project first and tasks without one last. Each project header opens that project's page.
List<Widget> projectTaskSections({
  required BuildContext context,
  required List<ActionItemWithMetadata> items,
  required Map<String, EntityRef> projects,
  required Widget Function(ActionItemWithMetadata item, List<ActionItemWithMetadata> group) buildRow,
}) {
  return [
    for (final (id, group) in groupTasksByProject(items, projects))
      SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ProjectHeader(project: id == null ? null : projects[id], count: group.length),
              for (final item in group) buildRow(item, group),
            ],
          ),
        ),
      ),
  ];
}

class _ProjectHeader extends StatelessWidget {
  const _ProjectHeader({required this.project, required this.count});

  final EntityRef? project;
  final int count;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final title = project?.name ?? l10n.tasksNoProject;
    final row = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 44),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
        child: Row(
          children: [
            Icon(Icons.folder_outlined, size: 18, color: OmiColors.textSecondary),
            const SizedBox(width: 10),
            Expanded(child: Text(title, style: OmiType.headline, maxLines: 1, overflow: TextOverflow.ellipsis)),
            Text(
              '$count',
              semanticsLabel: l10n.tasksCountLabel(count),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
            if (project != null) ...[
              const SizedBox(width: 4),
              Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary),
            ] else
              const SizedBox(width: 4),
          ],
        ),
      ),
    );
    if (project == null) return Semantics(header: true, child: row);
    return Semantics(
      header: true,
      button: true,
      child: InkWell(
        key: ValueKey('project_header_${project!.entityId}'),
        borderRadius: OmiRadius.mdAll,
        onTap: () => openEntityPage(context, project!),
        child: row,
      ),
    );
  }
}
