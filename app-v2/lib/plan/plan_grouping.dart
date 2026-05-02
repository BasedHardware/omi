import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';

/// One section in the Plan list. Title is uppercase / letter-spaced (already
/// styled by `_GroupSection`). Items are pre-sorted in pivot-appropriate
/// order — the renderer doesn't re-sort.
class PlanGroup {
  const PlanGroup(this.title, this.items);
  final String title;
  final List<ActionItem> items;
}

/// All grouping logic for the Plan list, keyed off [PlanPivot]. Pulled out of
/// the screen widget so it's directly unit-testable without pumping a
/// MaterialApp.
///
/// All three pivots share one rule: transcript items (no externalSource)
/// always render under their own group at the bottom. The pivot only
/// reshuffles Jira items.
class PlanGrouping {
  PlanGrouping._();

  /// Bucket order for [PlanPivot.byStatus]. Jira's status_type values map to
  /// the same canonical order ("To Do" → "In Progress" → "Done") that most
  /// project boards use, so the screen reads top-to-bottom as workflow flow.
  static const Map<String, int> _statusTypeOrder = {'todo': 0, 'indeterminate': 1, 'done': 2};

  static const String _transcriptTitle = 'FROM CONVERSATIONS';

  static List<PlanGroup> group(List<ActionItem> items, {required PlanPivot pivot}) {
    switch (pivot) {
      case PlanPivot.byDate:
        return _groupByDate(items);
      case PlanPivot.byProject:
        return _groupByProject(items);
      case PlanPivot.byStatus:
        return _groupByStatus(items);
    }
  }

  /// Original pre-pivot bucketing. Kept identical so the byDate path is a
  /// strict no-op refactor relative to the previous Plan screen.
  static List<PlanGroup> _groupByDate(List<ActionItem> items) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final tomorrow = today.add(const Duration(days: 1));
    final weekEnd = today.add(const Duration(days: 7));
    final overdue = <ActionItem>[];
    final dueToday = <ActionItem>[];
    final thisWeek = <ActionItem>[];
    final later = <ActionItem>[];
    final anytime = <ActionItem>[];
    for (final item in items) {
      final due = item.dueAt;
      if (due == null) {
        anytime.add(item);
      } else if (due.isBefore(today)) {
        overdue.add(item);
      } else if (due.isBefore(tomorrow)) {
        dueToday.add(item);
      } else if (due.isBefore(weekEnd)) {
        thisWeek.add(item);
      } else {
        later.add(item);
      }
    }
    return [
      if (overdue.isNotEmpty) PlanGroup('OVERDUE', _sortByDue(overdue)),
      if (dueToday.isNotEmpty) PlanGroup('TODAY', _sortByDue(dueToday)),
      if (thisWeek.isNotEmpty) PlanGroup('THIS WEEK', _sortByDue(thisWeek)),
      if (later.isNotEmpty) PlanGroup('LATER', _sortByDue(later)),
      if (anytime.isNotEmpty) PlanGroup('ANYTIME', _sortByCreated(anytime)),
    ];
  }

  /// Jira items grouped by `metadata.project_key`, projects sorted
  /// alphabetically. Jira items missing a project_key fall under "JIRA"
  /// rather than disappearing — better-than-nothing surfacing keeps the
  /// pivot honest. Transcript items always tail under FROM CONVERSATIONS.
  static List<PlanGroup> _groupByProject(List<ActionItem> items) {
    final byProject = <String, List<ActionItem>>{};
    final transcript = <ActionItem>[];
    for (final item in items) {
      final ext = item.externalSource;
      if (ext == null) {
        transcript.add(item);
        continue;
      }
      final key = ext.jiraProjectKey;
      final bucket = (key != null && key.isNotEmpty) ? key : 'JIRA';
      byProject.putIfAbsent(bucket, () => []).add(item);
    }
    final sortedKeys = byProject.keys.toList()..sort();
    final groups = <PlanGroup>[for (final k in sortedKeys) PlanGroup(k, _sortByDueThenCreated(byProject[k]!))];
    if (transcript.isNotEmpty) {
      groups.add(PlanGroup(_transcriptTitle, _sortByCreated(transcript)));
    }
    return groups;
  }

  /// Jira items grouped by `metadata.status`, status groups ordered by
  /// status_type (todo → indeterminate → done), alphabetical inside each
  /// type. Transcript items tail under FROM CONVERSATIONS.
  static List<PlanGroup> _groupByStatus(List<ActionItem> items) {
    final byStatus = <String, _StatusBucket>{};
    final transcript = <ActionItem>[];
    for (final item in items) {
      final ext = item.externalSource;
      if (ext == null) {
        transcript.add(item);
        continue;
      }
      final status = ext.jiraStatus;
      final type = ext.jiraStatusType;
      final key = (status != null && status.isNotEmpty) ? status : 'No Status';
      byStatus.putIfAbsent(key, () => _StatusBucket(label: key, statusType: type)).items.add(item);
    }
    final entries = byStatus.values.toList()
      ..sort((a, b) {
        final aOrder = _statusTypeOrder[a.statusType] ?? 99;
        final bOrder = _statusTypeOrder[b.statusType] ?? 99;
        if (aOrder != bOrder) return aOrder.compareTo(bOrder);
        return a.label.toLowerCase().compareTo(b.label.toLowerCase());
      });
    final groups = <PlanGroup>[
      for (final e in entries) PlanGroup(e.label.toUpperCase(), _sortByDueThenCreated(e.items)),
    ];
    if (transcript.isNotEmpty) {
      groups.add(PlanGroup(_transcriptTitle, _sortByCreated(transcript)));
    }
    return groups;
  }

  static List<ActionItem> _sortByDue(List<ActionItem> list) {
    list.sort((a, b) => (a.dueAt ?? DateTime(2100)).compareTo(b.dueAt ?? DateTime(2100)));
    return list;
  }

  static List<ActionItem> _sortByCreated(List<ActionItem> list) {
    list.sort((a, b) {
      final ac = a.createdAt;
      final bc = b.createdAt;
      if (ac == null && bc == null) return 0;
      if (ac == null) return 1;
      if (bc == null) return -1;
      return bc.compareTo(ac);
    });
    return list;
  }

  /// Pivot-internal ordering: due date first (earliest due → top), then
  /// created date as a tiebreaker (newest first). Items with no due date
  /// fall to the bottom of the bucket.
  static List<ActionItem> _sortByDueThenCreated(List<ActionItem> list) {
    list.sort((a, b) {
      final aDue = a.dueAt;
      final bDue = b.dueAt;
      if (aDue != null && bDue != null) {
        final cmp = aDue.compareTo(bDue);
        if (cmp != 0) return cmp;
      } else if (aDue == null && bDue != null) {
        return 1;
      } else if (aDue != null && bDue == null) {
        return -1;
      }
      final ac = a.createdAt;
      final bc = b.createdAt;
      if (ac == null && bc == null) return 0;
      if (ac == null) return 1;
      if (bc == null) return -1;
      return bc.compareTo(ac);
    });
    return list;
  }
}

class _StatusBucket {
  _StatusBucket({required this.label, required this.statusType});
  final String label;
  final String? statusType;
  final List<ActionItem> items = [];
}
