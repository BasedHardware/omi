/// Light client model for `GET /v1/conversations`. We only project the
/// fields the v0 mobile UI renders (title, overview, when, who, segments).
/// Full Conversation has dozens of fields; the rest are decoded lazily via
/// the raw JSON kept on the model in case the detail screen needs them.
class ConversationItem {
  const ConversationItem({
    required this.id,
    required this.title,
    required this.overview,
    required this.category,
    required this.createdAt,
    required this.starred,
    required this.segmentCount,
    required this.actionItemCount,
    required this.appResultCount,
    required this.raw,
  });

  final String id;
  final String title;
  final String overview;
  final String? category;
  final DateTime? createdAt;
  final bool starred;
  final int segmentCount;
  final int actionItemCount;
  final int appResultCount;
  final Map<String, dynamic> raw;

  /// Parsed `decisions` array from `structured.decisions`. Returns an empty
  /// list when the key is absent (legacy/non-allowlisted backend response)
  /// or when the field is not a list. Computed lazily on each read — there's
  /// at most a handful of decisions per conversation, so this is cheap.
  List<DecisionItem> get decisions {
    final structured = raw['structured'];
    if (structured is! Map) return const [];
    final list = structured['decisions'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map((m) => DecisionItem.fromJson(Map<String, dynamic>.from(m)))
        .toList(growable: false);
  }

  /// True when the backend wrote a `decisions` key onto `structured`,
  /// regardless of whether the array has any entries. Lets the detail
  /// screen distinguish "extraction ran but found nothing" (zero-state
  /// caption) from "user is not allowlisted" (no section at all).
  bool get hasDecisionsField {
    final structured = raw['structured'];
    if (structured is! Map) return false;
    return structured.containsKey('decisions');
  }

  static ConversationItem fromJson(Map<String, dynamic> j) {
    final structured = j['structured'] is Map
        ? Map<String, dynamic>.from(j['structured'] as Map)
        : const <String, dynamic>{};
    final segs = j['transcript_segments'];
    final actions = structured['action_items'];
    final apps = j['apps_results'];
    return ConversationItem(
      id: (j['id'] as String?) ?? '',
      title: (structured['title'] as String?)?.trim().isNotEmpty == true
          ? structured['title'] as String
          : 'Untitled conversation',
      overview: (structured['overview'] as String?) ?? '',
      category: structured['category'] as String?,
      createdAt: _parseDate(j['created_at']),
      starred: j['starred'] == true,
      segmentCount: segs is List ? segs.length : 0,
      actionItemCount: actions is List ? actions.length : 0,
      appResultCount: apps is List ? apps.length : 0,
      raw: j,
    );
  }

  static DateTime? _parseDate(Object? v) {
    if (v is String && v.isNotEmpty) {
      return DateTime.tryParse(v)?.toLocal();
    }
    return null;
  }
}

/// One decision extracted from a meeting transcript. Lives in the
/// `decisions` array on `structured`. v0 is built-in (not app-produced);
/// v0.1 may externalize as an app capability.
class DecisionItem {
  const DecisionItem({
    required this.id,
    required this.statement,
    this.ownerName,
    this.dueAt,
    required this.status,
    required this.openQuestions,
    required this.relatedActionItemIds,
  });

  final String id;
  final String statement;
  final String? ownerName;
  final DateTime? dueAt;
  final String status; // "open" | "done" | "blocked"
  final List<String> openQuestions;
  // Indexes into structured.action_items (positional). v0.1 graduates to stable ids — see app-v2/TODOS.md.
  final List<int> relatedActionItemIds;

  static DecisionItem fromJson(Map<String, dynamic> j) {
    return DecisionItem(
      id: (j['id'] as String?) ?? '',
      statement: (j['statement'] as String?) ?? '',
      ownerName: j['owner_name'] as String?,
      dueAt: _parseDate(j['due_at']),
      status: (j['status'] as String?) ?? 'open',
      openQuestions: (j['open_questions'] is List)
          ? List<String>.from((j['open_questions'] as List).whereType<String>())
          : const <String>[],
      relatedActionItemIds: (j['related_action_item_ids'] is List)
          ? List<int>.from((j['related_action_item_ids'] as List).whereType<num>().map((n) => n.toInt()))
          : const <int>[],
    );
  }

  static DateTime? _parseDate(Object? v) {
    if (v is String && v.isNotEmpty) {
      return DateTime.tryParse(v)?.toLocal();
    }
    return null;
  }
}

/// Date-bucket label for a list-grouped conversations view. Matches the
/// desktop-v2 grouping: Today / Yesterday / This Week / This Month / month name.
String conversationDateBucket(DateTime? d, {DateTime? now}) {
  if (d == null) return 'Earlier';
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  final dayStart = DateTime(d.year, d.month, d.day);
  final diff = today.difference(dayStart).inDays;
  if (diff == 0) return 'Today';
  if (diff == 1) return 'Yesterday';
  if (diff < 7) return 'This Week';
  if (diff < 30) return 'This Month';
  if (d.year == n.year) {
    return _monthLong(d.month);
  }
  return '${_monthLong(d.month)} ${d.year}';
}

const _months = <String>[
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

String _monthLong(int month) => _months[(month - 1).clamp(0, 11)];

class ConversationGroup {
  const ConversationGroup({required this.label, required this.items});
  final String label;
  final List<ConversationItem> items;
}
