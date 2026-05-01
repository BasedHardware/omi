/// One memory: a fact Nooto inferred from conversation, or a note you wrote.
/// Backed by `/v3/memories/MemoryDB`. We model only the fields the v0 UI
/// touches; the wire schema is wider.
class MemoryItem {
  const MemoryItem({
    required this.id,
    required this.content,
    required this.bucket,
    required this.manuallyAdded,
    required this.isLocked,
    this.rawCategory,
    this.conversationId,
    this.appId,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String content;
  final MemoryBucket bucket;
  final String? rawCategory;
  final bool manuallyAdded;
  final bool isLocked;
  final String? conversationId;
  final String? appId;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory MemoryItem.fromJson(Map<String, dynamic> json) {
    final raw = json['category'] as String?;
    return MemoryItem(
      id: (json['id'] ?? '').toString(),
      content: (json['content'] ?? '').toString(),
      rawCategory: raw,
      bucket: MemoryBucket.fromCategory(raw),
      manuallyAdded: json['manually_added'] as bool? ?? false,
      isLocked: json['is_locked'] as bool? ?? false,
      conversationId: json['conversation_id'] as String?,
      appId: json['app_id'] as String?,
      createdAt: _parseDate(json['created_at']),
      updatedAt: _parseDate(json['updated_at']),
    );
  }

  static DateTime? _parseDate(dynamic value) {
    if (value is String && value.isNotEmpty) {
      return DateTime.tryParse(value)?.toLocal();
    }
    return null;
  }
}

/// Backend categories that should bucket as LIFE CONTEXT. Exposed so tests
/// can iterate the set without re-typing string literals (which would drift
/// from the [MemoryBucket.fromCategory] switch independently).
const Set<String> lifeContextCategories = {
  'work',
  'hobbies',
  'lifestyle',
  'interests',
  'skills',
  'learnings',
  'core',
  'system',
  'auto',
  'other',
};

/// Coalesced sections in the Library tab. Backend returns up to 11 raw
/// categories; we map them into 4 user-facing buckets per `/plan-eng-review`.
/// Unknown/null categories fall through to [yourNotes] — never silently
/// dropped (regression-class behaviour, locked by test).
enum MemoryBucket {
  interesting('INTERESTING'),
  lifeContext('LIFE CONTEXT'),
  habits('HABITS'),
  yourNotes('YOUR NOTES');

  const MemoryBucket(this.label);
  final String label;

  static MemoryBucket fromCategory(String? raw) {
    if (raw == null) return MemoryBucket.yourNotes;
    if (raw == 'interesting') return MemoryBucket.interesting;
    if (raw == 'habits') return MemoryBucket.habits;
    if (raw == 'manual') return MemoryBucket.yourNotes;
    if (lifeContextCategories.contains(raw)) return MemoryBucket.lifeContext;
    // Empty or unknown future categories go to YOUR NOTES — never silently
    // drop a memory just because we haven't mapped its category yet.
    return MemoryBucket.yourNotes;
  }
}

/// One section in the Library — bucket + the memories that belong to it.
class MemoryGroup {
  const MemoryGroup({required this.bucket, required this.items});

  final MemoryBucket bucket;
  final List<MemoryItem> items;
}
