import 'package:flutter/foundation.dart';

import 'package:collection/collection.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Where a review card is rendered. Carried into analytics verbatim.
enum MemoryReviewSource {
  chatBlock('chat_block'),
  dailySummaryDetail('daily_summary_detail');

  final String analyticsValue;

  const MemoryReviewSource(this.analyticsValue);
}

/// What a review row shows.
enum MemoryReviewRowState { pending, confirmed, dropped, updated }

/// The review state behind one "Things I learned today" card, shared by the Flutter card and the
/// native rows.
///
/// It owns no verdict. Every row reads `userReview`/`edited` live from [MemoriesProvider], the single
/// mutation owner; a tap paints optimistically only until the request returns, then the row reads
/// the live memory again. A row whose id the provider has not loaded stays actionable: the requests
/// are id-addressed and the item carries the id and the recap text.
class MemoryReviewController extends ChangeNotifier {
  /// Counts the shown impression once per [impressionKey] (per process) when the card has rows.
  ///
  /// With [shown] false the owner records the impression itself, through [recordShown], once the card
  /// is actually on screen (the native transcript projects history that may never scroll into view).
  MemoryReviewController(
      {required List<MemoryReviewItem> items, required this.source, String? impressionKey, bool shown = true})
      : rows = _cap(items),
        _impressionKey = impressionKey {
    if (shown) recordShown();
  }

  final String? _impressionKey;
  bool _shown = false;

  /// Counts the shown impression, at most once per controller and once per [_impressionKey].
  void recordShown() {
    if (_shown) return;
    _shown = true;
    final key = _impressionKey;
    if (rows.isNotEmpty && (key == null || _seenImpressions.add('${source.name}:$key'))) {
      PlatformManager.instance.analytics.memoryReviewCardShown(itemCount: rows.length, source: source.analyticsValue);
    }
  }

  /// The card's items, at most [MemoryReviewCardBlock.maxItems].
  List<MemoryReviewItem> rows;
  final MemoryReviewSource source;

  static List<MemoryReviewItem> _cap(List<MemoryReviewItem> items) =>
      items.take(MemoryReviewCardBlock.maxItems).toList(growable: false);

  /// Follows a parent that rebuilt the card with other items; the per-id state carries over.
  void updateItems(List<MemoryReviewItem> items) => rows = _cap(items);

  final Map<String, MemoryReviewRowState> _optimistic = {};
  final Set<String> _inFlight = {};
  final Set<String> _failed = {};

  /// The text a persisted correction submitted, per row. A knowledge-ledger correction appends a new
  /// row under a *new* id, so the id this card references stops resolving in the provider; without
  /// this the row would fall back to the original learned text under an "Updated." status.
  final Map<String, String> _settledEdits = {};

  /// Card identities already counted as shown in this process.
  static final Set<String> _seenImpressions = {};

  bool _disposed = false;

  bool isInFlight(String memoryId) => _inFlight.contains(memoryId);
  bool isFailed(String memoryId) => _failed.contains(memoryId);

  /// Clears a row's save-failed line, as opening its editor does.
  void clearFailed(String memoryId) {
    if (_failed.remove(memoryId)) _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  Memory? memoryFor(MemoriesProvider provider, String memoryId) {
    return provider.memories.firstWhereOrNull((memory) => memory.id == memoryId);
  }

  /// A memory referenced by the card may not be in the provider's list (cold provider, truncated bulk
  /// list, or an id this client never paged in). There is no by-id read on this client, so ask the
  /// provider, the single owner of memory state, to load its list. Hydration is best-effort: the
  /// controls act by id regardless, and only settled verdicts need the live row.
  void startHydrationIfNeeded(MemoriesProvider provider) {
    if (_disposed) return;
    // A fetch the provider owns is already in flight (memories page, an earlier card); when it
    // settles the rows re-read whatever it loaded. A never-loaded provider reports `loading == true`
    // before any request exists, so that alone must not read as "a fetch is in flight".
    if (provider.loading && provider.hasLoaded) return;
    final eligible = rows
        .where((item) => memoryFor(provider, item.memoryId) == null)
        .map((item) => item.memoryId)
        // The provider owns the attempt budget (session-scoped, reset on user data clear), so a card
        // rebuilt by scrolling does not re-count and a failing backend is not retried forever.
        .where(provider.consumeHydrationAsk)
        .toList(growable: false);
    if (eligible.isEmpty) return;
    provider.loadMemories();
  }

  /// A load that already settled in failure is the card's cue to spend its capped retry.
  bool shouldRetryHydration(MemoriesProvider provider) => provider.hasLoaded && provider.loadFailed;

  /// Live state first: an optimistic verdict only survives until its request returns, after which
  /// `userReview`/`edited` on the memory are authoritative.
  MemoryReviewRowState stateFor(MemoriesProvider? provider, Memory? memory, String memoryId) {
    final optimistic = _optimistic[memoryId];
    if (optimistic != null) return optimistic;
    if (memory == null) {
      // A correction that appended a replacement row leaves this id unresolvable; that is settled,
      // not unknown, but only while nothing live answers for the id, so a later refresh or another
      // device still wins. A verdict this card persisted while unresolved settles the row the same
      // way; anything else is pending, because the controls act by id and no verdict has been read.
      if (_settledEdits.containsKey(memoryId)) return MemoryReviewRowState.updated;
      final settled = provider?.settledReviewFor(memoryId);
      if (settled != null) return settled ? MemoryReviewRowState.confirmed : MemoryReviewRowState.dropped;
      return MemoryReviewRowState.pending;
    }
    if (memory.userReview == false) return MemoryReviewRowState.dropped;
    if (memory.userReview == true) return MemoryReviewRowState.confirmed;
    if (memory.edited) return MemoryReviewRowState.updated;
    return MemoryReviewRowState.pending;
  }

  /// Confirms ([accepted]) or drops a row through the provider.
  Future<void> review(MemoriesProvider provider, MemoryReviewItem item, Memory? memory, bool accepted) async {
    if (_inFlight.contains(item.memoryId) || _disposed) return;
    _inFlight.add(item.memoryId);
    _failed.remove(item.memoryId);
    _optimistic[item.memoryId] = accepted ? MemoryReviewRowState.confirmed : MemoryReviewRowState.dropped;
    _notify();

    // A row the provider never loaded still mutates: the requests are id-addressed, and the item
    // carries the identity to address it with.
    final persisted = await provider.reviewMemory(memory ?? _standInMemory(item), accepted);
    if (_disposed) return;
    _inFlight.remove(item.memoryId);
    // Drop the optimistic paint either way: on success the provider has already applied the verdict
    // to the memory this row reads, and when no live memory answers for the id the settled verdict
    // does.
    _optimistic.remove(item.memoryId);
    if (!persisted) _failed.add(item.memoryId);
    _notify();
    PlatformManager.instance.analytics.memoryReviewAction(
      source: source.analyticsValue,
      action: accepted ? 'accept' : 'reject',
      outcome: persisted ? 'ok' : 'error',
      memoryCategory: _categoryOf(item, memory),
    );
  }

  /// Saves a correction; answers whether it persisted. An empty [value] or a row with a write in
  /// flight saves nothing and answers false.
  Future<bool> saveEdit(MemoriesProvider provider, MemoryReviewItem item, Memory? memory, String value) async {
    if (value.isEmpty || _inFlight.contains(item.memoryId) || _disposed) return false;
    _inFlight.add(item.memoryId);
    _failed.remove(item.memoryId);
    _optimistic[item.memoryId] = MemoryReviewRowState.updated;
    _notify();

    final persisted = await provider.editMemory(memory ?? _standInMemory(item), value);
    if (_disposed) return false;
    _inFlight.remove(item.memoryId);
    // Drop the optimistic paint either way. What the row shows next is derived state: the live memory
    // when the id still resolves, otherwise the correction recorded below.
    _optimistic.remove(item.memoryId);
    if (persisted) {
      _settledEdits[item.memoryId] = value;
    } else {
      _failed.add(item.memoryId);
    }
    _notify();
    PlatformManager.instance.analytics.memoryReviewAction(
      source: source.analyticsValue,
      action: 'edit',
      outcome: persisted ? 'ok' : 'error',
      memoryCategory: _categoryOf(item, memory),
    );
    return persisted;
  }

  String _categoryOf(MemoryReviewItem item, Memory? memory) {
    if (item.category.trim().isNotEmpty) return item.category.trim();
    return memory?.category.name ?? '';
  }

  /// The mutation carrier for a row whose live memory has not been loaded: identity (the id) plus the
  /// recap text. Only the id-addressed review and edit requests consume it.
  Memory _standInMemory(MemoryReviewItem item) {
    return Memory(
      id: item.memoryId,
      uid: '',
      content: item.content,
      category: MemoryCategory.system,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      visibility: MemoryVisibility.private,
    );
  }

  /// What a row displays: the live memory when it resolves, otherwise the last correction this card
  /// persisted, otherwise the recap text.
  String contentOf(MemoryReviewItem item, Memory? memory) {
    final live = memory?.content.trim() ?? '';
    return live.isNotEmpty ? live : (_settledEdits[item.memoryId] ?? item.content);
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
