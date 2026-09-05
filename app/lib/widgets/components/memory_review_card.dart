import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

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

/// "Things I learned today" — up to three memories Omi stored, each with
/// confirm / drop / correct controls.
///
/// The card owns no verdict state. Every row reads `userReview`/`edited` live
/// from [MemoriesProvider], which is the single mutation owner: a vote cast on
/// desktop shows here, and a vote cast here is not persisted in the chat
/// message or in preferences. A tap paints optimistically only until the
/// request returns, then the row goes back to reading the live memory.
///
/// A row whose id the provider has not loaded is still actionable: the item
/// carries the id and the recap text, and the provider's review and edit
/// requests are id-addressed. Such a row stays pending until a verdict is
/// written, and the card never renders untappable control chrome.
class MemoryReviewCard extends StatefulWidget {
  const MemoryReviewCard({
    super.key,
    required this.items,
    required this.source,
    this.impressionKey,
    this.title = 'Things I learned today',
  });

  final List<MemoryReviewItem> items;
  final MemoryReviewSource source;

  /// Stable identity for the shown-impression event. A chat card scrolled out
  /// and back rebuilds its State; without this the impression count would
  /// measure scrolling rather than reach.
  final String? impressionKey;
  final String title;

  @override
  State<MemoryReviewCard> createState() => _MemoryReviewCardState();
}

enum _RowState { pending, confirmed, dropped, updated }

class _MemoryReviewCardState extends State<MemoryReviewCard> {
  static const _cardColor = Color(0xFF1A1A1F);

  final Map<String, _RowState> _optimistic = {};
  final Set<String> _inFlight = {};
  final Set<String> _failed = {};
  final Map<String, TextEditingController> _editors = {};

  /// The text a persisted correction submitted, per row. A knowledge-ledger
  /// correction appends a new row under a *new* id, so the id this card
  /// references stops resolving in the provider; without this the row would
  /// fall back to the original learned text under an "Updated." status.
  final Map<String, String> _settledEdits = {};

  /// Card identities already counted as shown in this process.
  static final Set<String> _seenImpressions = {};

  List<MemoryReviewItem> get _rows => widget.items.take(MemoryReviewCardBlock.maxItems).toList(growable: false);

  @override
  void initState() {
    super.initState();
    final impressionKey = widget.impressionKey;
    if (_rows.isNotEmpty && (impressionKey == null || _seenImpressions.add('${widget.source.name}:$impressionKey'))) {
      PlatformManager.instance.analytics.memoryReviewCardShown(
        itemCount: _rows.length,
        source: widget.source.analyticsValue,
      );
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureMemoriesLoaded());
  }

  @override
  void dispose() {
    for (final controller in _editors.values) {
      controller.dispose();
    }
    super.dispose();
  }

  MemoriesProvider? _memoriesProvider({required bool listen}) {
    try {
      return listen ? context.watch<MemoriesProvider>() : context.read<MemoriesProvider>();
    } on ProviderNotFoundException {
      return null;
    }
  }

  /// A memory referenced by the card may not be in the provider's list (cold
  /// provider, truncated bulk list, or an id this client never paged in).
  /// There is no by-id read on this client, so ask the provider — the single
  /// owner of memory state — to load its list. Hydration is best-effort: the
  /// controls act by id regardless, and only settled verdicts need the live
  /// row.
  void _ensureMemoriesLoaded() {
    _startHydrationIfNeeded();
  }

  void _startHydrationIfNeeded() {
    if (!mounted) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    // A fetch the provider owns is already in flight (memories page, an
    // earlier card); when it settles the rows re-read whatever it loaded.
    // A never-loaded provider reports `loading == true` before any request
    // exists, so that alone must not read as "a fetch is in flight".
    if (provider.loading && provider.hasLoaded) return;
    final eligible = _rows
        .where((item) => _memoryFor(provider, item.memoryId) == null)
        .map((item) => item.memoryId)
        // The provider owns the attempt budget (session-scoped, reset on user
        // data clear), so a State rebuilt by scrolling does not re-count and
        // a failing backend is not retried forever.
        .where(provider.consumeHydrationAsk)
        .toList(growable: false);
    if (eligible.isEmpty) return;
    provider.loadMemories();
  }

  Memory? _memoryFor(MemoriesProvider provider, String memoryId) {
    return provider.memories.firstWhereOrNull((memory) => memory.id == memoryId);
  }

  /// Live state first: an optimistic verdict only survives until its request
  /// returns, after which `userReview`/`edited` on the memory are authoritative.
  _RowState _stateFor(MemoriesProvider? provider, Memory? memory, String memoryId) {
    final optimistic = _optimistic[memoryId];
    if (optimistic != null) return optimistic;
    if (memory == null) {
      // A correction that appended a replacement row leaves this id
      // unresolvable; that is settled, not unknown — but only while nothing
      // live answers for the id, so a later refresh or another device still
      // wins. A verdict this card persisted while unresolved settles the row
      // the same way; anything else is pending, because the controls act by
      // id and no verdict has been read.
      if (_settledEdits.containsKey(memoryId)) return _RowState.updated;
      final settled = provider?.settledReviewFor(memoryId);
      if (settled != null) return settled ? _RowState.confirmed : _RowState.dropped;
      return _RowState.pending;
    }
    if (memory.userReview == false) return _RowState.dropped;
    if (memory.userReview == true) return _RowState.confirmed;
    if (memory.edited) return _RowState.updated;
    return _RowState.pending;
  }

  String _statusText(_RowState state) {
    switch (state) {
      case _RowState.confirmed:
        return "Confirmed. I'll act on this.";
      case _RowState.dropped:
        return "Dropped. I'll avoid facts like this.";
      case _RowState.updated:
        return 'Updated.';
      case _RowState.pending:
        return '';
    }
  }

  Future<void> _review(MemoryReviewItem item, Memory? memory, bool accepted) async {
    if (_inFlight.contains(item.memoryId)) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    setState(() {
      _inFlight.add(item.memoryId);
      _failed.remove(item.memoryId);
      _optimistic[item.memoryId] = accepted ? _RowState.confirmed : _RowState.dropped;
    });

    // A row the provider never loaded still mutates: the requests are
    // id-addressed, and the item carries the identity to address it with.
    final persisted = await provider.reviewMemory(memory ?? _standInMemory(item), accepted);
    if (!mounted) return;
    setState(() {
      _inFlight.remove(item.memoryId);
      // Drop the optimistic paint either way: on success the provider has
      // already applied the verdict to the memory this row reads, and when no
      // live memory answers for the id the settled verdict below does.
      _optimistic.remove(item.memoryId);
      if (!persisted) {
        _failed.add(item.memoryId);
      }
    });
    PlatformManager.instance.analytics.memoryReviewAction(
      source: widget.source.analyticsValue,
      action: accepted ? 'accept' : 'reject',
      outcome: persisted ? 'ok' : 'error',
      memoryCategory: _categoryOf(item, memory),
    );
  }

  Future<void> _saveEdit(MemoryReviewItem item, Memory? memory) async {
    final controller = _editors[item.memoryId];
    final value = controller?.text.trim() ?? '';
    if (value.isEmpty || _inFlight.contains(item.memoryId)) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    setState(() {
      _inFlight.add(item.memoryId);
      _failed.remove(item.memoryId);
      _optimistic[item.memoryId] = _RowState.updated;
    });

    final persisted = await provider.editMemory(memory ?? _standInMemory(item), value);
    if (!mounted) return;
    setState(() {
      _inFlight.remove(item.memoryId);
      // Drop the optimistic paint either way. What the row shows next is
      // derived state: the live memory when the id still resolves, otherwise
      // the correction recorded below.
      _optimistic.remove(item.memoryId);
      if (persisted) {
        _editors.remove(item.memoryId)?.dispose();
        // A knowledge-ledger correction appends a new row under a new id, so
        // the memory this reference points at can stop resolving. Remember what
        // was submitted so the row shows the corrected text under "Updated."
        // rather than the original learned text under a disabled control.
        _settledEdits[item.memoryId] = value;
      } else {
        _failed.add(item.memoryId);
      }
    });
    PlatformManager.instance.analytics.memoryReviewAction(
      source: widget.source.analyticsValue,
      action: 'edit',
      outcome: persisted ? 'ok' : 'error',
      memoryCategory: _categoryOf(item, memory),
    );
  }

  String _categoryOf(MemoryReviewItem item, Memory? memory) {
    if (item.category.trim().isNotEmpty) return item.category.trim();
    return memory?.category.name ?? '';
  }

  /// The mutation carrier for a row whose live memory has not been loaded:
  /// identity (the id) plus the recap text. Only the id-addressed review and
  /// edit requests consume it; no list-mutating provider path reads anything
  /// else off it.
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

  /// What a row displays: the live memory when it resolves, otherwise the
  /// last correction this card persisted, otherwise the recap text.
  String _contentOf(MemoryReviewItem item, Memory? memory) {
    final live = memory?.content.trim() ?? '';
    return live.isNotEmpty ? live : (_settledEdits[item.memoryId] ?? item.content);
  }

  @override
  Widget build(BuildContext context) {
    final rows = _rows;
    if (rows.isEmpty) return const SizedBox.shrink();
    final provider = _memoriesProvider(listen: true);
    // A load that already settled in failure is the card's cue to spend its
    // capped retry: the initState ask started this load, and only a rebuild
    // observes how it settled.
    if (provider != null && provider.hasLoaded && provider.loadFailed) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _startHydrationIfNeeded());
    }

    return Column(
      key: const Key('memory_review_card'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          widget.title,
          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 10),
        ...rows.map((item) {
          final memory = provider == null ? null : _memoryFor(provider, item.memoryId);
          return _buildRow(item, provider, memory);
        }),
      ],
    );
  }

  Widget _buildRow(MemoryReviewItem item, MemoriesProvider? provider, Memory? memory) {
    final interactive = provider != null;
    final state = _stateFor(provider, memory, item.memoryId);
    final editing = _editors.containsKey(item.memoryId);
    final dimmed = state == _RowState.dropped;
    final content = _contentOf(item, memory);

    return Container(
      key: Key('memory_review_row_${item.memoryId}'),
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: _cardColor, borderRadius: BorderRadius.circular(14)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Only the opacity changes when a row is dropped, so the list never
          // reflows under the user's finger.
          AnimatedOpacity(
            opacity: dimmed ? 0.45 : 1.0,
            duration: const Duration(milliseconds: 150),
            child: editing
                ? _buildEditor(item, memory)
                : Text(content, style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.35)),
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: 28,
            child: Row(
              children: [
                if (item.categoryLabel.isNotEmpty) ...[
                  Text(
                    item.categoryLabel,
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 11, letterSpacing: 0.3),
                  ),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  // Without a MemoriesProvider there is no mutation owner, so
                  // no controls render at all — never dead chrome.
                  child: interactive ? _buildTrailing(item, memory, state, editing) : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
          if (_failed.contains(item.memoryId))
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                "Couldn't save, try again",
                key: Key('memory_review_error_${item.memoryId}'),
                style: TextStyle(color: Colors.orange.shade300, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildEditor(MemoryReviewItem item, Memory? memory) {
    final controller = _editors[item.memoryId]!;
    return TextField(
      key: Key('memory_review_editor_${item.memoryId}'),
      controller: controller,
      maxLines: 1,
      autofocus: true,
      style: const TextStyle(color: Colors.white, fontSize: 15),
      decoration: InputDecoration(
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(vertical: 8),
        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: Colors.grey.shade700)),
        focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Colors.white)),
      ),
      onSubmitted: (_) => _saveEdit(item, memory),
    );
  }

  Widget _buildTrailing(MemoryReviewItem item, Memory? memory, _RowState state, bool editing) {
    if (editing) {
      return Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _control(
            key: Key('memory_review_cancel_${item.memoryId}'),
            label: 'Cancel',
            onTap: () => setState(() => _editors.remove(item.memoryId)?.dispose()),
          ),
          const SizedBox(width: 8),
          _control(
            key: Key('memory_review_save_${item.memoryId}'),
            label: 'Save',
            emphasized: true,
            onTap: _inFlight.contains(item.memoryId) ? null : () => _saveEdit(item, memory),
          ),
        ],
      );
    }

    if (state != _RowState.pending) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text(
          _statusText(state),
          key: Key('memory_review_status_${item.memoryId}'),
          style: TextStyle(color: Colors.grey.shade400, fontSize: 12.5),
        ),
      );
    }

    // Actionable by identity, not by list membership: the requests are
    // id-addressed and the item carries the id, so a row the provider never
    // loaded stays tappable. `_inFlight` only disables its own write.
    final enabled = !_inFlight.contains(item.memoryId);
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        _control(
          key: Key('memory_review_accept_${item.memoryId}'),
          label: '✓ Right',
          onTap: enabled ? () => _review(item, memory, true) : null,
        ),
        const SizedBox(width: 8),
        _control(
          key: Key('memory_review_reject_${item.memoryId}'),
          label: '✗ Wrong',
          onTap: enabled ? () => _review(item, memory, false) : null,
        ),
        const SizedBox(width: 8),
        _control(
          key: Key('memory_review_fix_${item.memoryId}'),
          label: 'Fix',
          onTap: enabled
              ? () => setState(() {
                    _failed.remove(item.memoryId);
                    _editors[item.memoryId] = TextEditingController(text: _contentOf(item, memory));
                  })
              : null,
        ),
      ],
    );
  }

  Widget _control({required Key key, required String label, VoidCallback? onTap, bool emphasized = false}) {
    final color = onTap == null
        ? Colors.grey.shade700
        : emphasized
            ? Colors.white
            : Colors.grey.shade300;
    return Semantics(
      button: true,
      enabled: onTap != null,
      label: label,
      child: InkWell(
        key: key,
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          child: Text(
            label,
            style: TextStyle(color: color, fontSize: 13, fontWeight: emphasized ? FontWeight.w600 : FontWeight.w500),
          ),
        ),
      ),
    );
  }
}
