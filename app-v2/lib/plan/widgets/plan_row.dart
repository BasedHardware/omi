import 'package:flutter/material.dart';

import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';
import 'package:nooto_v2/widgets/jira_chip.dart';

/// One commitment row in the Plan screen. Two visual lines:
///   1. Top: checkbox + description (+ optional inline Jira chip on narrow
///      widths via Wrap) + trailing due-date label.
///   2. Bottom: a metadata strip ("In Review · PROJ · 4d at status · P1" for
///      Jira items; "From conversation · 2d ago" for transcript items). The
///      strip is suppressed entirely when there's nothing useful to say.
///
/// Per DESIGN.md "one accent color" rule, the metadata strip is text-only —
/// status_type drives logic (which transitions are available) but never a
/// visual channel. The status name itself carries the meaning.
///
/// Tap on the checkbox marks complete (optimistic, rolls back on server
/// error). The full row's tap target stays ≥44pt by virtue of vertical
/// padding + checkbox height + metadata strip when present.
class PlanRow extends StatelessWidget {
  const PlanRow({
    super.key,
    required this.item,
    required this.onToggle,
    this.onProjectTap,
    this.sectionHasMixedSources = true,
  });

  final ActionItem item;
  final Future<void> Function() onToggle;

  /// Tapped when the project-key portion of an inline Jira chip is tapped.
  /// Plumbed through to [JiraChip.onProjectTap]. When null, project taps
  /// fall through to the default Safari-launch behavior.
  final VoidCallback? onProjectTap;

  /// True when the visible group containing this row has at least one
  /// Jira-sourced item AND at least one transcript-sourced item. When
  /// false, the metadata strip skips the "From conversation · " prefix on
  /// transcript rows (just renders the relative age) — six rows in a row
  /// all narrating the same source is noise.
  final bool sectionHasMixedSources;

  @override
  Widget build(BuildContext context) {
    final trailing = _trailingLabel(item);
    final hasChip = item.externalSource != null;
    final metaSegments = _metaSegments(item, sectionHasMixedSources: sectionHasMixedSources);
    return InkWell(
      onTap: onToggle,
      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: AppStyles.spacingM),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: _Checkbox(checked: item.completed),
                ),
                const SizedBox(width: AppStyles.spacingM),
                // Wrap so a long description + chip on a narrow viewport flows
                // the chip below the text rather than clipping the description.
                // Single-line description rows still render exactly as before
                // because Wrap collapses to one line when content fits.
                Expanded(
                  child: hasChip
                      ? Wrap(
                          spacing: AppStyles.spacingS,
                          runSpacing: AppStyles.spacingXS,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(item.description, style: _descriptionStyle(item.completed)),
                            JiraChip.forSource(item.externalSource, onProjectTap: onProjectTap),
                          ],
                        )
                      : Text(
                          item.description,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: _descriptionStyle(item.completed),
                        ),
                ),
                if (trailing != null) ...[
                  const SizedBox(width: AppStyles.spacingS),
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      trailing,
                      style: const TextStyle(fontSize: 12, color: AppColors.textTertiary, fontWeight: FontWeight.w500),
                    ),
                  ),
                ],
              ],
            ),
            if (metaSegments.isNotEmpty) ...[
              const SizedBox(height: AppStyles.spacingXS),
              Padding(
                // Align under the description, not the checkbox: 20 (checkbox
                // width) + spacingM (gap) keeps the strip flush with the title.
                padding: const EdgeInsets.only(left: 20 + AppStyles.spacingM),
                child: _MetaStrip(segments: metaSegments),
              ),
            ],
          ],
        ),
      ),
    );
  }

  static TextStyle _descriptionStyle(bool completed) => TextStyle(
    fontSize: 15,
    color: completed ? AppColors.textTertiary : AppColors.textPrimary,
    height: 1.4,
    decoration: completed ? TextDecoration.lineThrough : TextDecoration.none,
    decorationColor: AppColors.textTertiary,
  );

  /// Due → relative ("today", "tomorrow", "3d", "overdue 2d"). Else age of
  /// createdAt ("2d"). Null if neither is set.
  static String? _trailingLabel(ActionItem item) {
    final now = DateTime.now();
    final due = item.dueAt;
    if (due != null) {
      final today = DateTime(now.year, now.month, now.day);
      final dueDay = DateTime(due.year, due.month, due.day);
      final diffDays = dueDay.difference(today).inDays;
      if (diffDays < 0) return 'overdue ${-diffDays}d';
      if (diffDays == 0) return 'today';
      if (diffDays == 1) return 'tomorrow';
      if (diffDays < 7) return '${diffDays}d';
      if (diffDays < 30) return '${(diffDays / 7).round()}w';
      return '${(diffDays / 30).round()}mo';
    }
    final created = item.createdAt;
    if (created != null) {
      final age = now.difference(created);
      if (age.inDays < 1) return '${age.inHours}h';
      if (age.inDays < 30) return '${age.inDays}d';
      if (age.inDays < 365) return '${(age.inDays / 30).round()}mo';
      return '${(age.inDays / 365).round()}y';
    }
    return null;
  }

  /// Builds the bottom metadata strip. Each segment is `(text, optional dot
  /// color)`. Order is fixed; segments with no useful payload are dropped so
  /// the separator-dot rendering stays clean.
  ///
  /// Jira:
  ///   * status (with status_type-colored dot)
  ///   * project_key
  ///   * "Xd at status" when daysAtStatus > 0
  ///   * priority (skip "Medium"/"None" — boring middle)
  /// Transcript:
  ///   * "From conversation · Xd ago" — but only when createdAt exists. We
  ///     refuse to render "From conversation" alone because it's noise on a
  ///     row that already has a description.
  static List<_MetaSegment> _metaSegments(ActionItem item, {required bool sectionHasMixedSources}) {
    final ext = item.externalSource;
    final segments = <_MetaSegment>[];
    if (ext != null && ext.source == 'jira') {
      final status = ext.jiraStatus;
      if (status != null && status.isNotEmpty) {
        segments.add(_MetaSegment(text: status));
      }
      final project = ext.jiraProjectKey;
      if (project != null && project.isNotEmpty) {
        segments.add(_MetaSegment(text: project));
      }
      final days = ext.daysAtStatus;
      if (days != null && days > 0) {
        segments.add(_MetaSegment(text: '${days}d at status'));
      }
      final priority = ext.jiraPriority;
      if (priority != null && priority.isNotEmpty && priority != 'Medium' && priority != 'None') {
        segments.add(_MetaSegment(text: priority));
      }
      return segments;
    }
    // Transcript path. Refuse to render "From conversation" alone — a bare
    // label without an age is noise. When the visible group has no
    // Jira-sourced items to contrast against, drop the "From conversation"
    // prefix entirely and render only the age — repeating the source
    // across six rows in a single-source group is decorative noise.
    if (ext == null) {
      final created = item.createdAt;
      if (created != null) {
        final age = DateTime.now().difference(created);
        final ageLabel = _relativeAge(age);
        if (sectionHasMixedSources) {
          segments.add(const _MetaSegment(text: 'From conversation'));
        }
        segments.add(_MetaSegment(text: '$ageLabel ago'));
      }
    }
    return segments;
  }

  static String _relativeAge(Duration age) {
    if (age.inDays < 1) {
      final hours = age.inHours;
      if (hours <= 0) return 'just now';
      return '${hours}h';
    }
    if (age.inDays < 30) return '${age.inDays}d';
    if (age.inDays < 365) return '${(age.inDays / 30).round()}mo';
    return '${(age.inDays / 365).round()}y';
  }
}

class _MetaSegment {
  const _MetaSegment({required this.text});
  final String text;
}

/// Renders the bottom metadata strip as plain text-only segments separated
/// by middle dots ("·"). One `Text` widget per segment so screen-readers
/// and widget-finder tests can target each piece individually. Per
/// DESIGN.md, no colored dots, chips, or accent color anywhere on this
/// line.
class _MetaStrip extends StatelessWidget {
  const _MetaStrip({required this.segments});

  final List<_MetaSegment> segments;

  static const TextStyle _style = TextStyle(fontSize: 12, color: AppColors.textSecondary, fontWeight: FontWeight.w500);

  @override
  Widget build(BuildContext context) {
    final children = <Widget>[];
    for (var i = 0; i < segments.length; i++) {
      if (i > 0) {
        children.add(const Text(' · ', style: _style));
      }
      children.add(Text(segments[i].text, style: _style));
    }
    return Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: children);
  }
}

class _Checkbox extends StatelessWidget {
  const _Checkbox({required this.checked});
  final bool checked;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        color: checked ? AppColors.brandPrimary : Colors.transparent,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: checked ? AppColors.brandPrimary : AppColors.textTertiary.withValues(alpha: 0.5),
          width: 1.5,
        ),
      ),
      child: checked ? const Icon(Icons.check_rounded, size: 14, color: AppColors.textPrimary) : null,
    );
  }
}
