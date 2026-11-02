import 'package:omi/backend/schema/review.dart';

/// Where a change appears on Recent changes, in screen order.
enum RecentChangeSection { terms, memories, tasks, titles, people, conversations, other }

RecentChangeSection recentChangeSection(ReviewChange change) => switch (change.editKind) {
      'spelling' || 'transcript' || 'vocabulary' => RecentChangeSection.terms,
      'memory' || 'merge_memories' || 'retire_memory' || 'supersede_memory' => RecentChangeSection.memories,
      'close_task' || 'merge_tasks' || 'retire_task' => RecentChangeSection.tasks,
      'title' || 'overview' || 'entity_summary' => RecentChangeSection.titles,
      'merge_people' || 'dismiss_person' => RecentChangeSection.people,
      'merge_conversations' || 'set_language' => RecentChangeSection.conversations,
      _ => switch (change.kind) {
          ReviewChangeKind.rename => RecentChangeSection.terms,
          ReviewChangeKind.mergeMemories => RecentChangeSection.memories,
          ReviewChangeKind.closeTask => RecentChangeSection.tasks,
          ReviewChangeKind.titleConversation => RecentChangeSection.titles,
          ReviewChangeKind.updatePerson || ReviewChangeKind.labelSpeaker => RecentChangeSection.people,
          ReviewChangeKind.other => RecentChangeSection.other,
        },
    };

/// The text before the change, preferring the server-extracted span over the stored field.
String? recentChangeBefore(ReviewChange change) => _nonEmpty(change.diff?.before) ?? _nonEmpty(change.before);

/// The text after the change. Empty means removed; null means the server did not say.
String? recentChangeAfter(ReviewChange change) => change.diff?.after ?? change.after;

String? _nonEmpty(String? value) => value == null || value.isEmpty ? null : value;

final _idLike = RegExp(r'^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$|^[0-9A-Za-z_-]{20,}$');

/// A reference label fit to show: never an id standing in for a name.
String? recentChangeRefLabel(ReviewChangeRef ref) {
  final label = ref.label.trim();
  if (label.isEmpty || label == ref.id || _idLike.hasMatch(label)) return null;
  return label;
}

/// The conversation a change came from, if it has one.
ReviewChangeRef? recentChangeConversation(ReviewChange change) =>
    change.refs.where((ref) => ref.type == 'conversation' && ref.id.isNotEmpty).firstOrNull;

/// The title of the conversation (or other source) a change came from, never an id.
String? recentChangeSourceTitle(ReviewChange change) {
  final title = _nonEmpty(change.diff?.sourceTitle?.trim()) ?? _nonEmpty(change.context?.conversationTitle.trim());
  if (title != null) return title;
  final conversation = recentChangeConversation(change);
  return conversation == null ? null : recentChangeRefLabel(conversation);
}

/// When the source happened, falling back to when Omi made the change.
DateTime recentChangeSourceTime(ReviewChange change) =>
    change.diff?.sourceStartedAt ?? change.context?.conversationDate ?? change.createdAt;

/// The verification note, only when it says something the row does not.
String? recentChangeNote(ReviewChange change) {
  final reason = change.reason?.trim();
  if (reason == null || reason.isEmpty || reason == change.title.trim()) return null;
  return reason;
}

/// The same change applied in one or more places, shown as one row.
class RecentChangeGroup {
  RecentChangeGroup._(this.key, this.section, this.changes);

  final String key;
  final RecentChangeSection section;

  /// Newest first; never empty.
  final List<ReviewChange> changes;

  ReviewChange get latest => changes.first;
  String? get before => recentChangeBefore(latest);
  String? get after => recentChangeAfter(latest);

  bool get allUndone => changes.every((c) => c.undone);
  List<ReviewChange> get active => changes.where((c) => !c.undone).toList(growable: false);

  /// Distinct conversations touched; changes without a conversation count once each.
  int get conversationCount {
    final ids = <String>{};
    var unanchored = 0;
    for (final change in changes) {
      final conversation = recentChangeConversation(change);
      if (conversation == null) {
        unanchored++;
      } else {
        ids.add(conversation.id);
      }
    }
    return ids.length + unanchored;
  }

  /// Every place the change landed across those conversations.
  int get placeCount => changes.fold(0, (sum, c) => sum + (c.diff?.occurrenceCount ?? 1));
}

String _groupKey(ReviewChange change, RecentChangeSection section) {
  final explicit = change.groupKey;
  if (explicit != null) return 'g:$explicit';
  final before = recentChangeBefore(change);
  final after = recentChangeAfter(change);
  if (before == null && (after == null || after.isEmpty)) return 'c:${change.changeId}';
  // Without a server key, the same kind of edit with the same before and after is the same change.
  return 'f:${section.name}\u0000${change.editKind ?? change.kind.name}\u0000${before ?? ''}\u0000${after ?? ''}';
}

/// Groups [changes] by what changed, sections in screen order and the newest group first within
/// each section.
Map<RecentChangeSection, List<RecentChangeGroup>> groupRecentChanges(List<ReviewChange> changes) {
  final byKey = <String, List<ReviewChange>>{};
  final sections = <String, RecentChangeSection>{};
  for (final change in changes) {
    final section = recentChangeSection(change);
    final key = _groupKey(change, section);
    (byKey[key] ??= []).add(change);
    sections.putIfAbsent(key, () => section);
  }
  final result = <RecentChangeSection, List<RecentChangeGroup>>{};
  for (final entry in byKey.entries) {
    final sorted = [...entry.value]..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    final section = sections[entry.key]!;
    (result[section] ??= []).add(RecentChangeGroup._(entry.key, section, List.unmodifiable(sorted)));
  }
  for (final groups in result.values) {
    groups.sort((a, b) => b.latest.createdAt.compareTo(a.latest.createdAt));
  }
  return {
    for (final section in RecentChangeSection.values)
      if (result[section] case final groups?) section: groups,
  };
}
