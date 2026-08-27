import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/utils/logger.dart';

typedef ConversationListFetcher = Future<({List<ServerConversation> items, bool ok})> Function();
typedef ConversationPageFetcher = Future<({List<ServerConversation> items, bool ok, bool truncated})> Function();
typedef ConversationLifecycleFetcher = Future<({ServerConversation? item, bool ok})> Function(String id);
typedef DailySummariesChecker = Future<bool> Function();
typedef ConversationSearchFetcher = Future<(List<ServerConversation>, int, int)> Function(
  String query, {
  int? page,
  int? limit,
  required bool includeDiscarded,
  DateTime? startDate,
  DateTime? endDate,
  String? speakerId,
});
typedef ConversationDetailsFetcher = Future<ServerConversation?> Function(String conversationId);

/// Day-bucket key for a conversation timestamp, in the viewer's **local** timezone.
///
/// `started_at`/`created_at` arrive as UTC (ISO-8601 `Z`), so bucketing by their raw
/// UTC `year/month/day` filed an early-morning-local conversation under the previous
/// day for any UTC+ viewer — it vanished from the "Today" group even though the
/// local-day date filter still found it (#10198). Truncating the *local* calendar day
/// keeps grouping consistent with the local-day filter and the Today/Yesterday labels.
DateTime conversationLocalDayKey(DateTime timestamp) {
  final local = timestamp.toLocal();
  return DateTime(local.year, local.month, local.day);
}

/// Search results keep server rank: day buckets appear in first-hit order,
/// and items inside a day stay in ranked order (no recency re-sort).
Map<DateTime, List<ServerConversation>> groupSearchResultsPreservingRank(Iterable<ServerConversation> source) {
  final grouped = <DateTime, List<ServerConversation>>{};
  for (final conversation in source) {
    final date = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt);
    grouped.putIfAbsent(date, () => []).add(conversation);
  }
  return grouped;
}

class ConversationProvider extends ChangeNotifier {
  List<ServerConversation> conversations = [];
  List<ServerConversation> searchedConversations = [];
  Map<DateTime, List<ServerConversation>> groupedConversations = {};

  bool isLoadingConversations = false;
  bool showDiscardedConversations = false;
  bool showShortConversations = false;
  int shortConversationThreshold = 0; // in seconds
  bool showStarredOnly = false; // filter to show only starred conversations
  bool showDailySummaries = false; // filter to show daily summaries instead of conversations
  bool hasDailySummaries = false; // whether user has any daily summaries
  DateTime? selectedStartDate;
  DateTime? selectedEndDate;
  String? selectedFolderId;
  String? selectedSpeakerId;

  DateTime? searchStartDate;
  DateTime? searchEndDate;

  String previousQuery = '';
  int totalSearchPages = 1;
  int currentSearchPage = 1;

  // Add debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 60); // Minimum time between refreshes

  List<ServerConversation> processingConversations = [];

  // Per-conversation websocket transition versions. Reconciliation snapshots
  // these before lifecycle probes so a completion/removal for row B cannot
  // suppress an unrelated newly discovered row A.
  final Map<String, int> _processingStateRevisionById = {};

  // Merge functionality state
  Set<String> mergingConversationIds = {};
  bool isSelectionModeActive = false;
  Set<String> selectedConversationIds = {};
  StreamSubscription<MergeCompletedEvent>? _mergeCompletedSubscription;

  final AppReviewService _appReviewService = AppReviewService();

  bool isFetchingConversations = false;

  // True when the last full conversations fetch failed (no response /
  // non-200) rather than legitimately returning zero results. The UI uses
  // this to keep showing a loading state and auto-retry instead of latching
  // "No conversations yet" — e.g. on a cold start where the Firebase auth
  // token wasn't ready yet for the very first request.
  bool conversationsLoadFailed = false;
  Timer? _initialFetchRetryTimer;
  int _initialFetchRetryCount = 0;
  int _sessionGeneration = 0;
  int _conversationFetchRevision = 0;
  int _conversationLoadingRevision = 0;
  static const int _maxInitialFetchRetries = 4;
  // After the fast backoff budget is spent we keep retrying on a slow fixed
  // interval rather than giving up — otherwise a prolonged outage latches the
  // misleading get-started/"No conversations yet" hero for a user who really
  // does have conversations (just an empty local cache + a slow auth/network).
  static const int _slowFetchRetryIntervalSeconds = 15;

  // Lifecycle probes are best-effort checks for processing cards. Bound both
  // backend fan-out and the time they can hold the primary conversation fetch.
  static const int _processingLifecycleMaxConcurrency = 4;
  static const Duration _processingLifecycleDeadline = Duration(seconds: 2);
  static const int _conversationPageSize = 50;
  int _conversationServerOffset = 0;
  bool _conversationServerHasMore = false;
  final Set<String> _conversationServerLoadedIds = {};

  // The empty-state widget should defer to a pending auto-retry so the user
  // doesn't see "No conversations yet" in the gap between backoff attempts.
  bool get isAwaitingInitialFetchRetry => _initialFetchRetryTimer?.isActive ?? false;
  bool get hasActiveSearch => previousQuery.isNotEmpty || selectedSpeakerId != null;
  bool get hasMoreConversations => _conversationServerHasMore;
  int get conversationServerOffset => _conversationServerOffset;

  final ConversationListFetcher? _conversationListFetcher;
  final ConversationLifecycleFetcher _conversationLifecycleFetcher;
  final DailySummariesChecker? _dailySummariesChecker;
  final ConversationSearchFetcher _conversationSearchFetcher;
  final bool Function() _isSignedIn;

  @visibleForTesting
  ConversationDetailsFetcher? conversationDetailsFetcherOverride;

  @visibleForTesting
  ConversationPageFetcher? conversationPageFetcherOverride;

  @visibleForTesting
  Future<bool> Function(String conversationId)? conversationDeleteFetcherOverride;

  ConversationProvider({
    ConversationListFetcher? conversationListFetcher,
    ConversationLifecycleFetcher? conversationLifecycleFetcher,
    DailySummariesChecker? dailySummariesChecker,
    ConversationSearchFetcher? conversationSearchFetcher,
    bool Function()? isSignedIn,
  })  : _conversationListFetcher = conversationListFetcher,
        _conversationLifecycleFetcher = conversationLifecycleFetcher ?? getConversationByIdResult,
        _dailySummariesChecker = dailySummariesChecker,
        _conversationSearchFetcher = conversationSearchFetcher ?? searchConversationsServer,
        _isSignedIn = isSignedIn ?? AuthService.instance.isSignedIn {
    _setupMergeListener();
    _loadSettings();
  }

  void _loadSettings() {
    final prefs = SharedPreferencesUtil();
    showDiscardedConversations = prefs.showDiscardedMemories;
    showShortConversations = prefs.showShortConversations;
    shortConversationThreshold = prefs.shortConversationThreshold;
  }

  void _setupMergeListener() {
    _mergeCompletedSubscription = MergeNotificationHandler.onMergeCompleted.listen((event) {
      onMergeCompleted(event.mergedConversationId, event.removedConversationIds);
    });
  }

  void resetGroupedConvos() {
    groupConversationsByDate();
  }

  void clearUserData() {
    _sessionGeneration++;
    _conversationFetchRevision++;
    conversations = [];
    searchedConversations = [];
    groupedConversations = {};
    processingConversations = [];
    _processingStateRevisionById.clear();
    _conversationServerOffset = 0;
    _conversationServerHasMore = false;
    _conversationServerLoadedIds.clear();
    mergingConversationIds = {};
    selectedConversationIds = {};
    isSelectionModeActive = false;
    showDailySummaries = false;
    hasDailySummaries = false;
    selectedStartDate = null;
    selectedEndDate = null;
    selectedFolderId = null;
    selectedSpeakerId = null;
    searchStartDate = null;
    searchEndDate = null;
    previousQuery = '';
    totalSearchPages = 1;
    currentSearchPage = 1;
    isLoadingConversations = false;
    isFetchingConversations = false;
    conversationsLoadFailed = false;
    _initialFetchRetryTimer?.cancel();
    _initialFetchRetryTimer = null;
    _initialFetchRetryCount = 0;
    memoriesToDelete = {};
    deleteTimestamps = {};
    _refreshDebounceTimer?.cancel();
    _refreshDebounceTimer = null;
    _lastRefreshTime = null;
    notifyListeners();
  }

  Future<void> updateSearchedConvoDetails(String id) async {
    final convo = await (conversationDetailsFetcherOverride?.call(id) ?? getConversationById(id));
    if (convo != null) {
      updateConversationInSortedList(convo);
    } else {
      notifyListeners();
    }
  }

  Future<void> searchConversations(String query, {bool showShimmer = false}) async {
    if (!_isSignedIn()) return;
    if (query.isEmpty && selectedSpeakerId == null) {
      previousQuery = "";
      currentSearchPage = 0;
      totalSearchPages = 0;
      searchedConversations = [];
      groupConversationsByDate();
      return;
    }

    final generation = _sessionGeneration;
    if (showShimmer) {
      setLoadingConversations(true);
    } else {
      setIsFetchingConversations(true);
    }

    previousQuery = query;
    var (convos, current, total) = await _conversationSearchFetcher(
      query,
      includeDiscarded: showDiscardedConversations,
      startDate: searchStartDate,
      endDate: searchEndDate,
      speakerId: selectedSpeakerId,
    );
    if (generation != _sessionGeneration || !_isSignedIn()) return;
    // Search results are ranked by the server, including transcript-match relevance.
    // Re-sorting by recency would bury older spoken-moment matches.
    searchedConversations = convos;
    currentSearchPage = current;
    totalSearchPages = total;
    groupSearchConvosByDate();

    if (showShimmer) {
      setLoadingConversations(false);
    } else {
      setIsFetchingConversations(false);
    }

    notifyListeners();
  }

  Future<void> setSpeakerFilter(String? speakerId) async {
    selectedSpeakerId = speakerId;
    await searchConversations(previousQuery, showShimmer: true);
  }

  Future<void> searchMoreConversations() async {
    if (!_isSignedIn()) return;
    if (totalSearchPages < currentSearchPage + 1) {
      return;
    }
    final generation = _sessionGeneration;
    setLoadingConversations(true);
    var (newConvos, current, total) = await _conversationSearchFetcher(
      previousQuery,
      page: currentSearchPage + 1,
      includeDiscarded: showDiscardedConversations,
      startDate: searchStartDate,
      endDate: searchEndDate,
      speakerId: selectedSpeakerId,
    );
    if (generation != _sessionGeneration || !_isSignedIn()) return;
    searchedConversations.addAll(newConvos);
    totalSearchPages = total;
    currentSearchPage = current;
    groupSearchConvosByDate();
    setLoadingConversations(false);
    notifyListeners();
  }

  int groupedSearchConvoIndex(ServerConversation convo) {
    var convoDate = convo.startedAt ?? convo.createdAt;
    var date = conversationLocalDayKey(convoDate);
    if (groupedConversations.containsKey(date)) {
      return groupedConversations[date]!.indexWhere((element) => element.id == convo.id);
    }
    return -1;
  }

  void addProcessingConversation(ServerConversation conversation) {
    _bumpProcessingStateRevision(conversation.id);
    final existingIndex = processingConversations.indexWhere((item) => item.id == conversation.id);
    if (existingIndex == -1) {
      processingConversations.add(conversation);
    } else {
      // A replayed processing-start event can arrive while reconciliation is
      // waiting. Replace the old snapshot so the UI cannot render a stale
      // duplicate ahead of the live row.
      processingConversations[existingIndex] = conversation;
    }
    notifyListeners();
  }

  void removeProcessingConversation(String conversationId) {
    _bumpProcessingStateRevision(conversationId);
    processingConversations.removeWhere((m) => m.id == conversationId);
    notifyListeners();
  }

  void _bumpProcessingStateRevision(String conversationId) {
    _processingStateRevisionById[conversationId] = (_processingStateRevisionById[conversationId] ?? 0) + 1;
  }

  Map<String, int> _processingStateRevisionSnapshot() => Map<String, int>.from(_processingStateRevisionById);

  void onConversationTap(String conversationId) {
    final idx = conversations.indexWhere((c) => c.id == conversationId);
    if (idx == -1) return;
    var changed = false;
    if (conversations[idx].isNew) {
      conversations[idx].isNew = false;
      changed = true;
    }
    for (final conversation in searchedConversations) {
      if (conversation.id == conversationId && conversation.isNew) {
        conversation.isNew = false;
        changed = true;
      }
    }
    for (final group in groupedConversations.values) {
      for (final conversation in group) {
        if (conversation.id == conversationId && conversation.isNew) {
          conversation.isNew = false;
          changed = true;
        }
      }
    }
    if (changed) {
      // A sync refresh can replace the grouped object while the canonical
      // list still holds the old instance. Update every view by ID without
      // rebuilding and sorting the entire list on a tap.
      notifyListeners();
    }
  }

  void toggleDiscardConversations() {
    showDiscardedConversations = !showDiscardedConversations;
    SharedPreferencesUtil().showDiscardedMemories = showDiscardedConversations;

    // Clear grouped conversations to show shimmer effect while loading
    groupedConversations = {};
    notifyListeners();

    if (hasActiveSearch) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }

    PlatformManager.instance.analytics.showDiscardedMemoriesToggled(showDiscardedConversations);
  }

  void toggleShortConversations() {
    showShortConversations = !showShortConversations;
    SharedPreferencesUtil().showShortConversations = showShortConversations;

    // Clear and refresh to reflect the change
    groupedConversations = {};
    notifyListeners();

    if (hasActiveSearch) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }
  }

  void setShortConversationThreshold(int seconds) {
    shortConversationThreshold = seconds;
    SharedPreferencesUtil().shortConversationThreshold = seconds;

    // Clear and refresh to reflect the change
    groupedConversations = {};
    notifyListeners();

    if (hasActiveSearch) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }
  }

  void toggleStarredFilter() {
    showStarredOnly = !showStarredOnly;
    // Clear daily summaries filter when toggling starred
    if (showStarredOnly) {
      showDailySummaries = false;
    }

    // Clear and refetch conversations to get starred from server
    groupedConversations = {};
    notifyListeners();
    fetchConversations();
  }

  void toggleDailySummaries() {
    showDailySummaries = !showDailySummaries;
    // Clear other filters when showing daily summaries
    if (showDailySummaries) {
      showStarredOnly = false;
      selectedFolderId = null;
    }
    notifyListeners();
  }

  /// Check if user has any daily summaries
  Future<bool> checkHasDailySummaries() async {
    if (!_isSignedIn()) return false;
    final generation = _sessionGeneration;
    final hasSummaries = await (_dailySummariesChecker?.call() ??
        getDailySummaries(limit: 1, offset: 0).then((items) => items.isNotEmpty));
    if (generation != _sessionGeneration || !_isSignedIn()) return false;
    hasDailySummaries = hasSummaries;
    notifyListeners();
    return true;
  }

  /// Filter conversations by folder
  Future<void> filterByFolder(String? folderId) async {
    if (selectedFolderId == folderId) return;
    selectedFolderId = folderId;

    // Clear daily summaries filter when selecting a folder
    showDailySummaries = false;

    // Clear search when applying folder filter
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    groupedConversations = {};
    notifyListeners();

    await fetchConversations();
  }

  void setLoadingConversations(bool value) {
    isLoadingConversations = value;
    notifyListeners();
  }

  Future refreshConversations() async {
    // Debounce mechanism: only refresh if enough time has passed since last refresh
    final now = DateTime.now();
    if (_lastRefreshTime != null && now.difference(_lastRefreshTime!) < _refreshCooldown) {
      Logger.debug(
        'Skipping conversations refresh - too soon since last refresh (${now.difference(_lastRefreshTime!).inSeconds}s ago)',
      );
      return;
    }

    // Cancel any pending refresh
    _refreshDebounceTimer?.cancel();

    // Set debounce timer
    _refreshDebounceTimer = Timer(const Duration(milliseconds: 500), () {
      _lastRefreshTime = DateTime.now();
      _fetchNewConversations();
    });
  }

  // Force refresh bypassing debounce (for manual refresh, connection restored, etc.)
  Future forceRefreshConversations() async {
    _refreshDebounceTimer?.cancel();
    _lastRefreshTime = DateTime.now();
    await _fetchNewConversations();
  }

  Future _fetchNewConversations() async {
    if (!_isSignedIn()) return;
    final generation = _sessionGeneration;
    final fetchRevision = ++_conversationFetchRevision;
    _conversationLoadingRevision = fetchRevision;
    final processingRowsAtStart = _realProcessingConversationsById();
    final processingIdsAtStart = processingRowsAtStart.keys.toSet();
    final processingRevisionsAtStart = _processingStateRevisionSnapshot();
    final conversationsAtStart = <String, ServerConversation>{
      for (final conversation in conversations) conversation.id: conversation,
    };
    setLoadingConversations(true);
    final result = await _getConversationsFromServer();
    if (generation != _sessionGeneration || fetchRevision != _conversationFetchRevision) {
      if (_conversationLoadingRevision == fetchRevision) setLoadingConversations(false);
      return;
    }
    if (!_isSignedIn()) {
      setLoadingConversations(false);
      return;
    }

    // A background/debounced refresh failed (transient network error, token
    // expiry, etc.). Don't treat the empty result as "no new conversations" —
    // keep the existing list untouched; the next refresh trigger will retry.
    if (!result.ok) {
      setLoadingConversations(false);
      return;
    }

    final rawNewConversations = result.items;
    final newConversations = _filterPendingDeletes(rawNewConversations);
    final pageConversationIds = newConversations.map((conversation) => conversation.id).toSet();
    final lifecycleResults = await _loadProcessingLifecycleResults(newConversations, processingIdsAtStart);
    if (generation != _sessionGeneration || fetchRevision != _conversationFetchRevision || !_isSignedIn()) {
      if (_conversationLoadingRevision == fetchRevision) setLoadingConversations(false);
      return;
    }
    _reconcileProcessingConversations(
      lifecycleResults,
      processingIdsAtStart,
      pageConversationIds,
      processingRevisionsAtStart,
      processingRowsAtStart,
    );
    if (_conversationServerOffset == 0) {
      _conversationServerOffset = rawNewConversations.length;
      _conversationServerHasMore = !result.truncated && rawNewConversations.length >= _conversationPageSize;
    }
    _conversationServerLoadedIds.addAll(rawNewConversations.map((conversation) => conversation.id));
    final currentlyProcessingIds = processingConversations
        .where((conversation) => _isActiveProcessingStatus(conversation.status))
        .map((conversation) => conversation.id)
        .toSet();

    // A lifecycle probe can be newer than the stale refresh page (for example,
    // the page still says processing while the detail endpoint says completed).
    // Publish those authoritative completed details through the same upsert
    // path as page completions.
    final completedById = <String, ServerConversation>{
      for (final conversation in newConversations)
        if (conversation.status == ConversationStatus.completed && !currentlyProcessingIds.contains(conversation.id))
          conversation.id: conversation,
    };
    for (final lifecycleResult in lifecycleResults.values) {
      final conversation = lifecycleResult.item;
      if (!lifecycleResult.ok ||
          conversation == null ||
          conversation.status != ConversationStatus.completed ||
          currentlyProcessingIds.contains(conversation.id) ||
          memoriesToDelete.containsKey(conversation.id) ||
          !_matchesActiveConversationFilters(conversation)) {
        continue;
      }
      completedById[conversation.id] = conversation;
    }
    for (final conversation in completedById.values) {
      final index = conversations.indexWhere((existing) => existing.id == conversation.id);
      if (index == -1) {
        conversations.insert(0, conversation);
      } else if (identical(conversationsAtStart[conversation.id], conversations[index])) {
        conversations[index] = conversation;
      }
    }
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));

    _groupConversationsByDateWithoutNotify();
    // Keep pagination blocked until lifecycle reconciliation and the final
    // list assignment are complete. [getMoreConversationsFromServer] uses
    // this loading state as its serialization guard.
    setLoadingConversations(false);
    notifyListeners();
  }

  Future<bool> fetchConversations() async {
    if (!_isSignedIn()) {
      _cancelInitialFetchRetry();
      conversationsLoadFailed = false;
      return false;
    }
    final generation = _sessionGeneration;
    final fetchRevision = ++_conversationFetchRevision;
    _conversationLoadingRevision = fetchRevision;
    final conversationsAtStart = <String, ServerConversation>{
      for (final conversation in conversations) conversation.id: conversation,
    };
    final processingRowsAtStart = _realProcessingConversationsById();
    final processingIdsAtStart = processingRowsAtStart.keys.toSet();
    final processingRevisionsAtStart = _processingStateRevisionSnapshot();
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    setLoadingConversations(true);
    final result = await _getConversationsFromServer();
    if (generation != _sessionGeneration || fetchRevision != _conversationFetchRevision) {
      if (_conversationLoadingRevision == fetchRevision) setLoadingConversations(false);
      _cancelInitialFetchRetry();
      return false;
    }
    if (!_isSignedIn()) {
      setLoadingConversations(false);
      _cancelInitialFetchRetry();
      return false;
    }

    if (!result.ok) {
      // The request failed (no response / non-200) — most commonly the auth
      // token not being ready for the very first request after a cold start.
      // Do NOT overwrite what we have with an empty list or latch the
      // "No conversations yet" state: keep the cache (if any) and auto-retry
      // so the list self-heals without the user having to pull-to-refresh.
      conversationsLoadFailed = true;
      if (conversations.isEmpty && selectedFolderId == null) {
        final activeProcessingIds = processingConversations
            .where((conversation) => _isActiveProcessingStatus(conversation.status))
            .map((conversation) => conversation.id)
            .toSet();
        conversations = _filterPendingDeletes(SharedPreferencesUtil().cachedConversations)
            .where(
              (conversation) =>
                  !activeProcessingIds.contains(conversation.id) && _matchesActiveConversationFilters(conversation),
            )
            .toList();
      }
      if (searchedConversations.isEmpty) {
        searchedConversations = conversations;
      }
      _groupConversationsByDateWithoutNotify();
      setLoadingConversations(false);
      notifyListeners();
      _scheduleInitialFetchRetry();
      return false;
    }

    conversationsLoadFailed = false;
    _initialFetchRetryTimer?.cancel();
    _initialFetchRetryCount = 0;
    final fetchedConversations = _filterPendingDeletes(result.items);
    final pageConversationIds = fetchedConversations.map((conversation) => conversation.id).toSet();
    final lifecycleResults = await _loadProcessingLifecycleResults(fetchedConversations, processingIdsAtStart);
    if (generation != _sessionGeneration || fetchRevision != _conversationFetchRevision || !_isSignedIn()) {
      if (_conversationLoadingRevision == fetchRevision) setLoadingConversations(false);
      return false;
    }
    _reconcileProcessingConversations(
      lifecycleResults,
      processingIdsAtStart,
      pageConversationIds,
      processingRevisionsAtStart,
      processingRowsAtStart,
    );
    _conversationServerOffset = result.items.length;
    _conversationServerHasMore = !result.truncated && result.items.length >= _conversationPageSize;
    _conversationServerLoadedIds
      ..clear()
      ..addAll(result.items.map((conversation) => conversation.id));

    // A ConversationEvent can complete a row while the list/lifecycle awaits
    // above. The stale page may omit that row, so preserve only completed rows
    // that were added or replaced live during this fetch. Do not carry forward
    // an unchanged pre-fetch row (the server page is authoritative for those),
    // and never resurrect a row in the undo/delete window.
    final currentlyProcessingIds = processingConversations
        .where((conversation) => _isActiveProcessingStatus(conversation.status))
        .map((conversation) => conversation.id)
        .toSet();
    final completedById = <String, ServerConversation>{
      for (final conversation in fetchedConversations)
        if (conversation.status == ConversationStatus.completed && !currentlyProcessingIds.contains(conversation.id))
          conversation.id: conversation,
    };
    for (final lifecycleResult in lifecycleResults.values) {
      final conversation = lifecycleResult.item;
      if (!lifecycleResult.ok ||
          conversation == null ||
          conversation.status != ConversationStatus.completed ||
          currentlyProcessingIds.contains(conversation.id) ||
          memoriesToDelete.containsKey(conversation.id) ||
          !_matchesActiveConversationFilters(conversation)) {
        continue;
      }
      // A successful lifecycle probe is authoritative when the page still
      // reports this row as processing, so publish its completed detail.
      completedById[conversation.id] = conversation;
    }
    for (final conversation in conversations) {
      if (conversation.status != ConversationStatus.completed) continue;
      if (memoriesToDelete.containsKey(conversation.id) || !_matchesActiveConversationFilters(conversation)) {
        continue;
      }
      // A changed live object wins over a stale page object even when the
      // page contains the same ID with older status/content. Unchanged
      // pre-fetch rows remain governed by the authoritative page.
      if (!identical(conversationsAtStart[conversation.id], conversation)) {
        completedById[conversation.id] = conversation;
      }
    }
    conversations = completedById.values.toList()
      ..sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));

    // Only use cache when no folder filter is applied
    if (conversations.isEmpty && selectedFolderId == null) {
      final activeProcessingIds = processingConversations
          .where((conversation) => _isActiveProcessingStatus(conversation.status))
          .map((conversation) => conversation.id)
          .toSet();
      conversations = _filterPendingDeletes(SharedPreferencesUtil().cachedConversations)
          .where(
            (conversation) =>
                !activeProcessingIds.contains(conversation.id) && _matchesActiveConversationFilters(conversation),
          )
          .toList();
    } else if (selectedFolderId == null) {
      // Only cache when viewing all folders
      SharedPreferencesUtil().cachedConversations = conversations;
    }
    if (searchedConversations.isEmpty) {
      searchedConversations = conversations;
    }
    _groupConversationsByDateWithoutNotify();

    // Keep pagination blocked until lifecycle reconciliation and the final
    // list assignment are complete. [getMoreConversationsFromServer] uses
    // this loading state as its serialization guard.
    setLoadingConversations(false);
    notifyListeners();
    return true;
  }

  void _scheduleInitialFetchRetry() {
    if (!_isSignedIn()) {
      _cancelInitialFetchRetry();
      return;
    }
    _initialFetchRetryTimer?.cancel();
    final int delaySeconds;
    if (_initialFetchRetryCount < _maxInitialFetchRetries) {
      _initialFetchRetryCount++;
      // Fast linear backoff for the first few attempts: 2s, 4s, 6s, 8s.
      delaySeconds = 2 * _initialFetchRetryCount;
    } else {
      // Budget spent — keep self-healing on a slow interval so the UI stays
      // on the shimmer (isAwaitingInitialFetchRetry stays true) instead of
      // falling through to the misleading get-started/empty state.
      delaySeconds = _slowFetchRetryIntervalSeconds;
    }
    _initialFetchRetryTimer = Timer(Duration(seconds: delaySeconds), () {
      if (conversationsLoadFailed && _isSignedIn()) fetchConversations();
    });
  }

  void _cancelInitialFetchRetry() {
    _initialFetchRetryTimer?.cancel();
    _initialFetchRetryTimer = null;
    _initialFetchRetryCount = 0;
  }

  Future<void> getInitialConversations() async {
    // A manual/initial entry gets a fresh retry budget so pull-to-refresh
    // can recover even after the auto-retries were exhausted.
    _cancelInitialFetchRetry();
    final fetched = await fetchConversations();
    if (!fetched || !_isSignedIn()) return;
    await checkHasDailySummaries();
  }

  List<ServerConversation> _filterOutConvos(List<ServerConversation> convos) {
    return convos.where((convo) {
      // Filter by discarded status
      // When showDiscardedConversations is true, show all conversations (including discarded)
      // When showDiscardedConversations is false, hide discarded conversations
      if (!showDiscardedConversations && convo.discarded) {
        return false;
      }

      // Filter out short conversations unless explicitly showing them
      if (!showShortConversations) {
        final durationSeconds = convo.getDurationInSeconds();
        if (durationSeconds < shortConversationThreshold) {
          return false;
        }
      }

      // Filter by starred status if enabled
      if (showStarredOnly) {
        if (!convo.starred) {
          return false;
        }
      }

      // Apply date range filter if selected
      if (selectedStartDate != null && selectedEndDate != null) {
        var effectiveDate = convo.startedAt ?? convo.createdAt;
        var convoDate = conversationLocalDayKey(effectiveDate);
        var startDay = DateTime(selectedStartDate!.year, selectedStartDate!.month, selectedStartDate!.day);
        var endDay = DateTime(selectedEndDate!.year, selectedEndDate!.month, selectedEndDate!.day);
        if (convoDate.isBefore(startDay) || convoDate.isAfter(endDay)) {
          return false;
        }
      }

      // Filter by folder if selected
      if (selectedFolderId != null) {
        if (convo.folderId != selectedFolderId) {
          return false;
        }
      }

      return true;
    }).toList();
  }

  /// Set search date range (start and end). Null = no limit on that side.
  ///
  /// Dates are normalized to day boundaries so the selected final calendar day
  /// is included: [start] is set to the start of its day (00:00:00) and [end]
  /// is set to the end of its day (23:59:59.999), matching how the server
  /// interprets the ISO-8601 bounds.
  void setSearchDateRange(DateTime? start, DateTime? end) {
    searchStartDate = start != null ? DateTime(start.year, start.month, start.day) : null;
    searchEndDate = end != null ? DateTime(end.year, end.month, end.day, 23, 59, 59, 999) : null;
    notifyListeners();
  }

  /// Clear the search date range filter
  void clearSearchDateRange() {
    searchStartDate = null;
    searchEndDate = null;
    notifyListeners();
  }

  /// Filter conversations by a date range (inclusive of both start and end day)
  Future<void> filterConversationsByDateRange(DateTime start, DateTime end) async {
    selectedStartDate = start;
    selectedEndDate = end;

    // Clear search when applying date filter
    selectedSpeakerId = null;
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    groupedConversations = {};
    notifyListeners();

    await fetchConversations();
  }

  /// Clear the date filter
  Future<void> clearDateFilter() async {
    selectedStartDate = null;
    selectedEndDate = null;

    // Clear search when clearing date filter
    selectedSpeakerId = null;
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    groupedConversations = {};
    notifyListeners();

    await fetchConversations();
  }

  void _groupSearchConvosByDateWithoutNotify() {
    groupedConversations = groupSearchResultsPreservingRank(_filterOutConvos(searchedConversations));
  }

  void _groupConversationsByDateWithoutNotify() {
    groupedConversations = _buildGroupedByDate(_filterOutConvos(conversations));
  }

  /// Buckets conversations into day-keyed groups, sorted newest-first both
  /// at the day-group level and within each day.
  ///
  /// Why the explicit re-ordering at the end matters: the backend returns
  /// conversations ordered by `created_at` DESC, but we bucket by
  /// `started_at` (falling back to `created_at`). For re-processed or
  /// merged conversations these two timestamps diverge — a conversation
  /// merged today with the original recording date of, say, May 9 lands
  /// at the top of the API response (newest `created_at`) and creates
  /// the `May 9` day-bucket first. Dart's default Map iterates in
  /// insertion order, so without this sort step the UI would render
  /// `May 9` above today/yesterday. Rebuilding the map in descending
  /// key order fixes the day-group display order.
  Map<DateTime, List<ServerConversation>> _buildGroupedByDate(Iterable<ServerConversation> source) {
    final grouped = <DateTime, List<ServerConversation>>{};
    for (final conversation in source) {
      final effectiveDate = conversation.startedAt ?? conversation.createdAt;
      final date = conversationLocalDayKey(effectiveDate);
      grouped.putIfAbsent(date, () => []).add(conversation);
    }

    for (final list in grouped.values) {
      list.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    }

    final sortedKeys = grouped.keys.toList()..sort((a, b) => b.compareTo(a));
    return {for (final k in sortedKeys) k: grouped[k]!};
  }

  void groupConversationsByDate() {
    if (hasActiveSearch) {
      _groupSearchConvosByDateWithoutNotify();
    } else {
      _groupConversationsByDateWithoutNotify();
    }
    notifyListeners();
  }

  void groupSearchConvosByDate() {
    _groupSearchConvosByDateWithoutNotify();
    notifyListeners();
  }

  (DateTime?, DateTime?) _getDateFilterRange() {
    if (selectedStartDate == null || selectedEndDate == null) return (null, null);
    final start = selectedStartDate!;
    final end = selectedEndDate!;
    return (
      DateTime(start.year, start.month, start.day, 0, 0, 0),
      DateTime(end.year, end.month, end.day, 23, 59, 59, 999),
    );
  }

  Future<({List<ServerConversation> items, bool ok, bool truncated})> _getConversationsFromServer() async {
    final fetcher = _conversationListFetcher;
    if (fetcher != null) {
      final result = await fetcher();
      return (items: result.items, ok: result.ok, truncated: false);
    }

    final (startDate, endDate) = _getDateFilterRange();

    return await getConversationsResult(
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
  }

  bool _isActiveProcessingStatus(ConversationStatus status) {
    return status == ConversationStatus.processing || status == ConversationStatus.merging;
  }

  Map<String, ServerConversation> _realProcessingConversationsById() => {
        for (final conversation in processingConversations)
          if (conversation.id != '0') conversation.id: conversation,
      };

  Future<Map<String, ({ServerConversation? item, bool ok})>> _loadProcessingLifecycleResults(
    List<ServerConversation> pageItems,
    Set<String> processingIdsAtStart,
  ) async {
    final results = <String, ({ServerConversation? item, bool ok})>{
      for (final conversation in pageItems) conversation.id: (item: conversation, ok: true),
    };

    // Probe every card that was already tracked at refresh start, including
    // IDs present on this page. The page can carry an older status than the
    // detail endpoint; a failed probe remains inconclusive and preserves the
    // local card rather than replacing it with stale page data.
    final ids = processingIdsAtStart.toList();
    if (ids.isEmpty) return results;

    // Page entries are only a fallback for untracked rows. Tracked IDs must
    // start inconclusive until their lifecycle probe succeeds, otherwise a
    // probe that times out would silently retain a stale page status.
    for (final id in ids) {
      results[id] = (item: null, ok: false);
    }

    var nextIndex = 0;
    var deadlineExpired = false;
    Future<void> worker() async {
      while (true) {
        if (deadlineExpired || nextIndex >= ids.length) return;
        final id = ids[nextIndex++];
        ({ServerConversation? item, bool ok}) lifecycleResult;
        try {
          lifecycleResult = await _conversationLifecycleFetcher(id);
        } catch (_) {
          lifecycleResult = (item: null, ok: false);
        }
        // A timed-out worker may still complete later. Do not mutate the map
        // after the caller has received the fail-soft result.
        if (!deadlineExpired) results[id] = lifecycleResult;
      }
    }

    final workerCount =
        ids.length < _processingLifecycleMaxConcurrency ? ids.length : _processingLifecycleMaxConcurrency;
    final workers = List<Future<void>>.generate(workerCount, (_) => worker());
    try {
      await Future.wait(workers).timeout(_processingLifecycleDeadline);
    } on TimeoutException {
      deadlineExpired = true;
      // Mark all unresolved probes inconclusive. Existing cards are retained
      // by reconciliation, while page-only rows still come from the page.
      for (final id in ids) {
        results[id] ??= (item: null, ok: false);
      }
    }
    return results;
  }

  bool _matchesActiveConversationFilters(ServerConversation conversation) {
    if (!showDiscardedConversations && conversation.discarded) return false;
    if (showStarredOnly && !conversation.starred) return false;
    if (selectedStartDate != null && selectedEndDate != null) {
      final conversationDate = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt);
      final startDay = DateTime(selectedStartDate!.year, selectedStartDate!.month, selectedStartDate!.day);
      final endDay = DateTime(selectedEndDate!.year, selectedEndDate!.month, selectedEndDate!.day);
      if (conversationDate.isBefore(startDay) || conversationDate.isAfter(endDay)) return false;
    }
    if (selectedFolderId != null && conversation.folderId != selectedFolderId) return false;
    return true;
  }

  void _reconcileProcessingConversations(
    Map<String, ({ServerConversation? item, bool ok})> lifecycleResults,
    Set<String> processingIdsAtStart,
    Set<String> pageConversationIds,
    Map<String, int> processingRevisionsAtStart,
    Map<String, ServerConversation> processingRowsAtStart,
  ) {
    final localPlaceholder = processingConversations.where((conversation) => conversation.id == '0').toList();
    final reconciled = <ServerConversation>[];

    for (final existing in processingConversations.where((conversation) => conversation.id != '0')) {
      // A row added or replaced by websocket after this refresh began is newer
      // than the page/detail snapshot. Preserve that live object for this pass;
      // unrelated websocket events must not block reconciliation of this ID.
      if (!identical(processingRowsAtStart[existing.id], existing)) {
        if (_matchesActiveConversationFilters(existing)) reconciled.add(existing);
        continue;
      }
      final result = lifecycleResults[existing.id];
      if (result == null || !result.ok) {
        if (_matchesActiveConversationFilters(existing)) reconciled.add(existing);
        continue;
      }
      final current = result.item;
      if (current != null && _isActiveProcessingStatus(current.status) && _matchesActiveConversationFilters(current)) {
        reconciled.add(current);
      }
    }

    for (final result in lifecycleResults.values) {
      final conversation = result.item;
      if (!result.ok || conversation == null || !_isActiveProcessingStatus(conversation.status)) continue;
      // Previously tracked IDs are owned by the live-list loop above. If a
      // websocket completion removed one while lifecycle GETs were in flight,
      // a stale detail response must not revive it here. This loop only admits
      // newly discovered active rows from the authoritative list page.
      if (_processingStateRevisionById[conversation.id] != processingRevisionsAtStart[conversation.id] ||
          processingIdsAtStart.contains(conversation.id) ||
          !pageConversationIds.contains(conversation.id) ||
          !_matchesActiveConversationFilters(conversation)) {
        continue;
      }
      if (reconciled.every((existing) => existing.id != conversation.id)) {
        reconciled.add(conversation);
      }
    }

    processingConversations = [...localPlaceholder, ...reconciled];
  }

  void updateActionItemState(String convoId, bool state, int i, DateTime date) {
    conversations.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed = state;
    groupedConversations[date]!.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed =
        state;
    notifyListeners();
  }

  Future<bool> getMoreConversationsFromServer() async {
    // Use the server cursor rather than the displayed list length. Live
    // websocket overlays (and pending-delete filtering) can make the local
    // list cardinality differ from the server page cardinality.
    if (!_conversationServerHasMore) return false;
    if (isLoadingConversations) return false;
    final operationRevision = ++_conversationFetchRevision;
    _conversationLoadingRevision = operationRevision;
    setLoadingConversations(true);

    // Date filter if selected
    final (startDate, endDate) = _getDateFilterRange();

    final pageOffset = _conversationServerOffset;
    final pageResult = conversationPageFetcherOverride != null
        ? await conversationPageFetcherOverride!.call()
        : await getConversationsResult(
            offset: pageOffset,
            includeDiscarded: showDiscardedConversations,
            startDate: startDate,
            endDate: endDate,
            folderId: selectedFolderId,
            starred: showStarredOnly ? true : null,
          );
    if (operationRevision != _conversationFetchRevision) {
      if (_conversationLoadingRevision == operationRevision) setLoadingConversations(false);
      return false;
    }
    if (!pageResult.ok) {
      setLoadingConversations(false);
      notifyListeners();
      return false;
    }
    final newConversations = pageResult.items;
    _conversationServerOffset += newConversations.length;
    _conversationServerHasMore = !pageResult.truncated && newConversations.length >= _conversationPageSize;
    _conversationServerLoadedIds.addAll(newConversations.map((conversation) => conversation.id));
    final existingIds = conversations.map((conversation) => conversation.id).toSet();
    conversations.addAll(
      _filterPendingDeletes(newConversations).where((conversation) => !existingIds.contains(conversation.id)),
    );
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    _groupConversationsByDateWithoutNotify();
    setLoadingConversations(false);
    notifyListeners();
    return true;
  }

  Future<void> addConversation(ServerConversation conversation) async {
    // Check if this is the first conversation
    bool wasEmpty = conversations.isEmpty;

    conversations.insert(0, conversation);
    _groupConversationsByDateWithoutNotify();

    // Mark first conversation for app review
    if (wasEmpty && await _appReviewService.isFirstConversation()) {
      await _appReviewService.markFirstConversation();
    }

    notifyListeners();
  }

  void upsertConversation(ServerConversation conversation) {
    int idx = conversations.indexWhere((m) => m.id == conversation.id);
    if (idx < 0) {
      addConversation(conversation);
    } else {
      updateConversation(conversation, idx);
    }
  }

  void updateConversationInSortedList(ServerConversation conversation) {
    final canonicalIndex = conversations.indexWhere((element) => element.id == conversation.id);
    if (canonicalIndex != -1) {
      conversations[canonicalIndex] = conversation;
    }
    final searchedIndex = searchedConversations.indexWhere((element) => element.id == conversation.id);
    if (searchedIndex != -1) {
      searchedConversations[searchedIndex] = conversation;
    }
    for (final group in groupedConversations.values) {
      final groupedIndex = group.indexWhere((element) => element.id == conversation.id);
      if (groupedIndex != -1) {
        group[groupedIndex] = conversation;
      }
    }
    notifyListeners();
  }

  (int, DateTime) addConversationWithDateGrouped(ServerConversation conversation) {
    conversations.insert(0, conversation);
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    int idx;
    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var memDate = conversationLocalDayKey(effectiveDate);
    if (groupedConversations.containsKey(memDate)) {
      var convoEffectiveDate = conversation.startedAt ?? conversation.createdAt;
      idx = groupedConversations[memDate]!.indexWhere(
        (element) => (element.startedAt ?? element.createdAt).isBefore(convoEffectiveDate),
      );
      if (idx == -1) {
        groupedConversations[memDate]!.insert(0, conversation);
        idx = 0;
      } else {
        groupedConversations[memDate]!.insert(idx, conversation);
      }
    } else {
      groupedConversations[memDate] = [conversation];
      groupedConversations = Map.fromEntries(
        groupedConversations.entries.toList()..sort((a, b) => b.key.compareTo(a.key)),
      );
      idx = 0;
    }
    return (idx, memDate);
  }

  void updateConversation(ServerConversation conversation, [int? index]) {
    if (index != null) {
      conversations[index] = conversation;
    } else {
      int i = conversations.indexWhere((element) => element.id == conversation.id);
      if (i != -1) {
        conversations[i] = conversation;
      }
    }
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    if (hasActiveSearch) {
      int si = searchedConversations.indexWhere((element) => element.id == conversation.id);
      if (si != -1) {
        searchedConversations[si] = conversation;
      }
      _groupSearchConvosByDateWithoutNotify();
    } else {
      _groupConversationsByDateWithoutNotify();
    }
    notifyListeners();
  }

  // _handleCalendarCreation(ServerMemory memory) {
  //   if (!SharedPreferencesUtil().calendarEnabled) return;
  //   if (SharedPreferencesUtil().calendarType != 'auto') return;
  //
  //   List<Event> events = memory.structured.events;
  //   if (events.isEmpty) return;
  //
  //   List<int> indexes = events.mapIndexed((index, e) => index).toList();
  //   setMemoryEventsState(memory.id, indexes, indexes.map((_) => true).toList());
  //   for (var i = 0; i < events.length; i++) {
  //     if (events[i].created) continue;
  //     events[i].created = true;
  //     CalendarUtil().createEvent(
  //       events[i].title,
  //       events[i].startsAt,
  //       events[i].duration,
  //       description: events[i].description,
  //     );
  //   }
  // }

  /////////////////////////////////////////////////////////////////
  ////////// Delete Memory With Undo Functionality ///////////////

  Map<String, ServerConversation> memoriesToDelete = {};
  String? lastDeletedConversationId;
  Map<String, DateTime> deleteTimestamps = {};

  // Hide conversations whose server-side DELETE is still pending (3s undo window
  // or in-flight HTTP). Without this, a pull-to-refresh during that window
  // re-surfaces the just-deleted conversation, which users read as "delete didn't work".
  List<ServerConversation> _filterPendingDeletes(List<ServerConversation> items) {
    if (memoriesToDelete.isEmpty) return items;
    return items.where((c) => !memoriesToDelete.containsKey(c.id)).toList();
  }

  void deleteConversationLocally(ServerConversation conversation, DateTime date) {
    if (lastDeletedConversationId != null &&
        memoriesToDelete.containsKey(lastDeletedConversationId) &&
        DateTime.now().difference(deleteTimestamps[lastDeletedConversationId]!) < const Duration(seconds: 3)) {
      deleteConversationOnServer(lastDeletedConversationId!);
    }

    memoriesToDelete[conversation.id] = conversation;
    lastDeletedConversationId = conversation.id;
    deleteTimestamps[conversation.id] = DateTime.now();
    conversations.removeWhere((element) => element.id == conversation.id);
    final group = groupedConversations[date];
    if (group != null) {
      group.removeWhere((e) => e.id == conversation.id);
      if (group.isEmpty) {
        groupedConversations.remove(date);
      }
    }
    notifyListeners();
    Future.delayed(const Duration(seconds: 3), () {
      if (memoriesToDelete.containsKey(conversation.id) && lastDeletedConversationId == conversation.id) {
        deleteConversationOnServer(conversation.id);
      }
    });
  }

  void deleteConversationOnServer(String conversationId) {
    final generation = _sessionGeneration;
    final wasLoadedFromServer = _conversationServerLoadedIds.contains(conversationId);
    final deleteFuture =
        conversationDeleteFetcherOverride?.call(conversationId) ?? deleteConversationServer(conversationId);
    unawaited(
      deleteFuture.then(
        (succeeded) {
          // A DELETE can outlive sign-out/account switching. Its result belongs
          // to the session that started it; never let an old account mutate the
          // new provider's tombstones, cursor, revision, or loading state.
          if (generation != _sessionGeneration) return;
          // Only rebase the server cursor after the backend confirms deletion. A
          // failed DELETE leaves the row in the server sequence and must not make
          // the next page skip an item.
          if (succeeded && wasLoadedFromServer && _conversationServerLoadedIds.remove(conversationId)) {
            if (_conversationServerOffset > 0) _conversationServerOffset--;
          }
          if (succeeded) {
            final invalidatedRevision = _conversationFetchRevision;
            _conversationFetchRevision++;
            if (_conversationLoadingRevision == invalidatedRevision) {
              setLoadingConversations(false);
            }
          }
          // Keep the tombstone in place until the request settles so a concurrent
          // refresh cannot reinsert the server row before DELETE completes.
          if (succeeded) {
            conversations.removeWhere((conversation) => conversation.id == conversationId);
            searchedConversations.removeWhere((conversation) => conversation.id == conversationId);
            for (final group in groupedConversations.values) {
              group.removeWhere((conversation) => conversation.id == conversationId);
            }
            groupedConversations.removeWhere((_, group) => group.isEmpty);
          }
          _clearDeleteTombstone(conversationId);
          notifyListeners();
        },
        onError: (Object _, StackTrace __) {
          // Match the prior behavior on a failed request: release the local
          // tombstone, but do not rebase the server cursor.
          if (generation != _sessionGeneration) return;
          _clearDeleteTombstone(conversationId);
          notifyListeners();
        },
      ),
    );
  }

  void _clearDeleteTombstone(String conversationId) {
    memoriesToDelete.remove(conversationId);
    deleteTimestamps.remove(conversationId);
    if (lastDeletedConversationId == conversationId) {
      lastDeletedConversationId = null;
    }
  }

  void undoDeletedConversation(ServerConversation conversation) {
    if (!conversations.any((e) => e.id == conversation.id)) {
      conversations.add(conversation);
      conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
      _groupConversationsByDateWithoutNotify();
    }
    memoriesToDelete.remove(conversation.id);
    deleteTimestamps.remove(conversation.id);
    if (lastDeletedConversationId == conversation.id) {
      lastDeletedConversationId = null;
    }
    notifyListeners();
  }

  /////////////////////////////////////////////////////////////////

  void deleteConversation(ServerConversation conversation) {
    conversations.removeWhere((element) => element.id == conversation.id);
    searchedConversations.removeWhere((element) => element.id == conversation.id);
    // Keep a tombstone through the in-flight DELETE so a concurrent list
    // response cannot reinsert the just-removed row before confirmation.
    memoriesToDelete[conversation.id] = conversation;
    deleteConversationOnServer(conversation.id);
    groupConversationsByDate();
  }

  @override
  void dispose() {
    _refreshDebounceTimer?.cancel();
    _initialFetchRetryTimer?.cancel();
    _mergeCompletedSubscription?.cancel();
    super.dispose();
  }

  void setIsFetchingConversations(bool value) {
    isFetchingConversations = value;
    notifyListeners();
  }

  // New Getter for Action Items Page
  Map<ServerConversation, List<ActionItem>> get conversationsWithActiveActionItems {
    final Map<ServerConversation, List<ActionItem>> result = {};
    final List<ServerConversation> sourceList = conversations;

    for (final convo in sourceList) {
      if (convo.discarded && !showDiscardedConversations) continue;

      final activeItems = convo.structured.actionItems.where((item) => !item.deleted).toList();
      if (activeItems.isNotEmpty) {
        result[convo] = activeItems;
      }
    }
    return result;
  }

  Future<void> updateGlobalActionItemState(
    ServerConversation conversation,
    String actionItemDescription,
    bool newState,
  ) async {
    final convoId = conversation.id;
    bool conversationFoundAndUpdated = false;

    final originalConvoIndex = conversations.indexWhere((c) => c.id == convoId);
    if (originalConvoIndex != -1) {
      final itemIndex = conversations[originalConvoIndex].structured.actionItems.indexWhere(
            (item) => item.description == actionItemDescription,
          );
      if (itemIndex != -1) {
        conversations[originalConvoIndex].structured.actionItems[itemIndex].completed = newState;
        conversationFoundAndUpdated = true;
      }
    }

    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var dateKey = conversationLocalDayKey(effectiveDate);
    if (groupedConversations.containsKey(dateKey)) {
      final groupIndex = groupedConversations[dateKey]!.indexWhere((c) => c.id == convoId);
      if (groupIndex != -1) {
        final itemIndex = groupedConversations[dateKey]![groupIndex].structured.actionItems.indexWhere(
              (item) => item.description == actionItemDescription,
            );
        if (itemIndex != -1) {
          groupedConversations[dateKey]![groupIndex].structured.actionItems[itemIndex].completed = newState;
        }
      }
    }

    if (conversationFoundAndUpdated) {
      // Find the item index for the server call
      final itemIndex = conversation.structured.actionItems.indexWhere(
        (item) => item.description == actionItemDescription,
      );
      if (itemIndex != -1) {
        await setConversationActionItemState(convoId, [itemIndex], [newState]);
      }
      notifyListeners();
    } else {
      Logger.debug("Error: Conversation or action item not found for updateGlobalActionItemState.");
    }
  }

  void updateActionItemDescriptionInConversation(String conversationId, int itemIndex, String newDescription) {
    final convoIndex = conversations.indexWhere((c) => c.id == conversationId);
    if (convoIndex != -1) {
      if (conversations[convoIndex].structured.actionItems.length > itemIndex) {
        conversations[convoIndex].structured.actionItems[itemIndex].description = newDescription;
      }
    }

    groupedConversations.forEach((date, convoList) {
      final groupIndex = convoList.indexWhere((c) => c.id == conversationId);
      if (groupIndex != -1) {
        if (convoList[groupIndex].structured.actionItems.length > itemIndex) {
          convoList[groupIndex].structured.actionItems[itemIndex].description = newDescription;
        }
      }
    });

    notifyListeners();
  }

  Future<void> deleteActionItemAndUpdateLocally(String conversationId, int itemIndex, ActionItem actionItem) async {
    deleteConversationActionItem(conversationId, actionItem);

    final convoIndex = conversations.indexWhere((c) => c.id == conversationId);
    if (convoIndex != -1) {
      if (conversations[convoIndex].structured.actionItems.length > itemIndex) {
        conversations[convoIndex].structured.actionItems.removeAt(itemIndex);
      }
    }

    groupedConversations.forEach((date, convoList) {
      final groupConvoIndex = convoList.indexWhere((c) => c.id == conversationId);
      if (groupConvoIndex != -1) {
        if (convoList[groupConvoIndex].structured.actionItems.length > itemIndex) {
          convoList[groupConvoIndex].structured.actionItems.removeAt(itemIndex);
        }
      }
    });

    notifyListeners();
  }

  (DateTime, int)? getConversationDateAndIndex(ServerConversation conversation) {
    final effectiveDate = conversation.startedAt ?? conversation.createdAt;
    final date = conversationLocalDayKey(effectiveDate);

    final list = groupedConversations[date];
    if (list == null) return null;

    final idx = list.indexWhere((e) => e.id == conversation.id);
    if (idx == -1) return null;

    return (date, idx);
  }

  /// Same lookup as [getConversationDateAndIndex] for callers that only hold an
  /// id (a chat message's conversation reference, a memory's `conversationId`).
  /// Resolving through the loaded conversation keeps the day key derived from
  /// `startedAt ?? createdAt` in local time — the contract the groups use.
  (DateTime, int)? getConversationDateAndIndexById(String conversationId) {
    final idx = conversations.indexWhere((c) => c.id == conversationId);
    if (idx == -1) return null;
    return getConversationDateAndIndex(conversations[idx]);
  }

  /// Places [conversation] in its local-day group if it isn't there yet and
  /// returns that group's key, so a caller navigating straight to a detail page
  /// selects the same day the list groups it under.
  DateTime ensureConversationInGroup(ServerConversation conversation) {
    final date = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt);
    final group = groupedConversations.putIfAbsent(date, () => []);
    if (!group.any((c) => c.id == conversation.id)) {
      group.insert(0, conversation);
    }
    return date;
  }

  int getConversationIndexById(String id, DateTime date) {
    final normalizedDate = DateTime(date.year, date.month, date.day);
    final list = groupedConversations[normalizedDate] ?? [];
    return list.indexWhere((c) => c.id == id);
  }

  /// Get adjacent conversation in display order (across date groups).
  /// [direction]: 1 for older (next in list), -1 for newer (previous in list).
  /// Returns null if at the boundary (no more conversations in that direction).
  ({ServerConversation conversation, DateTime date})? getAdjacentConversation(
    String currentConversationId,
    DateTime currentDate,
    int direction,
  ) {
    if (groupedConversations.isEmpty) return null;

    // Get sorted date keys (newest first, matching display order)
    final sortedDates = groupedConversations.keys.toList()..sort((a, b) => b.compareTo(a));
    if (sortedDates.isEmpty) return null;

    // Normalize current date
    final normalizedDate = DateTime(currentDate.year, currentDate.month, currentDate.day);
    final dateIndex = sortedDates.indexWhere(
      (d) => d.year == normalizedDate.year && d.month == normalizedDate.month && d.day == normalizedDate.day,
    );
    if (dateIndex == -1) return null;

    final currentDayList = groupedConversations[sortedDates[dateIndex]] ?? [];
    final convoIndexInDay = currentDayList.indexWhere((c) => c.id == currentConversationId);
    if (convoIndexInDay == -1) return null;

    if (direction == 1) {
      // Moving to older conversation (next in list)
      if (convoIndexInDay < currentDayList.length - 1) {
        // There's a next item in the same day
        return (conversation: currentDayList[convoIndexInDay + 1], date: sortedDates[dateIndex]);
      } else {
        // Need to move to the next older day (next date index since dates are sorted newest first)
        if (dateIndex < sortedDates.length - 1) {
          final nextDate = sortedDates[dateIndex + 1];
          final nextDayList = groupedConversations[nextDate] ?? [];
          if (nextDayList.isNotEmpty) {
            return (conversation: nextDayList.first, date: nextDate);
          }
        }
      }
    } else if (direction == -1) {
      // Moving to newer conversation (previous in list)
      if (convoIndexInDay > 0) {
        // There's a previous item in the same day
        return (conversation: currentDayList[convoIndexInDay - 1], date: sortedDates[dateIndex]);
      } else {
        // Need to move to the next newer day (previous date index since dates are sorted newest first)
        if (dateIndex > 0) {
          final prevDate = sortedDates[dateIndex - 1];
          final prevDayList = groupedConversations[prevDate] ?? [];
          if (prevDayList.isNotEmpty) {
            return (conversation: prevDayList.last, date: prevDate);
          }
        }
      }
    }

    return null; // At the boundary
  }

  void updateSyncedConversation(ServerConversation conversation) {
    updateConversationInSortedList(conversation);
    notifyListeners();
  }

  // ***************************************
  // ******** MERGE FUNCTIONALITY **********
  // ***************************************

  /// Check if a conversation is currently being merged
  /// Checks both local state and the conversation's actual status from server
  bool isConversationMerging(String conversationId) {
    // Check local tracking
    if (mergingConversationIds.contains(conversationId)) {
      return true;
    }
    // Check actual conversation status from server
    final idx = conversations.indexWhere((c) => c.id == conversationId);
    if (idx == -1) return false;

    return conversations[idx].status == ConversationStatus.merging;
  }

  /// Enter selection mode for merge
  void enterSelectionMode() {
    isSelectionModeActive = true;
    selectedConversationIds.clear();
    PlatformManager.instance.analytics.conversationMergeSelectionModeEntered();
    notifyListeners();
  }

  /// Exit selection mode and clear selections
  void exitSelectionMode() {
    isSelectionModeActive = false;
    selectedConversationIds.clear();
    PlatformManager.instance.analytics.conversationMergeSelectionModeExited();
    notifyListeners();
  }

  List<String> markSelectedAsMergingAndExit() {
    final idsToMerge = selectedConversationIds.toList();
    mergingConversationIds.addAll(idsToMerge);
    isSelectionModeActive = false;
    selectedConversationIds.clear();
    notifyListeners();
    return idsToMerge;
  }

  /// Toggle selection of a conversation
  void toggleConversationSelection(String conversationId) {
    if (isConversationMerging(conversationId)) {
      // Don't allow selection of conversations being merged
      return;
    }
    if (selectedConversationIds.contains(conversationId)) {
      selectedConversationIds.remove(conversationId);
      // Auto-exit selection mode if no items remain selected
      if (selectedConversationIds.isEmpty) {
        isSelectionModeActive = false;
      }
    } else {
      selectedConversationIds.add(conversationId);
      PlatformManager.instance.analytics.conversationSelectedForMerge(conversationId, selectedConversationIds.length);
    }
    notifyListeners();
  }

  /// Check if a conversation is selected
  bool isConversationSelected(String conversationId) {
    return selectedConversationIds.contains(conversationId);
  }

  /// Get selected conversations sorted by creation date (earliest first)
  List<ServerConversation> get selectedConversations {
    final selected = conversations.where((c) => selectedConversationIds.contains(c.id)).toList();
    selected.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    return selected;
  }

  /// Check if a conversation is eligible for merge selection
  ///
  /// A conversation is eligible if:
  /// - It's not locked
  /// - It's not currently being merged
  ///
  /// No time gap restrictions - user can merge any conversations they want.
  bool isConversationEligibleForMerge(String conversationId) {
    // Find the conversation
    final idx = conversations.indexWhere((c) => c.id == conversationId);
    if (idx == -1) return false;

    final convo = conversations[idx];
    if (convo.isLocked) return false;
    if (mergingConversationIds.contains(conversationId)) return false;

    return true;
  }

  /// Check if merge is allowed (at least 2 conversations selected)
  bool get canMerge => selectedConversationIds.length >= 2;

  /// Initiate merge of selected conversations
  Future<MergeConversationsResponse?> initiateConversationMerge({List<String>? conversationIds}) async {
    final idsToMerge = conversationIds ?? selectedConversationIds.toList();
    if (idsToMerge.length < 2) return null;

    // Call merge API
    final response = await mergeConversations(idsToMerge);
    PlatformManager.instance.analytics.conversationMergeInitiated(idsToMerge);

    if (response == null) {
      PlatformManager.instance.analytics.conversationMergeFailed(idsToMerge);
      if (conversationIds != null) {
        for (final id in conversationIds) {
          mergingConversationIds.remove(id);
        }
        notifyListeners();
      }
    } else if (conversationIds == null) {
      mergingConversationIds.addAll(idsToMerge);
      exitSelectionMode();
      notifyListeners();
    }

    return response;
  }

  /// Handle merge completion from FCM notification
  Future<void> onMergeCompleted(String mergedConversationId, List<String> removedConversationIds) async {
    // Remove merging status for ALL involved conversations
    mergingConversationIds.remove(mergedConversationId);
    for (final id in removedConversationIds) {
      mergingConversationIds.remove(id);
    }

    PlatformManager.instance.analytics.conversationMergeCompleted(mergedConversationId, removedConversationIds);

    // Remove deleted conversations from local state
    for (final id in removedConversationIds) {
      conversations.removeWhere((c) => c.id == id);
    }

    // Fetch updated merged conversation
    final mergedConvo = await getConversationById(mergedConversationId);
    if (mergedConvo != null) {
      final idx = conversations.indexWhere((c) => c.id == mergedConversationId);
      if (idx != -1) {
        conversations[idx] = mergedConvo;
      } else {
        conversations.insert(0, mergedConvo);
      }
      conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    }

    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }
}
