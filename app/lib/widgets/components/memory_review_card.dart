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

enum _RowState { loading, pending, confirmed, dropped, updated }

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

  /// Ids this process has already asked the provider to go looking for. A card
  /// scrolled in and out of the chat list rebuilds its State, and an id that is
  /// genuinely absent from the account would otherwise re-trigger a full
  /// memories fetch on every rebuild.
  static final Set<String> _requestedIds = {};

  /// Whether this process has already asked the provider to load its list.
  /// Nothing in app start-up initialises [MemoriesProvider] — only the memories
  /// page calls `init()` — and a provider that has never loaded still reports
  /// `loading == true`, so "already loading" cannot be read as "a fetch is in
  /// flight" until this card has started one itself.
  static bool _loadRequested = false;

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

  /// A memory referenced by the card may not be in the provider's page yet.
  /// There is no by-id read on this client, so ask the provider — the single
  /// owner of memory state — to load its list once. Until it resolves the row
  /// renders its content with the controls disabled.
  void _ensureMemoriesLoaded() {
    if (!mounted) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    final unresolved = _rows
        .where((item) => _memoryFor(provider, item.memoryId) == null)
        .map((item) => item.memoryId)
        .where(_requestedIds.add)
        .toList(growable: false);
    if (unresolved.isEmpty) return;
    // Only skip when a fetch this process started is still running. Chat and
    // the daily summary are usually the first memory surface a session opens,
    // and there `loading` is just the never-loaded initial value.
    if (_loadRequested && provider.loading) return;
    _loadRequested = true;
    provider.loadMemories();
  }

  Memory? _memoryFor(MemoriesProvider provider, String memoryId) {
    return provider.memories.firstWhereOrNull((memory) => memory.id == memoryId);
  }

  /// Live state first: an optimistic verdict only survives until its request
  /// returns, after which `userReview`/`edited` on the memory are authoritative.
  _RowState _stateFor(Memory? memory, String memoryId) {
    final optimistic = _optimistic[memoryId];
    if (optimistic != null) return optimistic;
    // A correction that appended a replacement row leaves this id unresolvable.
    // That is settled, not still loading — but only while nothing live answers
    // for the id, so a later refresh or another device still wins.
    if (memory == null) return _settledEdits.containsKey(memoryId) ? _RowState.updated : _RowState.loading;
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
      case _RowState.loading:
      case _RowState.pending:
        return '';
    }
  }

  Future<void> _review(MemoryReviewItem item, Memory memory, bool accepted) async {
    if (_inFlight.contains(item.memoryId)) return;
    final provider = _memoriesProvider(listen: false);
    if (provider == null) return;
    setState(() {
      _inFlight.add(item.memoryId);
      _failed.remove(item.memoryId);
      _optimistic[item.memoryId] = accepted ? _RowState.confirmed : _RowState.dropped;
    });

    final persisted = await provider.reviewMemory(memory, accepted);
    if (!mounted) return;
    setState(() {
      _inFlight.remove(item.memoryId);
      // Drop the optimistic paint either way: on success the provider has
      // already applied the verdict to the memory this row reads.
      _optimistic.remove(item.memoryId);
      if (!persisted) _failed.add(item.memoryId);
    });
    PlatformManager.instance.analytics.memoryReviewAction(
      source: widget.source.analyticsValue,
      action: accepted ? 'accept' : 'reject',
      outcome: persisted ? 'ok' : 'error',
      memoryCategory: _categoryOf(item, memory),
    );
  }

  Future<void> _saveEdit(MemoryReviewItem item, Memory memory) async {
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

    final persisted = await provider.editMemory(memory, value);
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

  @override
  Widget build(BuildContext context) {
    final rows = _rows;
    if (rows.isEmpty) return const SizedBox.shrink();
    final provider = _memoriesProvider(listen: true);

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
        ...rows.map((item) => _buildRow(item, provider == null ? null : _memoryFor(provider, item.memoryId))),
      ],
    );
  }

  Widget _buildRow(MemoryReviewItem item, Memory? memory) {
    final state = _stateFor(memory, item.memoryId);
    final editing = _editors.containsKey(item.memoryId);
    final dimmed = state == _RowState.dropped;
    final live = memory?.content.trim() ?? '';
    final content = live.isNotEmpty ? live : (_settledEdits[item.memoryId] ?? item.content);

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
                Expanded(child: _buildTrailing(item, memory, state, editing)),
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
      onSubmitted: memory == null ? null : (_) => _saveEdit(item, memory),
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
            onTap: memory == null || _inFlight.contains(item.memoryId) ? null : () => _saveEdit(item, memory),
          ),
        ],
      );
    }

    if (state != _RowState.pending && state != _RowState.loading) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text(
          _statusText(state),
          key: Key('memory_review_status_${item.memoryId}'),
          style: TextStyle(color: Colors.grey.shade400, fontSize: 12.5),
        ),
      );
    }

    final enabled = memory != null && !_inFlight.contains(item.memoryId);
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
                  _editors[item.memoryId] = TextEditingController(text: memory.content.trim());
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
