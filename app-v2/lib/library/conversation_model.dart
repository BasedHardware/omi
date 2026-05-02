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

  static ConversationItem fromJson(Map<String, dynamic> j) {
    final structured = j['structured'] is Map ? Map<String, dynamic>.from(j['structured'] as Map) : const <String, dynamic>{};
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
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

String _monthLong(int month) => _months[(month - 1).clamp(0, 11)];

class ConversationGroup {
  const ConversationGroup({required this.label, required this.items});
  final String label;
  final List<ConversationItem> items;
}
