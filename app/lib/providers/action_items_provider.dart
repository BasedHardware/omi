import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/services/action_item_export_service.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/integrations/apple_reminders_service.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

typedef ActionItemsFetcher = Future<ActionItemsResponse?> Function({
  int limit,
  int offset,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
});

typedef DeleteActionItemRequest = Future<bool> Function(String id);
typedef BulkDeleteActionItemsRequest = Future<List<String>?> Function(List<String> ids);
typedef CreateActionItemRequest = Future<ActionItemWithMetadata?> Function({
  required String description,
  DateTime? dueAt,
  String? conversationId,
  bool completed,
});
typedef UpdateDueDateRequest = Future<ActionItemWithMetadata?> Function(
  String id, {
  DateTime? dueAt,
  bool clearDueAt,
});

typedef UpdateActionItemRequest = Future<ActionItemWithMetadata?> Function(
  String id, {
  String? description,
  bool? completed,
  DateTime? dueAt,
});

typedef BatchUpdateActionItemsRequest = Future<bool> Function(List<Map<String, dynamic>> items);

/// An optimistic create that was included in a multi-selection bulk delete
/// while its server request was still in flight. The bulk endpoint cannot
/// delete a temp id, so the row is hidden and tombstoned immediately, kept out
/// of the bulk request, and the deletion completes with a single follow-up
/// delete of the confirmed server id once the create settles. A failed create
/// or a failed bulk request dissolves the capture and restores the row.
class _CapturedBulkDeleteCreate {
  _CapturedBulkDeleteCreate({
    required this.tempId,
    required this.index,
    required this.homeIndex,
  });

  final String tempId;

  /// Position snapshots so a failed bulk request can restore the row where
  /// the user expected it.
  final int index;
  final int homeIndex;

  /// Set when the create settles; the follow-up delete targets this id.
  String? serverId;
  ActionItemWithMetadata? settledRow;
}

class ActionItemsProvider extends ChangeNotifier {
  ActionItemsProvider({
    ActionItemsFetcher? getActionItems,
    DeleteActionItemRequest? deleteActionItemRequest,
    UpdateActionItemRequest? updateActionItemRequest,
    BulkDeleteActionItemsRequest? bulkDeleteActionItemsRequest,
    CreateActionItemRequest? createActionItemRequest,
    UpdateDueDateRequest? updateDueDateRequest,
    api.ActionItemsApi? actionItemsApi,
    BatchUpdateActionItemsRequest? batchUpdateActionItemsRequest,
  })  : _getActionItems = getActionItems ?? api.tryGetActionItems,
        _deleteActionItemRequest = deleteActionItemRequest ?? api.deleteActionItem,
        _updateActionItemRequest = updateActionItemRequest ?? api.updateActionItem,
        _bulkDeleteActionItemsRequest = bulkDeleteActionItemsRequest ?? api.bulkDeleteActionItems,
        _createActionItemRequest = createActionItemRequest ?? api.createActionItem,
        _updateDueDateRequest = updateDueDateRequest ?? api.updateActionItem,
        _batchUpdateActionItemsRequest = batchUpdateActionItemsRequest ?? api.batchUpdateActionItems,
        _actionItemsApi = actionItemsApi;

  final ActionItemsFetcher _getActionItems;
  final DeleteActionItemRequest _deleteActionItemRequest;
  final UpdateActionItemRequest _updateActionItemRequest;
  final BulkDeleteActionItemsRequest _bulkDeleteActionItemsRequest;
  final CreateActionItemRequest _createActionItemRequest;
  final UpdateDueDateRequest _updateDueDateRequest;
  final BatchUpdateActionItemsRequest _batchUpdateActionItemsRequest;
  final api.ActionItemsApi? _actionItemsApi;
  ApiViewState<List<ActionItemWithMetadata>> _listViewState = const ApiViewState(phase: ApiViewPhase.data);
  Future<void>? _initialLoad;
  bool _initialLoadCompleted = false;
  Future<void>? _homeWidgetLoad;
  DateTime? _homeWidgetRefreshedAt;
  Future<void>? _homeTodayLoad;
  bool _homeDayLoaded = false;
  List<ActionItemWithMetadata> _homeDayItems = [];

  List<ActionItemWithMetadata> _actionItems = [];
  int _sessionGeneration = 0;

  bool _isLoading = false;
  bool _isFetching = false;
  bool _hasMore = false;
  bool _loadedPageSetComplete = false;

  bool _includeCompleted = true;

  // UI filter: show completed tasks view
  bool _showCompletedView = false;

  // Date range filter
  DateTime? _startDate;
  DateTime? _endDate;

  // Debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 30);

  // Debounced persistence for sort order and indent level
  final Map<String, int> _pendingSortUpdates = {};
  final Map<String, int> _pendingIndentUpdates = {};
  Timer? _layoutDebounce;

  // Multi-selection state
  bool _isSelectionMode = false;
  Set<String> _selectedItems = {};

  // IDs of action items that have been optimistically deleted but whose server
  // delete may still be in flight. Guarded against re-insertion by fetch/load.
  final Set<String> _pendingDeletionIds = {};

  // Optimistic creates waiting on the server, and creates that settled while a
  // wholesale list fetch was still in flight. Such a fetch's response predates
  // the create and cannot contain it; the settled row stays shadowed until
  // every fetch that was in flight at settle time has applied its replacement.
  final Map<String, ActionItemWithMetadata> _pendingCreates = {};
  final Map<String, (ActionItemWithMetadata, Set<int>)> _fetchShadowedCreates = {};
  // Server-confirmed rows carrying a settled edit (complete/description/due
  // date) that wholesale fetches already in flight predate: their responses
  // hold the pre-edit version and would silently revert the user's change.
  // The edit survives exactly the replacements of the fetches that were in
  // flight when the mutation settled; later fetches see it server-side.
  final Map<String, (ActionItemWithMetadata, Set<int>)> _fetchShadowedEdits = {};
  // Final server ids of creates that were preserved into the visible list but
  // have not yet been observed inside any server page response. They stay out
  // of the pagination offset until the server confirms them, so loadMore never
  // skips a server row.
  final Set<String> _preservedCreateIds = {};
  // Local sort-order/indent-level changes that the server has not confirmed
  // yet. While an entry is uncommitted (pendingThreats == null) every wholesale
  // replacement re-applies it: any fetch response received before the batch
  // write lands can predate it. Once the write commits, the entry survives only
  // the fetches that were in flight at commit time (their reads may predate
  // the write); later fetches see the layout server-side and win.
  final Map<String, ({int? sortOrder, int? indentLevel, Set<int>? pendingThreats})> _uncommittedLayout = {};
  // Monotonic revision of staged layout edits per id. Each debounced batch
  // snapshots the values it submitted; a batch response may only settle the
  // revision it carried, never a newer edit the user staged while the older
  // request was awaiting its response (Codex PRRT sTqip).
  final Map<String, int> _layoutRevisions = {};
  // Monotonic revision of completion (done/undone) mutations per id. Rapid
  // toggles can have their PATCH responses resolve out of order; only the
  // latest attempt for an item may settle its row, register its fetch
  // shadow, or revert the visible state. Mirrors [_layoutRevisions]
  // (Codex PRRT sf5P9).
  final Map<String, int> _completionMutationRevisions = {};
  int _layoutRevisionCounter = 0;
  int _wholesaleListFetchOrdinal = 0;
  final Set<int> _wholesaleFetchesInFlight = {};

  /// Count of server-backed rows in [_actionItems] for pagination: preserved
  /// optimistic/shadowed creates are excluded until a server response has
  /// contained them, so `loadMoreActionItems` never skips a server task.
  int get _serverBackedRowCount {
    if (_pendingCreates.isEmpty && _fetchShadowedCreates.isEmpty && _preservedCreateIds.isEmpty) {
      return _actionItems.length;
    }
    return _actionItems
        .where(
          (item) =>
              !_pendingCreates.containsKey(item.id) &&
              !_fetchShadowedCreates.containsKey(item.id) &&
              !_preservedCreateIds.contains(item.id),
        )
        .length;
  }

  /// Merges optimistic creates into [fetched] so a wholesale list replacement
  /// cannot drop a create the response predates. [fetchOrdinal] identifies the
  /// replacing fetch: a shadowed row survives exactly the replacements of the
  /// fetches that were in flight when it settled. Later fetches see the row
  /// server-side and their replacements are authoritative without it.
  List<ActionItemWithMetadata> _withPendingCreates(
    List<ActionItemWithMetadata> fetched, {
    required int fetchOrdinal,
  }) {
    final fetchedIds = fetched.map((item) => item.id).toSet();
    // A server page observing a preserved create confirms it server-side; it
    // now counts as server-backed for pagination. Retirement must precede the
    // nothing-to-preserve early return below: the common settle path (a create
    // that landed with no fetch in flight) leaves only _preservedCreateIds
    // populated, and skipping retirement would exclude that row from the
    // pagination offset forever.
    _preservedCreateIds.removeWhere(fetchedIds.contains);
    // This replacement has applied, and any shadowed ordinal that is no longer
    // in flight either applied or aborted without replacing the list; neither
    // can drop its shadowed row anymore. Fetches still in flight remain threats.
    final stillThreatening = {..._wholesaleFetchesInFlight}..remove(fetchOrdinal);
    final List<ActionItemWithMetadata> merged;
    if (_pendingCreates.isEmpty && _fetchShadowedCreates.isEmpty) {
      merged = fetched;
    } else {
      // A row the user has deleted — staged behind an Undo toast or deleted
      // outright — must not be resurrected by preservation: its pending-deletion
      // tombstone deliberately outlives this replacement (the server delete may
      // still be in flight), and the server-side filter above already dropped
      // the row from `fetched`.
      final hidden = _pendingDeletionIds;
      final preserved = <ActionItemWithMetadata>[
        for (final entry in _fetchShadowedCreates.entries)
          if (entry.value.$2.contains(fetchOrdinal) && !fetchedIds.contains(entry.key) && !hidden.contains(entry.key))
            entry.value.$1,
        for (final entry in _pendingCreates.entries)
          if (!fetchedIds.contains(entry.key) && !hidden.contains(entry.key)) entry.value,
      ];
      _fetchShadowedCreates.updateAll(
        (_, shadow) => (shadow.$1, shadow.$2.intersection(stillThreatening)),
      );
      _fetchShadowedCreates.removeWhere((_, shadow) => shadow.$2.isEmpty);
      merged = [...preserved, ...fetched];
    }
    // Layout reapply must run after edit shadows: a shadow row (settled
    // completion/description edit) may itself carry a pre-layout-write
    // sortOrder/indentLevel, and the user's live layout wins over both.
    return _withUncommittedLayout(
      _withFetchShadowedEdits(
        merged,
        fetchOrdinal: fetchOrdinal,
        stillThreatening: stillThreatening,
      ),
      fetchOrdinal: fetchOrdinal,
      stillThreatening: stillThreatening,
    );
  }

  /// Re-applies settled edits over [rows]. A wholesale replacement whose fetch
  /// was in flight when the edit settled holds the pre-edit server version;
  /// substituting the edited row keeps the user's completed/edited task from
  /// reverting until another refresh. Fetches that started after the mutation
  /// settled see the edit server-side, so their rows stay authoritative.
  List<ActionItemWithMetadata> _withFetchShadowedEdits(
    List<ActionItemWithMetadata> rows, {
    required int fetchOrdinal,
    required Set<int> stillThreatening,
  }) {
    if (_fetchShadowedEdits.isEmpty) return rows;
    final reapplied = List<ActionItemWithMetadata>.of(rows);
    for (var i = 0; i < reapplied.length; i++) {
      final shadow = _fetchShadowedEdits[reapplied[i].id];
      if (shadow != null && shadow.$2.contains(fetchOrdinal)) {
        reapplied[i] = shadow.$1;
      }
    }
    _fetchShadowedEdits.updateAll(
      (_, shadow) => (shadow.$1, shadow.$2.intersection(stillThreatening)),
    );
    _fetchShadowedEdits.removeWhere((_, shadow) => shadow.$2.isEmpty);
    return reapplied;
  }

  /// Records that [row] carries a settled mutation the wholesale fetches
  /// currently in flight predate. Called with the server-confirmed row right
  /// after the mutation request succeeds, before any further awaits, so a
  /// threat fetch completing in between cannot miss the shadow.
  void _registerFetchShadowedEdit(ActionItemWithMetadata row) {
    if (_wholesaleFetchesInFlight.isEmpty) return;
    _fetchShadowedEdits[row.id] = (row, {..._wholesaleFetchesInFlight});
  }

  /// Merges the visible row's layout into the settled row of a non-layout
  /// mutation (completion/description/due date). Such a mutation never moves
  /// the task in the hierarchy, but its echo may omit sort_order/indent_level
  /// — the wire schema defaults both to 0 — so splicing the echo or
  /// re-applying it as a fetch shadow would flatten the indent the list
  /// already shows (hub #4: completing a task never changes its indent).
  /// Layout truth keeps flowing from list fetches and layout mutations.
  ActionItemWithMetadata _withVisibleLayout(
    String id,
    ActionItemWithMetadata settled,
  ) {
    final visibleIndex = _actionItems.indexWhere((i) => i.id == id);
    if (visibleIndex == -1) return settled;
    final visible = _actionItems[visibleIndex];
    if (visible.sortOrder == settled.sortOrder && visible.indentLevel == settled.indentLevel) {
      return settled;
    }
    return settled.copyWith(
      sortOrder: visible.sortOrder,
      indentLevel: visible.indentLevel,
    );
  }

  /// Re-applies not-yet-confirmed sort-order/indent-level changes over [rows],
  /// after edit shadows. Drag-reorder and indent mutations update the visible
  /// rows immediately but only reach the server after the debounce; a fetch
  /// response predating the write holds the old layout and would snap the
  /// hierarchy back. Runs after [_withFetchShadowedEdits] because a shadow row
  /// (settled completion/description edit) may itself carry a pre-layout-write
  /// sortOrder/indentLevel; the user's live layout wins over both.
  List<ActionItemWithMetadata> _withUncommittedLayout(
    List<ActionItemWithMetadata> rows, {
    required int fetchOrdinal,
    required Set<int> stillThreatening,
  }) {
    if (_uncommittedLayout.isEmpty) return rows;
    final reapplied = List<ActionItemWithMetadata>.of(rows);
    for (var i = 0; i < reapplied.length; i++) {
      final row = reapplied[i];
      final entry = _uncommittedLayout[row.id];
      if (entry == null) continue;
      // An uncommitted entry (null threats) applies to every replacement: any
      // fetch response received before the batch write lands can predate it.
      // A settled entry applies only to the fetches in flight at commit time.
      if (entry.pendingThreats != null && !entry.pendingThreats!.contains(fetchOrdinal)) {
        continue;
      }
      if (row.sortOrder == entry.sortOrder && row.indentLevel == entry.indentLevel) {
        continue;
      }
      reapplied[i] = row.copyWith(
        sortOrder: entry.sortOrder,
        indentLevel: entry.indentLevel,
      );
    }
    // This replacement has applied, and any ordinal no longer in flight either
    // applied or aborted without replacing the list; neither can revert the
    // layout anymore. Fetches still in flight remain threats.
    _uncommittedLayout.updateAll((id, entry) {
      final threats = entry.pendingThreats;
      if (threats == null) return entry;
      final remaining = threats.intersection(stillThreatening);
      if (remaining.length == threats.length) return entry;
      return (
        sortOrder: entry.sortOrder,
        indentLevel: entry.indentLevel,
        pendingThreats: remaining,
      );
    });
    _uncommittedLayout.removeWhere(
      (_, entry) => entry.pendingThreats != null && entry.pendingThreats!.isEmpty,
    );
    return reapplied;
  }

  /// Marks [id]'s layout fields as unconfirmed so wholesale fetch replacements
  /// predating the debounced batch write cannot revert them. Values already in
  /// the visible rows carry over unchanged (null keeps them via copyWith).
  void _stageUncommittedLayout(String id, {int? sortOrder, int? indentLevel}) {
    final existing = _uncommittedLayout[id];
    _uncommittedLayout[id] = (
      sortOrder: sortOrder ?? existing?.sortOrder,
      indentLevel: indentLevel ?? existing?.indentLevel,
      pendingThreats: null,
    );
    _layoutRevisions[id] = ++_layoutRevisionCounter;
  }

  /// The batch write for [ids] settled. Success: later fetches see the layout
  /// server-side, so the entries survive only the fetches still in flight
  /// (their reads may predate the write) and then retire. Failure: the server
  /// kept the old layout, but the local rows already show what the user
  /// arranged — retire without re-applying so a later refresh restores truth.
  /// Settlement applies only to the revision each id carried when this batch
  /// was submitted; a newer edit staged while the request was in flight stays
  /// uncommitted and keeps protecting the visible rows.
  void _settleUncommittedLayout(
    Map<String, int> submittedRevisions, {
    required bool committed,
  }) {
    for (final id in submittedRevisions.keys) {
      final entry = _uncommittedLayout[id];
      if (entry == null) continue;
      // A newer revision exists: this response settles only the older one.
      if (_layoutRevisions[id] != submittedRevisions[id]) continue;
      if (!committed || _wholesaleFetchesInFlight.isEmpty) {
        _uncommittedLayout.remove(id);
        _layoutRevisions.remove(id);
      } else {
        _uncommittedLayout[id] = (
          sortOrder: entry.sortOrder,
          indentLevel: entry.indentLevel,
          pendingThreats: {..._wholesaleFetchesInFlight},
        );
      }
    }
  }

  /// Drops [ordinal] from every shadow's threat set. An aborted wholesale
  /// fetch (e.g. a Home preview that lost the navigation race) never runs its
  /// `_withPendingCreates` replacement, so its ordinal must be pruned by the
  /// aborting caller's `finally` — otherwise the shadow keeps excluding a
  /// server-confirmed row from `_serverBackedRowCount` forever.
  void _dropFetchShadowOrdinal(int ordinal) {
    if (_fetchShadowedCreates.isNotEmpty) {
      _fetchShadowedCreates.updateAll(
        (_, shadow) => (shadow.$1, shadow.$2.difference({ordinal})),
      );
      _fetchShadowedCreates.removeWhere((_, shadow) => shadow.$2.isEmpty);
    }
    if (_fetchShadowedEdits.isNotEmpty) {
      _fetchShadowedEdits.updateAll(
        (_, shadow) => (shadow.$1, shadow.$2.difference({ordinal})),
      );
      _fetchShadowedEdits.removeWhere((_, shadow) => shadow.$2.isEmpty);
    }
    if (_uncommittedLayout.isNotEmpty) {
      _uncommittedLayout.updateAll((_, entry) {
        final threats = entry.pendingThreats;
        if (threats == null) return entry;
        final remaining = threats.difference({ordinal});
        return (
          sortOrder: entry.sortOrder,
          indentLevel: entry.indentLevel,
          pendingThreats: remaining,
        );
      });
      _uncommittedLayout.removeWhere(
        (_, entry) => entry.pendingThreats != null && entry.pendingThreats!.isEmpty,
      );
    }
  }

  // Single-task deletes waiting for their Undo toast to close (docs/ux-contract.md §4): hidden
  // from every list, not yet deleted on the server.
  final Map<String, ({ActionItemWithMetadata item, int index, int homeIndex})> _stagedDeletes = {};

  // Temp-id → confirmed server id for staged deletes that were re-keyed when
  // their optimistic create settled mid-toast: the Undo toast captured the temp
  // id, so undo/commit resolve through this alias to reach the transferred
  // staged delete.
  final Map<String, String> _stagedDeleteAliasIds = {};

  // Optimistic creates captured by an in-flight bulk delete while still on
  // their temp id. The bulk endpoint cannot delete a temp id, so the captured
  // rows are excluded from the bulk request and deleted by follow-up single
  // deletes of their confirmed server ids once the creates settle.
  final Map<String, _CapturedBulkDeleteCreate> _bulkDeleteCaptures = {};

  // Search state — lexical client-side filter over already-loaded items.
  // Backend vector search will replace the filter implementation behind
  // the same getters in a follow-up PR.
  String _searchQuery = '';

  // Getters
  List<ActionItemWithMetadata> get actionItems => _actionItems;
  ApiViewState<List<ActionItemWithMetadata>> get apiViewState => _listViewState;

  @visibleForTesting
  bool get usesTypedActionItemsApi => _actionItemsApi != null;
  bool get isLoading => _isLoading;
  bool get isFetching => _isFetching;

  /// A bounded snapshot is ready for Home widgets, or the Tasks list has loaded.
  bool get hasLoaded => _initialLoadCompleted || _homeWidgetRefreshedAt != null;

  /// The Tasks screen's own full initialization, separate from [hasLoaded]:
  /// Home's bounded widget preview can complete (zero tasks) without this
  /// screen ever running [ensureLoaded], and the screen must still shimmer
  /// through its authoritative first load instead of flashing the empty state.
  bool get screenLoaded => _initialLoadCompleted;
  bool get hasMore => _hasMore;
  bool get includeCompleted => _includeCompleted;
  bool get showCompletedView => _showCompletedView;
  DateTime? get startDate => _startDate;
  DateTime? get endDate => _endDate;
  bool get hasActiveFilter => _startDate != null || _endDate != null;

  /// Home preview: due-window rows plus any first-page matches, so an empty
  /// due-window response cannot hide a task already on the global first page.
  List<ActionItemWithMetadata> todayPreviewTasks({
    DateTime? now,
    int limit = 3,
  }) {
    final clock = now ?? DateTime.now();
    final byId = <String, ActionItemWithMetadata>{};
    for (final item in filterTodayTasks(_actionItems, now: clock)) {
      byId[item.id] = item;
    }
    if (_homeDayLoaded) {
      for (final item in filterTodayTasks(_homeDayItems, now: clock)) {
        byId[item.id] = item;
      }
    }
    return byId.values.take(limit).toList();
  }

  static List<ActionItemWithMetadata> filterTodayTasks(
    List<ActionItemWithMetadata> items, {
    required DateTime now,
  }) {
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
    final sevenDaysAgo = now.subtract(const Duration(days: 7));
    return items.where((item) {
      if (item.completed) return false;
      if (item.dueAt == null) return false;
      if (item.dueAt!.isBefore(sevenDaysAgo)) return false;
      return item.dueAt!.isBefore(startOfTomorrow);
    }).toList();
  }

  // Selection getters
  bool get isSelectionMode => _isSelectionMode;
  Set<String> get selectedItems => _selectedItems;
  int get selectedCount => _selectedItems.length;
  bool get hasSelection => _selectedItems.isNotEmpty;

  // Search getters
  String get searchQuery => _searchQuery;
  bool get isSearching => _searchQuery.isNotEmpty;

  /// Items matching the active search query, or all items when no query is set.
  /// Lexical case-insensitive substring match on description.
  List<ActionItemWithMetadata> get filteredActionItems {
    if (_searchQuery.isEmpty) return _actionItems;
    final q = _searchQuery.toLowerCase();
    return _actionItems.where((i) => i.description.toLowerCase().contains(q)).toList();
  }

  // Group action items by completion status
  List<ActionItemWithMetadata> get incompleteItems => _actionItems.where((item) => item.completed == false).toList();

  List<ActionItemWithMetadata> get completedItems => _actionItems.where((item) => item.completed == true).toList();

  // New categorization with 3-day cutoff for tabs
  List<ActionItemWithMetadata> get todoItems {
    final now = DateTime.now();
    final threeDaysAgo = now.subtract(const Duration(days: 3));

    return _actionItems.where((item) {
      if (item.completed) return false;

      // Check if within 3 days based on due_at or created_at
      if (item.dueAt != null) {
        return item.dueAt!.isAfter(threeDaysAgo) || item.dueAt!.isAtSameMomentAs(threeDaysAgo);
      } else if (item.createdAt != null) {
        return item.createdAt!.isAfter(threeDaysAgo) || item.createdAt!.isAtSameMomentAs(threeDaysAgo);
      }

      // If no dates, include in To Do by default
      return true;
    }).toList();
  }

  List<ActionItemWithMetadata> get doneItems {
    return _actionItems.where((item) => item.completed == true).toList();
  }

  List<ActionItemWithMetadata> get snoozedItems {
    final now = DateTime.now();
    final threeDaysAgo = now.subtract(const Duration(days: 3));

    return _actionItems.where((item) {
      if (item.completed) return false;

      // Check if past 3 days based on due_at or created_at
      if (item.dueAt != null) {
        return item.dueAt!.isBefore(threeDaysAgo);
      } else if (item.createdAt != null) {
        return item.createdAt!.isBefore(threeDaysAgo);
      }

      // If no dates, don't include in snoozed
      return false;
    }).toList();
  }

  /// Full Tasks initialization is demand-driven and coalesced across callers.
  Future<void> ensureLoaded({bool showShimmer = false}) {
    if (_initialLoadCompleted) return Future.value();
    final existingLoad = _initialLoad;
    if (existingLoad != null) {
      // A non-screen caller (Chat task card) started this load without a
      // shimmer. If the Tasks screen joins while it is still in flight, the
      // empty list would otherwise render the false empty state for the rest
      // of the request: upgrade the presentation to the screen shimmer.
      if (showShimmer && !_isLoading) {
        final joinGeneration = _sessionGeneration;
        setLoading(true);
        existingLoad.whenComplete(() {
          // Generation-fence like every other completion in this provider:
          // this callback belongs to the account that joined the load, and
          // clearUserData() already reset _isLoading for a successor account
          // whose shimmer must survive this stale completion.
          if (joinGeneration == _sessionGeneration && _isLoading) setLoading(false);
        });
      }
      return existingLoad;
    }
    final generation = _sessionGeneration;
    final load = fetchActionItems(showShimmer: showShimmer).then((loaded) {
      if (generation != _sessionGeneration) return;
      _initialLoadCompleted = loaded;
    });
    _initialLoad = load.whenComplete(() {
      if (generation == _sessionGeneration) _initialLoad = null;
    });
    return _initialLoad!;
  }

  /// Home widgets consume a cached first-page snapshot (the same 100-row bound
  /// as before). This does not initialize screen filters, pagination, migration
  /// or authoritative Siri reconciliation. Freshness has its own cooldown.
  Future<void> ensureHomeWidgetPreviewLoaded() {
    if (_initialLoad != null) return _initialLoad!;
    if (_initialLoadCompleted) {
      // Once the Tasks screen has loaded, the preview fetch can no longer
      // apply its replacement (it yields to screen initialization), so a
      // resume-time freshness call must not dead-end here: refresh the
      // authoritative list under the shared 30 s cooldown instead. The
      // publisher listens to this provider, so the widget follows.
      return refreshActionItems();
    }
    if (_homeWidgetLoad != null) return _homeWidgetLoad!;
    final refreshedAt = _homeWidgetRefreshedAt;
    if (refreshedAt != null && DateTime.now().difference(refreshedAt) < _refreshCooldown) {
      return Future.value();
    }
    final generation = _sessionGeneration;
    final load = _fetchHomeWidgetPreview(generation).whenComplete(() {
      if (generation == _sessionGeneration) _homeWidgetLoad = null;
    });
    _homeWidgetLoad = load;
    return load;
  }

  Future<void> _fetchHomeWidgetPreview(int generation) async {
    // Register before the await: same wholesale-replacement semantics as
    // fetchActionItems for optimistic creates that settle mid-flight.
    final fetchOrdinal = ++_wholesaleListFetchOrdinal;
    _wholesaleFetchesInFlight.add(fetchOrdinal);
    try {
      final response = await _fetchActionItemsPage(limit: 100, offset: 0);
      // Navigation wins if Tasks was visited while this optional read was pending.
      if (generation != _sessionGeneration || _initialLoad != null || _initialLoadCompleted) {
        return;
      }
      if (response == null) return;
      _actionItems = _withPendingCreates(
        response.actionItems.where((item) => !_pendingDeletionIds.contains(item.id)).take(100).toList(),
        fetchOrdinal: fetchOrdinal,
      );
      _homeWidgetRefreshedAt = DateTime.now();
      // Home widgets mirror only confirmed rows; optimistic temp rows have no
      // stable server identity yet.
      final indexableRows = _pendingCreates.isEmpty
          ? _actionItems
          : _actionItems.where((item) => !_pendingCreates.containsKey(item.id)).toList();
      SiriIntegration.current.queueUpsertTasks(indexableRows);
      notifyListeners();
    } catch (e) {
      Logger.debug('Error fetching home widget task preview: $e');
    } finally {
      _wholesaleFetchesInFlight.remove(fetchOrdinal);
      // This preview applied or aborted without replacing the list; either way
      // it can no longer drop a shadowed row. An aborted preview never ran
      // _withPendingCreates, so prune its ordinal here or the shadow keeps
      // excluding a server-confirmed row from the pagination offset forever.
      _dropFetchShadowOrdinal(fetchOrdinal);
    }
  }

  /// Home asks only for incomplete tasks due in the visible window, instead of
  /// paging the whole task history. Does not replace `_actionItems`.
  Future<void> ensureHomeTodayTasksLoaded({DateTime? now}) {
    final existing = _homeTodayLoad;
    if (existing != null) return existing;
    if (_homeDayLoaded) return Future.value();

    final load = _fetchHomeTodayTasks(now: now ?? DateTime.now()).whenComplete(
      () {
        _homeTodayLoad = null;
      },
    );
    _homeTodayLoad = load;
    return load;
  }

  Future<void> _fetchHomeTodayTasks({required DateTime now}) async {
    final generation = _sessionGeneration;
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
    final sevenDaysAgo = now.subtract(const Duration(days: 7));
    try {
      final response = await _fetchActionItemsPage(
        limit: 100,
        offset: 0,
        completed: false,
        dueStartDate: sevenDaysAgo,
        dueEndDate: startOfTomorrow.subtract(const Duration(microseconds: 1)),
      );
      if (response != null && generation == _sessionGeneration) {
        _homeDayItems = _pendingDeletionIds.isEmpty
            ? List.of(response.actionItems)
            : response.actionItems.where((item) => !_pendingDeletionIds.contains(item.id)).toList();
        SiriIntegration.current.queueUpsertTasks(_homeDayItems);
        _homeDayLoaded = true;
      }
    } catch (e) {
      Logger.debug('Error fetching home today tasks: $e');
    }
    notifyListeners();
  }

  /// One-time migration: convert SharedPreferences taskCategoryOrder to sort_order on items
  Future<void> _migrateCategoryOrderFromPrefs() async {
    final savedOrder = SharedPreferencesUtil().taskCategoryOrder;
    if (savedOrder.isEmpty) return;

    final Map<String, int> sortUpdates = {};
    for (final entry in savedOrder.entries) {
      final ids = entry.value;
      for (int i = 0; i < ids.length; i++) {
        sortUpdates[ids[i]] = (i + 1) * 1000;
      }
    }

    if (sortUpdates.isNotEmpty) {
      batchUpdateSortOrders(sortUpdates);
      // Clear old prefs after migration
      SharedPreferencesUtil().taskCategoryOrder = {};
    }
  }

  void setLoading(bool value) {
    _isLoading = value;
    notifyListeners();
  }

  void setFetching(bool value) {
    _isFetching = value;
    notifyListeners();
  }

  static bool shouldAutoRevealCompleted(List<ActionItemWithMetadata> items) =>
      items.isNotEmpty && items.every((item) => item.completed);

  /// Shared list fetch. A typed outage returns null so Home today and
  /// load-more keep existing rows instead of looking like an empty account.
  Future<ActionItemsResponse?> _fetchActionItemsPage({
    required int limit,
    required int offset,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
    void Function(ApiResult<ActionItemsResponse> typed)? onTyped,
  }) async {
    final typedApi = _actionItemsApi;
    if (typedApi != null) {
      final typed = await typedApi.list(
        limit: limit,
        offset: offset,
        completed: completed,
        conversationId: conversationId,
        startDate: startDate,
        endDate: endDate,
        dueStartDate: dueStartDate,
        dueEndDate: dueEndDate,
      );
      onTyped?.call(typed);
      return switch (typed) {
        ApiSuccess(:final data) => data,
        ApiFailure() => null,
      };
    }
    return _getActionItems(
      limit: limit,
      offset: offset,
      completed: completed,
      conversationId: conversationId,
      startDate: startDate,
      endDate: endDate,
      dueStartDate: dueStartDate,
      dueEndDate: dueEndDate,
    );
  }

  Future<bool> fetchActionItems({bool showShimmer = false}) async {
    final generation = _sessionGeneration;
    // Register before any await: optimistic creates that settle while this
    // wholesale fetch is in flight must survive its list replacement.
    final fetchOrdinal = ++_wholesaleListFetchOrdinal;
    _wholesaleFetchesInFlight.add(fetchOrdinal);
    var decodedPageIsComplete = true;
    var loaded = false;
    if (showShimmer) {
      setLoading(true);
    } else {
      setFetching(true);
    }

    try {
      final response = await _fetchActionItemsPage(
        limit: 100,
        offset: 0,
        completed: _includeCompleted ? null : false,
        startDate: _startDate,
        endDate: _endDate,
        onTyped: (result) {
          // A fetch started before sign-out must not project its outcome onto
          // the next account's screen state.
          if (generation != _sessionGeneration) return;
          _projectTypedList(result);
          if (result case ApiSuccess(:final rejectedRows, :final truncated)) {
            decodedPageIsComplete = rejectedRows == 0 && !truncated;
          }
        },
      );
      if (response != null && generation == _sessionGeneration) {
        _loadedPageSetComplete = decodedPageIsComplete && !response.truncated && _pendingDeletionIds.isEmpty;
        await _applyFetchedActionItems(
          response,
          decodedPageIsComplete: decodedPageIsComplete,
          fetchOrdinal: fetchOrdinal,
        );
        if (generation != _sessionGeneration) return false;
        await _migrateCategoryOrderFromPrefs();
        if (generation != _sessionGeneration) return false;
        _initialLoadCompleted = true;
        loaded = true;
      }
    } catch (e) {
      Logger.debug('Error fetching action items: $e');
    } finally {
      _wholesaleFetchesInFlight.remove(fetchOrdinal);
      // Null response (typed outage), discarded after sign-out, or thrown:
      // this fetch never runs its _withPendingCreates replacement, so its
      // ordinal must be pruned here exactly like the Home preview abort —
      // otherwise a shadow keeps excluding a server-confirmed row from the
      // pagination offset forever.
      _dropFetchShadowOrdinal(fetchOrdinal);
      // Only the owning generation may retire the loading flags; a stale
      // completion would hide the successor account's shimmer/fetch state.
      if (generation == _sessionGeneration) {
        if (showShimmer) {
          setLoading(false);
        } else {
          setFetching(false);
        }
      }
    }

    if (generation == _sessionGeneration) notifyListeners();
    return loaded;
  }

  void _projectTypedList(ApiResult<ActionItemsResponse> result) {
    _listViewState = presentApiResult(
      switch (result) {
        ApiSuccess(:final data, :final rejectedRows) => ApiSuccess(
            data.actionItems,
            rejectedRows: rejectedRows,
          ),
        ApiFailure(:final problem) => ApiFailure<List<ActionItemWithMetadata>>(
            problem,
          ),
      },
      previous: _actionItems.isNotEmpty ? _actionItems : null,
      isEmpty: (rows) => rows.isEmpty,
      fallback: recordFallback,
    );
  }

  Future<void> _applyFetchedActionItems(
    ActionItemsResponse response, {
    required bool decodedPageIsComplete,
    required int fetchOrdinal,
  }) async {
    // Snapshot server IDs before filtering so tombstone retirement is
    // based on the full server response, not the filtered subset.
    final serverIds = response.actionItems.map((e) => e.id).toSet();
    // Filter into a new list rather than mutating response.actionItems
    // in-place: the response list may be unmodifiable, and aliasing it
    // would cause removeWhere to throw in deleteActionItem/deleteSelectedItems
    // and retire tombstones prematurely.
    _actionItems = _withPendingCreates(
      _pendingDeletionIds.isEmpty
          ? List.of(response.actionItems)
          : response.actionItems.where((item) => !_pendingDeletionIds.contains(item.id)).toList(),
      fetchOrdinal: fetchOrdinal,
    );
    // Lazily retire tombstones once the server confirms the item is gone:
    // any ID still tracked as pending-deletion that did not appear in the
    // fresh server response can be cleared, because subsequent refreshes
    // will no longer see it.
    if (_pendingDeletionIds.isNotEmpty &&
        !response.hasMore &&
        !hasActiveFilter &&
        _includeCompleted &&
        decodedPageIsComplete &&
        !response.truncated) {
      _pendingDeletionIds.removeWhere(
        (id) => !_stagedDeletes.containsKey(id) && !serverIds.contains(id),
      );
    }
    _hasMore = response.hasMore;
    // The Siri/Spotlight mirror never sees optimistic temp rows: their final
    // server identity is still unknown, and reconcile/upsert with a temp id
    // would leak an undeletable Spotlight entry until the next refresh.
    final indexableRows = _pendingCreates.isEmpty
        ? _actionItems
        : _actionItems.where((item) => !_pendingCreates.containsKey(item.id)).toList();
    // A rejected wire row or a staged delete is still present on the server.
    // Neither can be interpreted as an authoritative absence in Spotlight.
    if (!_hasMore && !hasActiveFilter && _loadedPageSetComplete && !response.truncated && _pendingDeletionIds.isEmpty) {
      SiriIntegration.current.queueReconcileTasks(
        indexableRows,
        includeCompleted: _includeCompleted,
      );
    } else {
      SiriIntegration.current.queueUpsertTasks(indexableRows);
    }

    if (!_showCompletedView && shouldAutoRevealCompleted(_actionItems)) {
      _showCompletedView = true;
    }
  }

  Future<void> loadMoreActionItems() async {
    if (_isFetching || !_hasMore) return;
    final generation = _sessionGeneration;

    setFetching(true);

    try {
      var decodedPageIsComplete = true;
      final response = await _fetchActionItemsPage(
        limit: 50,
        offset: _serverBackedRowCount,
        completed: _includeCompleted ? null : false,
        startDate: _startDate,
        endDate: _endDate,
        onTyped: (result) {
          if (result case ApiSuccess(:final rejectedRows, :final truncated)) {
            decodedPageIsComplete = rejectedRows == 0 && !truncated;
          }
        },
      );

      if (response != null && generation == _sessionGeneration) {
        _loadedPageSetComplete =
            _loadedPageSetComplete && decodedPageIsComplete && !response.truncated && _pendingDeletionIds.isEmpty;
        // A load-more page observing a preserved create confirms it server-side;
        // it now counts as server-backed for pagination. Retire from the full
        // server response, not the deduped/filtered subset — mirroring
        // _withPendingCreates retirement. Without this, a create ordered beyond
        // the initial page stays excluded from the offset forever and can stall
        // pagination on already-visible rows.
        _preservedCreateIds.removeWhere(
          response.actionItems.map((item) => item.id).toSet().contains,
        );
        // An optimistic delete shortens the visible list before the server removes the row.
        // Its length can therefore request an overlapping page; keep each server ID once.
        final seenIds = _actionItems.map((item) => item.id).toSet();
        final filtered = response.actionItems
            .where(
              (item) => !_pendingDeletionIds.contains(item.id) && seenIds.add(item.id),
            )
            .toList();
        _actionItems.addAll(filtered);
        _hasMore = response.hasMore;
        if (!_hasMore &&
            !hasActiveFilter &&
            _loadedPageSetComplete &&
            !response.truncated &&
            _pendingDeletionIds.isEmpty) {
          SiriIntegration.current.queueReconcileTasks(
            _actionItems,
            includeCompleted: _includeCompleted,
          );
        } else {
          SiriIntegration.current.queueUpsertTasks(filtered);
        }
      }
    } catch (e) {
      Logger.debug('Error loading more action items: $e');
    } finally {
      // A stale load-more from a signed-out generation must not clear the
      // successor account's fetch state (or admit an overlapping pagination
      // request while it runs): only the owning generation may reset it.
      if (generation == _sessionGeneration) {
        setFetching(false);
      }
    }

    if (generation == _sessionGeneration) notifyListeners();
  }

  /// Returns whether the change reached the server; the caller decides what to tell the user.
  Future<bool> updateActionItemState(
    ActionItemWithMetadata item,
    bool newState,
  ) async {
    final generation = _sessionGeneration;
    // A newer completion attempt on the same item supersedes this one: only
    // the latest attempt may settle the row, register its fetch shadow, or
    // revert the visible state when its own request fails.
    final mutationRevision = (_completionMutationRevisions[item.id] ?? 0) + 1;
    _completionMutationRevisions[item.id] = mutationRevision;
    bool isLatestCompletionAttempt() =>
        _completionMutationRevisions[item.id] == mutationRevision && generation == _sessionGeneration;
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.taskMutation,
      surface: ProductSurface.tasks,
      objectId: RecordReference.fromId(item.id),
    );
    try {
      final itemInList = _findAndUpdateItemState(item.id, newState);
      if (itemInList != null) {
        notifyListeners();
      }

      final success = await _updateActionItemRequest(
        item.id,
        completed: newState,
      );
      if (generation != _sessionGeneration) {
        attempt.complete(ProductOutcome.cancelled);
        return false;
      }

      if (success == null) {
        if (isLatestCompletionAttempt()) {
          _findAndUpdateItemState(item.id, !newState);
          notifyListeners();
          Logger.debug('Failed to update action item state on server');
        }
        attempt.complete(
          ProductOutcome.failure,
          failure: ProductFailure.server,
        );
        return false;
      }
      // The mutation is committed server-side; wholesale fetches still in
      // flight predate it and would revert this row in their replacement.
      // The echo of a completed-only mutation is not layout-authoritative,
      // so keep the hierarchy the visible row already shows.
      final settled = _withVisibleLayout(success.id, success);
      // A superseded response must not register a fetch shadow either: it
      // would protect the stale pre-newer-toggle state from wholesale fetches
      // that will return the up-to-date row.
      if (isLatestCompletionAttempt()) {
        _registerFetchShadowedEdit(settled);
      }
      // A wholesale fetch that already applied while this mutation was
      // awaiting its response retired its ordinal before the shadow could be
      // registered, so the visible row may still hold the pre-mutation state.
      // Splice the confirmed server row back in — the same settle behavior
      // the description and due-date edits already have.
      final settledIndex = _actionItems.indexWhere((i) => i.id == success.id);
      if (isLatestCompletionAttempt() && settledIndex != -1) {
        _actionItems[settledIndex] = settled;
        notifyListeners();
      }
      if (isLatestCompletionAttempt()) {
        // External projections (Siri donations, Apple Reminders) must not
        // receive the superseded state either; the newer attempt pushes its
        // own confirmed row when it settles.
        SiriIntegration.current.queueUpsertTasks([settled]);
      }
      // Cancel notification if the action item is marked as completed
      if (newState == true) {
        await ActionItemNotificationHandler.cancelNotification(item.id);
      }
      if (generation != _sessionGeneration) {
        attempt.complete(ProductOutcome.cancelled);
        return false;
      }
      if (isLatestCompletionAttempt()) {
        _pushUpdateToAppleReminder(item, completed: newState);
      }
      attempt.complete(ProductOutcome.success);
      if (newState) {
        unawaited(SiriIntegration.current.donateUiAction('task', item.id));
        ProductTelemetry.instance.value(
          ProductValue.taskCompleted,
          surface: ProductSurface.tasks,
          objectId: RecordReference.fromId(item.id),
        );
      }
      return true;
    } catch (e) {
      if (generation != _sessionGeneration) {
        attempt.complete(ProductOutcome.cancelled);
        return false;
      }
      if (isLatestCompletionAttempt()) {
        _findAndUpdateItemState(item.id, !newState);
        notifyListeners();
      }
      Logger.debug('Error updating action item state: $e');
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.network);
      return false;
    }
  }

  /// Returns whether the change reached the server; the caller decides what to tell the user.
  Future<bool> updateActionItemDescription(
    ActionItemWithMetadata item,
    String newDescription,
  ) async {
    final generation = _sessionGeneration;
    try {
      final itemInList = _findAndUpdateItemDescription(item.id, newDescription);
      if (itemInList != null) {
        notifyListeners();
      }

      final updatedItem = await _updateActionItemRequest(
        item.id,
        description: newDescription,
      );
      if (generation != _sessionGeneration) return false;

      if (updatedItem == null) {
        // Revert on failure
        _findAndUpdateItemDescription(item.id, item.description);
        notifyListeners();
        Logger.debug('Failed to update action item description on server');
        return false;
      }
      // Update the local item with server response
      final index = _actionItems.indexWhere((i) => i.id == item.id);
      if (index != -1) {
        _actionItems[index] = _withVisibleLayout(updatedItem.id, updatedItem);
        notifyListeners();
      }
      // Wholesale fetches in flight predate this committed edit.
      _registerFetchShadowedEdit(_withVisibleLayout(updatedItem.id, updatedItem));
      SiriIntegration.current.queueUpsertTasks([updatedItem]);
      _pushUpdateToAppleReminder(item, title: newDescription);
      return true;
    } catch (e) {
      if (generation != _sessionGeneration) return false;
      _findAndUpdateItemDescription(item.id, item.description);
      notifyListeners();
      Logger.debug('Error updating action item description: $e');
      return false;
    }
  }

  /// Returns whether the change reached the server; the caller decides what to tell the user.
  Future<bool> updateActionItemDueDate(
    ActionItemWithMetadata item,
    DateTime? dueDate,
  ) async {
    final generation = _sessionGeneration;
    // Optimistic update: update locally first for instant UI feedback
    final index = _actionItems.indexWhere((i) => i.id == item.id);
    ActionItemWithMetadata? originalItem;
    if (index != -1) {
      originalItem = _actionItems[index];
      _actionItems[index] = ActionItemWithMetadata(
        id: originalItem.id,
        description: originalItem.description,
        completed: originalItem.completed,
        createdAt: originalItem.createdAt,
        updatedAt: originalItem.updatedAt,
        dueAt: dueDate,
        completedAt: originalItem.completedAt,
        conversationId: originalItem.conversationId,
        isLocked: originalItem.isLocked,
        exported: originalItem.exported,
        exportDate: originalItem.exportDate,
        exportPlatform: originalItem.exportPlatform,
        sortOrder: originalItem.sortOrder,
        indentLevel: originalItem.indentLevel,
      );
      notifyListeners();
    }

    try {
      final updatedItem = await _updateDueDateRequest(
        item.id,
        dueAt: dueDate,
        clearDueAt: dueDate == null,
      );
      if (generation != _sessionGeneration) return false;

      if (updatedItem != null) {
        final idx = _actionItems.indexWhere((i) => i.id == item.id);
        if (idx != -1) {
          _actionItems[idx] = _withVisibleLayout(updatedItem.id, updatedItem);
          notifyListeners();
        }
        // Wholesale fetches in flight predate this committed edit.
        _registerFetchShadowedEdit(_withVisibleLayout(updatedItem.id, updatedItem));
        SiriIntegration.current.queueUpsertTasks([updatedItem]);
        _pushUpdateToAppleReminder(item, dueDate: dueDate);
        return true;
      } else {
        // Revert on failure — re-find index in case list changed during await
        if (originalItem != null) {
          final revertIdx = _actionItems.indexWhere((i) => i.id == item.id);
          if (revertIdx != -1) {
            _actionItems[revertIdx] = originalItem;
            notifyListeners();
          }
        }
        Logger.debug('Failed to update action item due date on server');
        return false;
      }
    } catch (e) {
      if (generation != _sessionGeneration) return false;
      // Revert on error — re-find index in case list changed during await
      if (originalItem != null) {
        final revertIdx = _actionItems.indexWhere((i) => i.id == item.id);
        if (revertIdx != -1) {
          _actionItems[revertIdx] = originalItem;
          notifyListeners();
        }
      }
      Logger.debug('Error updating action item due date: $e');
      return false;
    }
  }

  Future<int> clearTodayDeadlinesForIncompleteTasks() async {
    final generation = _sessionGeneration;
    final now = DateTime.now();
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);

    final itemsToClear = _actionItems.where((item) {
      final dueAt = item.dueAt;
      if (item.completed || dueAt == null) return false;
      // Keep clean behavior aligned with the tasks listed under "Today" in UI.
      return dueAt.isBefore(startOfTomorrow);
    }).toList();

    if (itemsToClear.isEmpty) return 0;

    final originalItemsById = <String, ActionItemWithMetadata>{};
    for (final item in itemsToClear) {
      final index = _actionItems.indexWhere((i) => i.id == item.id);
      if (index != -1) {
        originalItemsById[item.id] = _actionItems[index];
        _actionItems[index] = _actionItems[index].copyWith(dueAt: null);
      }
    }
    notifyListeners();

    int successCount = 0;
    for (final item in itemsToClear) {
      try {
        final updatedItem = await _updateDueDateRequest(
          item.id,
          clearDueAt: true,
        );
        if (generation != _sessionGeneration) return successCount;

        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (updatedItem != null) {
          if (index != -1) {
            _actionItems[index] = _withVisibleLayout(updatedItem.id, updatedItem);
          }
          // Wholesale fetches in flight predate this committed edit.
          _registerFetchShadowedEdit(_withVisibleLayout(updatedItem.id, updatedItem));
          SiriIntegration.current.queueUpsertTasks([updatedItem]);
          successCount++;
        } else if (index != -1) {
          final originalItem = originalItemsById[item.id];
          if (originalItem != null) {
            _actionItems[index] = originalItem;
          }
        }
      } catch (e) {
        if (generation != _sessionGeneration) return successCount;
        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (index != -1) {
          final originalItem = originalItemsById[item.id];
          if (originalItem != null) {
            _actionItems[index] = originalItem;
          }
        }
        Logger.debug('Error clearing today deadline for item ${item.id}: $e');
      }
    }

    notifyListeners();
    return successCount;
  }

  Future<bool> deleteActionItem(ActionItemWithMetadata item) async {
    final generation = _sessionGeneration;
    // Delete linked Apple Reminder if one exists
    _deleteAppleReminderIfLinked(item);

    // Track as pending-deletion so any background refresh doesn't re-insert it
    // while the server delete is in flight.
    _pendingDeletionIds.add(item.id);

    // Remove immediately to prevent dismissed Dismissible from being rebuilt
    final index = _actionItems.indexWhere(
      (actionItem) => actionItem.id == item.id,
    );
    _actionItems.removeWhere((actionItem) => actionItem.id == item.id);
    notifyListeners();

    try {
      final success = await _deleteActionItemRequest(item.id);
      if (generation != _sessionGeneration) return false;

      if (!success) {
        Logger.debug('Failed to delete action item on server');
        // On failure, remove from pending set so a future reload can re-fetch it
        _pendingDeletionIds.remove(item.id);
        _restoreDeletedItem(item, index);
      } else {
        SiriIntegration.current.queueDelete('task', item.id);
      }
      // On success, the tombstone is intentionally retained: a refresh that
      // started before the server processed the deletion may still return the
      // deleted item. It is cleaned up lazily in fetchActionItems() once the
      // server confirms the item is gone.
      return success;
    } catch (e) {
      if (generation != _sessionGeneration) return false;
      Logger.debug('Error deleting action item: $e');
      // On error, remove from pending set so a future reload can re-fetch it
      _pendingDeletionIds.remove(item.id);
      _restoreDeletedItem(item, index);
      return false;
    }
  }

  /// Hides [item] from the Tasks list and Home at once and holds its server delete until
  /// [commitStagedDelete]; [undoStagedDelete] puts it back where it was. Every single-task delete
  /// goes through this so it can offer Undo (D5) — see `deleteTaskWithUndo`.
  void stageDeleteActionItem(ActionItemWithMetadata item) {
    if (_stagedDeletes.containsKey(item.id)) return;
    _pendingDeletionIds.add(item.id);
    final index = _actionItems.indexWhere((i) => i.id == item.id);
    final homeIndex = _homeDayItems.indexWhere((i) => i.id == item.id);
    _actionItems.removeWhere((i) => i.id == item.id);
    _homeDayItems.removeWhere((i) => i.id == item.id);
    _selectedItems.remove(item.id);
    _stagedDeletes[item.id] = (item: item, index: index, homeIndex: homeIndex);
    notifyListeners();
  }

  /// Restores a task hidden by [stageDeleteActionItem]. False when it was not staged (already
  /// committed or restored).
  Future<bool> undoStagedDelete(String id) async {
    final resolvedId = _stagedDeleteAliasIds[id] ?? id;
    _stagedDeleteAliasIds.remove(id);
    final staged = _stagedDeletes.remove(resolvedId);
    if (staged == null) return false;
    _pendingDeletionIds.remove(resolvedId);
    if (!_actionItems.any((i) => i.id == resolvedId)) {
      _actionItems.insert(
        (staged.index == -1 ? 0 : staged.index).clamp(0, _actionItems.length),
        staged.item,
      );
    }
    if (staged.homeIndex != -1 && !_homeDayItems.any((i) => i.id == resolvedId)) {
      _homeDayItems.insert(
        staged.homeIndex.clamp(0, _homeDayItems.length),
        staged.item,
      );
    }
    notifyListeners();
    SiriIntegration.current.queueUpsertTasks([
      staged.item,
    ], restoreDeleted: true);
    return true;
  }

  /// Deletes a task hidden by [stageDeleteActionItem] on the server. On failure the task comes
  /// back where it was. False when it was not staged.
  Future<bool> commitStagedDelete(String id) async {
    final generation = _sessionGeneration;
    final resolvedId = _stagedDeleteAliasIds[id] ?? id;
    _stagedDeleteAliasIds.remove(id);
    final staged = _stagedDeletes.remove(resolvedId);
    if (staged == null) return false;
    _deleteAppleReminderIfLinked(staged.item);
    var success = false;
    try {
      success = await _deleteActionItemRequest(resolvedId);
    } catch (e) {
      Logger.debug('Error deleting action item: $e');
    }
    if (generation != _sessionGeneration) return false;
    if (!success) {
      _pendingDeletionIds.remove(resolvedId);
      _restoreDeletedItem(staged.item, staged.index);
      if (staged.homeIndex != -1 && !_homeDayItems.any((i) => i.id == resolvedId)) {
        _homeDayItems.insert(
          staged.homeIndex.clamp(0, _homeDayItems.length),
          staged.item,
        );
        notifyListeners();
      }
    } else {
      SiriIntegration.current.queueDelete('task', resolvedId);
    }
    return success;
  }

  @visibleForTesting
  bool isDeleteStaged(String id) => _stagedDeletes.containsKey(id);

  void _restoreDeletedItem(ActionItemWithMetadata item, int index) {
    if (index == -1 || _actionItems.any((actionItem) => actionItem.id == item.id)) {
      return;
    }
    _actionItems.insert(index.clamp(0, _actionItems.length), item);
    notifyListeners();
  }

  Future<ActionItemWithMetadata?> createActionItem({
    required String description,
    DateTime? dueAt,
    String? conversationId,
    bool completed = false,
  }) async {
    final generation = _sessionGeneration;
    final optimisticItem = ActionItemWithMetadata(
      id: 'temp_${DateTime.now().millisecondsSinceEpoch}',
      description: description,
      completed: completed,
      dueAt: dueAt,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      conversationId: conversationId,
    );

    // Track the optimistic row so a concurrent list fetch (demand load, Home
    // preview) that started before this create cannot drop it from the UI.
    _pendingCreates[optimisticItem.id] = optimisticItem;
    _actionItems.insert(0, optimisticItem);
    notifyListeners();

    try {
      final newItem = await _createActionItemRequest(
        description: description,
        dueAt: dueAt,
        conversationId: conversationId,
        completed: completed,
      );
      if (generation != _sessionGeneration) {
        _settlePendingCreate(optimisticItem.id, null);
        return null;
      }

      if (newItem != null) {
        _settlePendingCreate(optimisticItem.id, newItem);
        // A bulk delete captured this create while it was still a temp row.
        // The bulk endpoint cannot delete a temp id, so the capture was kept
        // out of the bulk request; transfer the deletion intent to the
        // confirmed server id and complete it with a single follow-up delete.
        // Without this the code below would reinsert the confirmed row — the
        // task reappears even though the user bulk-deleted it.
        final capture = _bulkDeleteCaptures.remove(optimisticItem.id);
        if (capture != null) {
          _pendingDeletionIds
            ..remove(optimisticItem.id)
            ..add(newItem.id);
          _actionItems.removeWhere((item) => item.id == newItem.id);
          _homeDayItems.removeWhere((item) => item.id == newItem.id);
          _selectedItems.remove(newItem.id);
          notifyListeners();
          unawaited(_completeCapturedDelete(newItem, capture));
          return newItem;
        }
        // The user staged a delete of the temp row while the create was in
        // flight (D5 undo toast). Do not resurrect what the user deleted:
        // transfer the staged deletion to the confirmed server id so Undo
        // restores the confirmed row and commit deletes it server-side,
        // instead of reinserting it here and leaving the staged temp entry
        // to later restore a duplicate.
        final stagedDelete = _stagedDeletes.remove(optimisticItem.id);
        if (stagedDelete != null) {
          _pendingDeletionIds
            ..remove(optimisticItem.id)
            ..add(newItem.id);
          _stagedDeletes[newItem.id] = (
            item: newItem,
            index: stagedDelete.index,
            homeIndex: stagedDelete.homeIndex,
          );
          // The open toast still addresses the temp id; resolve it to the
          // transferred staged delete.
          _stagedDeleteAliasIds[optimisticItem.id] = newItem.id;
          // A concurrent fetch may have observed the confirmed row before
          // this create settled and admitted it into the visible lists (the
          // tombstone still held only the temp id then). The staged state is
          // hidden by contract: remove the confirmed row everywhere a fresh
          // stageDeleteActionItem would, so it does not reappear during the
          // Undo window or outlive a successful commit.
          _actionItems.removeWhere((item) => item.id == newItem.id);
          _homeDayItems.removeWhere((item) => item.id == newItem.id);
          _selectedItems.remove(newItem.id);
          // Keep newItem.id in _preservedCreateIds: no server page has
          // observed the created row yet, so it must not shift the pagination
          // offset. If Undo restores it, the normal page-observed retirement
          // applies; if commit deletes it, the stale id is inert (the row is
          // no longer in _actionItems).
          notifyListeners();
          return newItem;
        }
        // The server row replaces the temp row wherever it sits; if an
        // interleaved list response already dropped the temp row, re-insert
        // the confirmed row so the create is never lost from the UI. A
        // concurrent list response may have observed the committed row before
        // this create settled, so drop any earlier copy of the same server id
        // instead of leaving a duplicate.
        _actionItems.removeWhere(
          (item) => item.id == newItem.id && item.id != optimisticItem.id,
        );
        final index = _actionItems.indexWhere(
          (item) => item.id == optimisticItem.id,
        );
        if (index != -1) {
          _actionItems[index] = newItem;
        } else {
          _actionItems.insert(0, newItem);
        }
        notifyListeners();
        // Direct sync to Apple Reminders — no FCM roundtrip needed
        _syncToAppleRemindersIfNeeded(newItem);
        SiriIntegration.current.queueUpsertTasks([newItem]);
        return newItem;
      } else {
        _settlePendingCreate(optimisticItem.id, null);
        _actionItems.removeWhere((item) => item.id == optimisticItem.id);
        // The create never reached the server: the user's staged delete of the
        // temp row has nothing to commit. Dissolve it (and its tombstone) so
        // commitStagedDelete does not fire a server delete of an id that was
        // never created, and Undo does not resurrect the dead temp row.
        _dissolveStagedDeleteForFailedCreate(optimisticItem.id);
        notifyListeners();
        Logger.debug('Failed to create action item on server');
        return null;
      }
    } catch (e) {
      _settlePendingCreate(optimisticItem.id, null);
      if (generation != _sessionGeneration) return null;
      _actionItems.removeWhere((item) => item.id == optimisticItem.id);
      _dissolveStagedDeleteForFailedCreate(optimisticItem.id);
      notifyListeners();
      Logger.debug('Error creating action item: $e');
      return null;
    }
  }

  /// Removes a staged delete whose optimistic create failed: there is no
  /// server row to delete or restore, so the staged entry and its tombstone
  /// must go away entirely.
  void _dissolveStagedDeleteForFailedCreate(String tempId) {
    _stagedDeleteAliasIds.remove(tempId);
    final staged = _stagedDeletes.remove(tempId);
    if (staged != null) {
      _pendingDeletionIds.remove(tempId);
    }
    // A bulk delete captured the temp row. The create never reached the
    // server, so there is no confirmed row to follow up on: the capture and
    // its tombstone dissolve, and the row stays hidden — the user's delete
    // intent stands (the task never existed).
    if (_bulkDeleteCaptures.remove(tempId) != null) {
      _pendingDeletionIds.remove(tempId);
    }
  }

  /// Completes a bulk-deleted optimistic create after its create settled: the
  /// bulk request never saw the temp id, so the confirmed server row is
  /// deleted directly. On failure the row is restored where the user deleted
  /// it from and the tombstone retires, matching deleteActionItem's behavior.
  Future<void> _completeCapturedDelete(
    ActionItemWithMetadata row,
    _CapturedBulkDeleteCreate capture,
  ) async {
    final generation = _sessionGeneration;
    _deleteAppleReminderIfLinked(row);
    var success = false;
    try {
      success = await _deleteActionItemRequest(row.id);
    } catch (e) {
      Logger.debug('Error deleting captured create: $e');
    }
    if (generation != _sessionGeneration) return;
    if (!success) {
      _pendingDeletionIds.remove(row.id);
      _restoreDeletedItem(row, capture.index);
      if (capture.homeIndex != -1 && !_homeDayItems.any((i) => i.id == row.id)) {
        _homeDayItems.insert(
          capture.homeIndex.clamp(0, _homeDayItems.length),
          row,
        );
      }
      notifyListeners();
    } else {
      SiriIntegration.current.queueDelete('task', row.id);
    }
  }

  /// Settles an optimistic create. [settledRow] is the confirmed server row,
  /// or null when the create failed and the temp row was removed. If wholesale
  /// fetches were in flight, their responses predate the create; the row stays
  /// shadowed until each of those fetches has applied its replacement.
  void _settlePendingCreate(String tempId, ActionItemWithMetadata? settledRow) {
    _pendingCreates.remove(tempId);
    if (settledRow == null) return;
    // A concurrent fetch may have already observed the committed row and
    // placed it in the visible list before this create settled (its
    // retirement ran when the id was not preserved yet, so nothing retired).
    // A server page has contained the row: it is server-backed immediately
    // and must not be excluded from the pagination offset until some later
    // page happens to retire it.
    final alreadyObserved = _actionItems.any(
      (item) => item.id == settledRow.id,
    );
    if (!alreadyObserved) {
      // The settled row stays out of the pagination offset until a server page
      // response has contained it: the pages the demand load fetched may not
      // include it yet, and counting it would skip a server row in loadMore.
      _preservedCreateIds.add(settledRow.id);
    }
    if (_wholesaleFetchesInFlight.isEmpty) return;
    // Register the fetch threats even when the row is currently hidden (the
    // user staged a delete of it while the create was in flight): if Undo
    // later restores the row, those older in-flight responses must still not
    // drop it. Deletion intent is enforced at replacement time inside
    // _withPendingCreates via _pendingDeletionIds, so a committed delete never
    // resurrects the row while an Undo before the fetch returns re-arms it.
    _fetchShadowedCreates[settledRow.id] = (
      settledRow,
      {..._wholesaleFetchesInFlight},
    );
  }

  /// Directly create an Apple Reminder without waiting for FCM roundtrip.
  /// Fire-and-forget — doesn't block the UI.
  void _syncToAppleRemindersIfNeeded(ActionItemWithMetadata item) {
    if (!PlatformService.isApple) return;

    final service = AppleRemindersService();
    if (!service.isAvailable) return;

    () async {
      try {
        if (!await service.hasPermission()) return;

        final calendarItemId = await service.addReminder(
          title: item.description,
          notes: 'From Omi',
          dueDate: item.dueAt,
        );

        if (calendarItemId != null) {
          await api.updateActionItem(
            item.id,
            exported: true,
            exportPlatform: 'apple_reminders',
            appleReminderId: calendarItemId,
          );
          PlatformManager.instance.analytics.appleReminderDirectSync(
            actionItemId: item.id,
          );
        }
      } catch (e) {
        Logger.debug('Direct Apple Reminders sync failed: $e');
      }
    }();
  }

  /// Push a field update to the linked Apple Reminder immediately.
  void _pushUpdateToAppleReminder(
    ActionItemWithMetadata item, {
    bool? completed,
    String? title,
    DateTime? dueDate,
  }) {
    if (!PlatformService.isApple) return;
    if (item.appleReminderId == null || item.appleReminderId!.isEmpty) return;

    AppleRemindersService().updateReminderById(
      item.appleReminderId!,
      completed: completed,
      title: title,
      dueDate: dueDate,
    );
  }

  /// Delete the linked Apple Reminder when action item is deleted.
  void _deleteAppleReminderIfLinked(ActionItemWithMetadata item) {
    if (!PlatformService.isApple) return;
    if (item.appleReminderId == null || item.appleReminderId!.isEmpty) return;

    AppleRemindersService().deleteReminderById(item.appleReminderId!);
    PlatformManager.instance.analytics.appleReminderDeleted(
      actionItemId: item.id,
    );
  }

  // Sort order and indent level persistence

  void _updateItemInPlace(String id, {int? sortOrder, int? indentLevel}) {
    final index = _actionItems.indexWhere((item) => item.id == id);
    if (index != -1) {
      _actionItems[index] = _actionItems[index].copyWith(
        sortOrder: sortOrder,
        indentLevel: indentLevel,
      );
    }
  }

  void updateItemSortOrder(String id, int sortOrder) {
    _updateItemInPlace(id, sortOrder: sortOrder);
    _pendingSortUpdates[id] = sortOrder;
    _stageUncommittedLayout(id, sortOrder: sortOrder);
    notifyListeners();
    _scheduleLayoutFlush();
  }

  void updateItemIndentLevel(String id, int indentLevel) {
    _updateItemInPlace(id, indentLevel: indentLevel);
    _pendingIndentUpdates[id] = indentLevel;
    _stageUncommittedLayout(id, indentLevel: indentLevel);
    notifyListeners();
    _scheduleLayoutFlush();
  }

  void batchUpdateSortOrders(Map<String, int> updates) {
    for (final entry in updates.entries) {
      _updateItemInPlace(entry.key, sortOrder: entry.value);
      _pendingSortUpdates[entry.key] = entry.value;
      _stageUncommittedLayout(entry.key, sortOrder: entry.value);
    }
    notifyListeners();
    _scheduleLayoutFlush();
  }

  /// Both layout fields share one debounce and one batch request: a drag that
  /// changes a row's order and indent must commit atomically, and the shared
  /// revision must not be settled by whichever single-field flush would have
  /// finished first (Codex PRRT sZ2hW).
  void _scheduleLayoutFlush() {
    _layoutDebounce?.cancel();
    _layoutDebounce = Timer(const Duration(milliseconds: 500), _flushLayoutUpdates);
  }

  Future<void> _flushLayoutUpdates() async {
    if (_pendingSortUpdates.isEmpty && _pendingIndentUpdates.isEmpty) return;
    final sortUpdates = Map<String, int>.from(_pendingSortUpdates);
    final indentUpdates = Map<String, int>.from(_pendingIndentUpdates);
    _pendingSortUpdates.clear();
    _pendingIndentUpdates.clear();

    final ids = {...sortUpdates.keys, ...indentUpdates.keys};
    // One item per id carrying whichever fields changed; the batch endpoint
    // accepts both fields in a single entry.
    final items = [
      for (final id in ids)
        {
          'id': id,
          if (sortUpdates[id] != null) 'sort_order': sortUpdates[id],
          if (indentUpdates[id] != null) 'indent_level': indentUpdates[id],
        },
    ];
    // Snapshot each id's revision before the await: the response may only
    // settle the values this batch actually submitted. (Every pending update
    // was staged with a revision; ids without one have nothing to settle.)
    final submitted = {
      for (final id in ids)
        if (_layoutRevisions[id] != null) id: _layoutRevisions[id]!,
    };
    final committed = await _batchUpdateActionItemsRequest(items);
    _settleUncommittedLayout(submitted, committed: committed);
  }

  ActionItemWithMetadata? _findAndUpdateItemState(
    String itemId,
    bool newState,
  ) {
    ActionItemWithMetadata? updated;
    final mainIndex = _actionItems.indexWhere((item) => item.id == itemId);
    if (mainIndex != -1) {
      _actionItems[mainIndex] = _actionItems[mainIndex].copyWith(
        completed: newState,
      );
      updated = _actionItems[mainIndex];
    }
    final homeIndex = _homeDayItems.indexWhere((item) => item.id == itemId);
    if (homeIndex != -1) {
      _homeDayItems[homeIndex] = _homeDayItems[homeIndex].copyWith(
        completed: newState,
      );
      updated ??= _homeDayItems[homeIndex];
    }
    return updated;
  }

  ActionItemWithMetadata? _findAndUpdateItemDescription(
    String itemId,
    String newDescription,
  ) {
    final mainIndex = _actionItems.indexWhere((item) => item.id == itemId);
    if (mainIndex != -1) {
      _actionItems[mainIndex] = _actionItems[mainIndex].copyWith(
        description: newDescription,
      );
      return _actionItems[mainIndex];
    }

    return null;
  }

  void toggleCompletedActionItems() {
    _includeCompleted = !_includeCompleted;
    fetchActionItems(showShimmer: true);
    // TODO: Add analytics for completed action items toggle
  }

  void toggleShowCompletedView() {
    _showCompletedView = !_showCompletedView;
    notifyListeners();
  }

  void setDateRangeFilter(DateTime? startDate, DateTime? endDate) {
    _startDate = startDate;
    _endDate = endDate;
    fetchActionItems(showShimmer: true);
  }

  void clearDateRangeFilter() {
    _startDate = null;
    _endDate = null;
    fetchActionItems(showShimmer: true);
  }

  Future<void> refreshActionItems() async {
    final now = DateTime.now();
    if (_lastRefreshTime != null && now.difference(_lastRefreshTime!) < _refreshCooldown) {
      Logger.debug(
        'Skipping action items refresh - too soon since last refresh',
      );
      return;
    }

    _refreshDebounceTimer?.cancel();
    _refreshDebounceTimer = Timer(const Duration(milliseconds: 500), () {
      _lastRefreshTime = DateTime.now();
      _fetchNewActionItems();
    });
  }

  /// Force refresh bypassing debounce
  Future<void> forceRefreshActionItems() async {
    _refreshDebounceTimer?.cancel();
    _lastRefreshTime = DateTime.now();
    await _fetchNewActionItems();
  }

  Future<void> _fetchNewActionItems() async {
    await fetchActionItems();
  }

  // Selection methods
  void startSelection() {
    _isSelectionMode = true;
    _selectedItems.clear();
    notifyListeners();
  }

  void endSelection() {
    _isSelectionMode = false;
    _selectedItems.clear();
    notifyListeners();
  }

  /// Cascades the toggle to [cascadeIds] — typically the parent's visible
  /// descendants computed at the call site (the page has the category-grouped
  /// display order; the provider does not). Pass an empty list for a leaf row.
  void toggleItemSelection(
    String itemId, {
    Iterable<String> cascadeIds = const [],
  }) {
    final wasSelected = _selectedItems.contains(itemId);
    if (wasSelected) {
      _selectedItems.remove(itemId);
      _selectedItems.removeAll(cascadeIds);
    } else {
      _selectedItems.add(itemId);
      _selectedItems.addAll(cascadeIds);
    }
    notifyListeners();
  }

  void selectItem(String itemId) {
    if (!_selectedItems.contains(itemId)) {
      _selectedItems.add(itemId);
      notifyListeners();
    }
  }

  void deselectItem(String itemId) {
    if (_selectedItems.contains(itemId)) {
      _selectedItems.remove(itemId);
      notifyListeners();
    }
  }

  void selectAllItems() {
    _selectedItems
      ..clear()
      ..addAll(_actionItems.map((i) => i.id));
    notifyListeners();
  }

  void selectAllItemsFromTab(int tabIndex) {
    _selectedItems.clear();
    List<ActionItemWithMetadata> itemsToSelect = [];

    switch (tabIndex) {
      case 0:
        itemsToSelect = todoItems;
        break;
      case 1:
        itemsToSelect = doneItems;
        break;
      case 2:
        itemsToSelect = snoozedItems;
        break;
    }

    _selectedItems.addAll(itemsToSelect.map((i) => i.id));
    notifyListeners();
  }

  void clearSelection() {
    _selectedItems.clear();
    notifyListeners();
  }

  void clearUserData() {
    _sessionGeneration++;
    _actionItems = [];
    _loadedPageSetComplete = false;
    _initialLoadCompleted = false;
    _initialLoad = null;
    _homeWidgetLoad = null;
    _homeWidgetRefreshedAt = null;
    _homeDayItems = [];
    _homeDayLoaded = false;
    _homeTodayLoad = null;
    // A fetch from the signed-out generation no longer clears these on
    // completion; reset them here so the next account starts clean.
    _isLoading = false;
    _isFetching = false;
    _listViewState = const ApiViewState(phase: ApiViewPhase.data);
    _selectedItems = {};
    _stagedDeletes.clear();
    _stagedDeleteAliasIds.clear();
    _bulkDeleteCaptures.clear();
    _pendingCreates.clear();
    _fetchShadowedCreates.clear();
    _fetchShadowedEdits.clear();
    _preservedCreateIds.clear();
    _uncommittedLayout.clear();
    _layoutRevisions.clear();
    _completionMutationRevisions.clear();
    // Wholesale fetches from the signed-out generation may still resolve
    // later; their ordinals are dead threats. Clear them so a create in the
    // successor account never records a stale ordinal as a fetch threat —
    // otherwise the confirmed row stays excluded from the pagination offset
    // until the old account's request eventually completes (or forever if it
    // never does).
    _wholesaleFetchesInFlight.clear();
    _pendingSortUpdates.clear();
    _pendingIndentUpdates.clear();
    notifyListeners();
  }

  bool isItemSelected(String itemId) {
    return _selectedItems.contains(itemId);
  }

  // Bulk operations
  Future<bool> deleteSelectedItems({BuildContext? context}) async {
    if (_selectedItems.isEmpty) return false;
    final generation = _sessionGeneration;

    final itemsToDelete = _actionItems.where((item) => _selectedItems.contains(item.id)).toList();
    final ids = itemsToDelete.map((item) => item.id).toList(growable: false);
    // Snapshot positions so a failed bulk delete can re-insert the rows
    // back where the user expected them, instead of dumping them at the end.
    final snapshot = <int, ActionItemWithMetadata>{
      for (final item in itemsToDelete) _actionItems.indexOf(item): item,
    };
    final wasInSelection = _isSelectionMode;

    // Optimistic temp rows among the selection cannot go through the bulk
    // endpoint (it only deletes real ids). Capture them: hide + tombstone now,
    // and delete the confirmed server id with a follow-up single delete once
    // the create settles. The bulk request below only carries real ids.
    for (final item in itemsToDelete) {
      if (!item.id.startsWith('temp_')) continue;
      final homeIndex = _homeDayItems.indexWhere((i) => i.id == item.id);
      _bulkDeleteCaptures[item.id] = _CapturedBulkDeleteCreate(
        tempId: item.id,
        index: _actionItems.indexOf(item),
        homeIndex: homeIndex,
      );
    }
    final bulkIds = [
      for (final id in ids)
        if (!_bulkDeleteCaptures.containsKey(id)) id,
    ];

    // Dismiss UI immediately — don't wait for API
    _actionItems.removeWhere((item) => _selectedItems.contains(item.id));
    // Register all bulk-deleted IDs as pending so a concurrent background
    // fetch cannot reinsert them while the server delete is in flight.
    _pendingDeletionIds.addAll(ids);
    _selectedItems.clear();
    _isSelectionMode = false;
    notifyListeners();

    // Apple Reminders mirror lives client-side, so it still has to fan out
    // per-item. The action-item record itself goes through the bulk endpoint.
    for (final item in itemsToDelete) {
      _deleteAppleReminderIfLinked(item);
    }

    if (bulkIds.isEmpty) {
      // Everything selected was a pending create; each capture settles through
      // its own create request. The bulk request would carry no real ids.
      return true;
    }

    final deleted = await _bulkDeleteActionItemsRequest(bulkIds);
    if (generation != _sessionGeneration) return false;
    if (deleted == null) {
      Logger.debug(
        'bulkDeleteActionItems returned null — rolling back local list',
      );
      // Clear tombstones on rollback so future refreshes don't filter the
      // re-inserted items.
      _pendingDeletionIds.removeAll(bulkIds);
      // Captured creates never joined this request and stay hidden/tombstoned
      // (a pending create settles through its own follow-up delete; a failed
      // create dissolves; an already-settled one now lives under its real id).
      // Nothing here may resurrect a row the user bulk-deleted, so rollback
      // re-inserts only the real ids that were part of this request.
      // Re-insert rows at their original positions, oldest index first.
      final entries = snapshot.entries.where((entry) => !entry.value.id.startsWith('temp_')).toList()
        ..sort((a, b) => a.key.compareTo(b.key));
      for (final entry in entries) {
        final idx = entry.key.clamp(0, _actionItems.length);
        _actionItems.insert(idx, entry.value);
      }
      _isSelectionMode = wasInSelection;
      _selectedItems = bulkIds.toSet();
      notifyListeners();

      if (context != null && context.mounted) {
        OmiFeedback.error(context, context.l10n.bulkDeleteFailed);
      }
      return false;
    }
    final deletedIDs = deleted.toSet();
    for (final id in deletedIDs) {
      SiriIntegration.current.queueDelete('task', id);
    }
    if (deletedIDs.length != bulkIds.length) {
      _pendingDeletionIds.removeAll(
        bulkIds.where((id) => !deletedIDs.contains(id)),
      );
      // Captured temp rows never joined this request (their ids were not
      // sent), so a partial response cannot report them deleted: filter them
      // out exactly like the null-response rollback, or this branch would
      // resurrect a row the user bulk-deleted whose create is still settling.
      final entries = snapshot.entries
          .where((entry) => !deletedIDs.contains(entry.value.id) && !entry.value.id.startsWith('temp_'))
          .toList()
        ..sort((a, b) => a.key.compareTo(b.key));
      for (final entry in entries) {
        _actionItems.insert(
          entry.key.clamp(0, _actionItems.length),
          entry.value,
        );
      }
      notifyListeners();
    }
    return deleted.length == bulkIds.length;
  }

  Future<bool> clearCompletedItems() async {
    final completed = _actionItems.where((item) => item.completed).toList();
    if (completed.isEmpty) return true;

    final results = await Future.wait(
      completed.map((item) => deleteActionItem(item)),
    );
    return results.every((success) => success);
  }

  void startSelectionWithItem(String itemId) {
    _isSelectionMode = true;
    _selectedItems = {itemId};
    notifyListeners();
  }

  // Search methods
  void setSearchQuery(String query) {
    final next = query.trim();
    if (next == _searchQuery) return;
    _searchQuery = next;
    notifyListeners();
  }

  void clearSearchQuery() {
    if (_searchQuery.isEmpty) return;
    _searchQuery = '';
    notifyListeners();
  }

  /// Fan-out export of every currently selected item to [platform].
  /// Snackbar feedback is posted via [context]; selection mode exits when done.
  Future<void> bulkExportSelected(
    BuildContext context,
    TaskIntegrationApp platform,
  ) async {
    if (_selectedItems.isEmpty) return;

    final ids = _selectedItems.toList(growable: false);
    final selected = _actionItems.where((i) => ids.contains(i.id)).toList(growable: false);
    // Exported items can now be selected (Delete shares the bar), but Export
    // itself silently no-ops on them so the user doesn't double-create on the
    // integration side.
    final items = selected.where((i) => !i.exported).toList(growable: false);
    final total = items.length;

    if (total == 0) {
      OmiFeedback.info(context, context.l10n.bulkExportAlreadyExported);
      endSelection();
      return;
    }

    OmiFeedback.progress(context, context.l10n.bulkExportInProgress);

    final results = await Future.wait(
      items.map((i) => ActionItemExportService.export(i, platform)),
    );
    final successCount = results.where((r) => r == ExportResult.success).length;

    // Refresh from server so newly-flipped `exported`/`exportPlatform` fields surface.
    await fetchActionItems();
    endSelection();

    if (!context.mounted) {
      return;
    }
    if (successCount == total) {
      OmiFeedback.confirm(
        context,
        context.l10n.bulkExportSuccess(successCount, platform.displayName),
      );
    } else {
      OmiFeedback.error(
        context,
        context.l10n.bulkExportPartial(
          successCount,
          total,
          platform.displayName,
        ),
      );
    }
  }

  @override
  void dispose() {
    _sessionGeneration++;
    _refreshDebounceTimer?.cancel();
    _layoutDebounce?.cancel();
    _flushLayoutUpdates();
    super.dispose();
  }
}
