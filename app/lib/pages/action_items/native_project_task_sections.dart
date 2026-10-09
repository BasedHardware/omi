import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/entities/entity_page.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'project_task_sections.dart';

/// The native section of the tasks without a known project; never collides with a project's id.
const nativeNoProjectSectionId = 'project_none';
const _projectSectionPrefix = 'project:';

/// The native Tasks sections while grouping by project: [groupTasksByProject] keyed by section id, in
/// the classic order, so both presentations always list the same groups and rows.
/// [categories] are the date buckets the classic list flattens; the projects are [ReviewProvider]'s.
Map<String, List<ActionItemWithMetadata>> nativeProjectTaskGroups(
  BuildContext context,
  Iterable<List<ActionItemWithMetadata>> categories,
) {
  final projects = context.read<ReviewProvider?>()?.projects ?? const {};
  return {
    for (final (id, group) in groupTasksByProject(categories.expand((items) => items).toList(), projects))
      id == null ? nativeNoProjectSectionId : '$_projectSectionPrefix$id': group,
  };
}

/// Whether [sectionId] came from [nativeProjectTaskGroups].
bool isNativeProjectSection(String sectionId) =>
    sectionId == nativeNoProjectSectionId || sectionId.startsWith(_projectSectionPrefix);

/// One project group: titled with the project's name (or "No project"), its count as the footer, and a
/// leading row that opens the project's page like the classic header. The no-project group opens nothing.
/// While [reorder] is set the section holds only its tasks, so the permutation is exactly [rows].
NativeSection nativeProjectTaskSection(
  BuildContext context,
  String sectionId,
  List<NativeRow> rows, {
  NativeAction? reorder,
}) {
  final l10n = context.l10n;
  final projects = context.read<ReviewProvider?>()?.projects ?? const <String, EntityRef>{};
  final project =
      sectionId.startsWith(_projectSectionPrefix) ? projects[sectionId.substring(_projectSectionPrefix.length)] : null;
  return NativeSection(
    sectionId,
    [
      if (project != null && reorder == null)
        NativeRow('project_open:${project.entityId}', project.name,
            // Fire and forget: the command completes now, not when the project page closes.
            kind: 'navigation',
            symbol: 'folder',
            action: (_) => unawaited(openEntityPage(context, project))),
      ...rows,
    ],
    title: project?.name ?? l10n.tasksNoProject,
    footer: l10n.tasksCountLabel(rows.length),
    reorder: reorder,
  );
}
