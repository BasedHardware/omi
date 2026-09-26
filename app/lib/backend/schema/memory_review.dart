import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;

/// One memory Omi says it learned, as referenced by the daily summary.
///
/// Deliberately carries no review verdict: `user_review`/`edited` are read live
/// from the memory itself (`MemoriesProvider`), so a vote cast on one device is
/// visible on the other. A reference that has gone stale still renders its
/// content; only the controls depend on the live row.
class MemoryReviewItem {
  final String memoryId;
  final String content;
  final String category;
  final DateTime? capturedAt;

  const MemoryReviewItem({required this.memoryId, required this.content, this.category = '', this.capturedAt});

  factory MemoryReviewItem.fromGenerated(wire.GeneratedLearnedMemoryRef generated) {
    return MemoryReviewItem(
      memoryId: generated.memoryId,
      content: generated.content,
      category: generated.category,
      capturedAt: generated.capturedAt,
    );
  }

  /// Decode one `memoryReviewCard.items[]` entry. Returns null for anything
  /// without an id or content: an unusable row must not become a blank control.
  static MemoryReviewItem? tryFromBlockItem(Object? value) {
    if (value is! Map) return null;
    final map = Map<String, dynamic>.from(value);
    String read(String camel, String snake) {
      final raw = map[camel] ?? map[snake];
      return raw is String ? raw.trim() : '';
    }

    final memoryId = read('memoryId', 'memory_id');
    final content = read('content', 'content');
    if (memoryId.isEmpty || content.isEmpty) return null;
    return MemoryReviewItem(memoryId: memoryId, content: content, category: read('category', 'category'));
  }

  /// Human label for the small category tag. Empty when the backend sent none.
  String get categoryLabel {
    final trimmed = category.trim();
    if (trimmed.isEmpty) return '';
    final normalized = trimmed.replaceAll('_', ' ');
    return normalized[0].toUpperCase() + normalized.substring(1);
  }
}

/// The `memoryReviewCard` chat content block.
///
/// Built by `backend/utils/memory/learned_today.py`; the block never carries
/// review state, only identity plus the paraphrase to show.
class MemoryReviewCardBlock {
  final String id;
  final String summaryId;
  final String date;
  final List<MemoryReviewItem> items;

  const MemoryReviewCardBlock({required this.id, required this.summaryId, required this.date, required this.items});

  static const int maxItems = 3;

  static const Set<String> blockTypes = {'memoryReviewCard', 'memory_review_card'};

  /// Fail-soft: an unknown, malformed, or item-less block decodes to null so the
  /// day summary text renders exactly as it did before this block existed.
  static MemoryReviewCardBlock? tryFromBlock(Map<String, dynamic> block) {
    if (!blockTypes.contains(block['type'])) return null;
    final rawItems = block['items'];
    if (rawItems is! List) return null;
    final items = rawItems
        .map(MemoryReviewItem.tryFromBlockItem)
        .whereType<MemoryReviewItem>()
        .take(maxItems)
        .toList(growable: false);
    if (items.isEmpty) return null;
    String read(String camel, String snake) {
      final raw = block[camel] ?? block[snake];
      return raw is String ? raw : '';
    }

    return MemoryReviewCardBlock(
      id: read('id', 'id'),
      summaryId: read('summaryId', 'summary_id'),
      date: read('date', 'date'),
      items: items,
    );
  }
}
