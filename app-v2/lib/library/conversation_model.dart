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

  /// Per-app summary outputs from the backend's `_trigger_apps()`. Each
  /// entry is markdown (potentially containing generative-UI XML tags
  /// like `<rich-list>`, `<chart>`, `<accordion>`) keyed to the producing
  /// app. v0 only ever has one entry — the picked summarization app —
  /// but the backend models a list because historical conversations may
  /// have multiple. We always render `appsResults.first`.
  List<AppResult> get appsResults {
    final list = raw['apps_results'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map((m) => AppResult.fromJson(Map<String, dynamic>.from(m)))
        .toList(growable: false);
  }

  /// The active summarized app result rendered in the OVERVIEW slot. Null
  /// when the backend never produced any app summary for this conversation
  /// (in which case the OVERVIEW falls back to plain `Structured.overview`).
  AppResult? get summarizedApp => appsResults.isNotEmpty ? appsResults.first : null;

  /// App ids the backend's prompt picker suggested for this conversation
  /// before settling on one. Surfaced inside the picker sheet to highlight
  /// relevant choices first.
  List<String> get suggestedSummarizationApps {
    final list = raw['suggested_summarization_apps'];
    if (list is! List) return const [];
    return List<String>.from(list.whereType<String>());
  }

  /// Re-derives a [ConversationItem] from a server-fresh raw JSON map.
  /// Used by [ConversationsProvider.reprocessWithApp] after the backend
  /// returns the updated conversation document.
  static ConversationItem fromRaw(Map<String, dynamic> raw) => fromJson(raw);

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

/// One app's summarization output for a conversation. Mirrors the backend's
/// `apps_results` array entry: `{ app_id: "...", content: "..." }`.
///
/// The content can be plain markdown or markdown with embedded generative-UI
/// XML tags (rich-list, chart, accordion, timeline, …). See
/// `lib/widgets/generative_ui/` for the renderer.
class AppResult {
  const AppResult({this.appId, required this.content});

  final String? appId;
  final String content;

  factory AppResult.fromJson(Map<String, dynamic> j) {
    return AppResult(
      appId: j['app_id'] as String?,
      content: (j['content'] as String?) ?? '',
    );
  }
}
