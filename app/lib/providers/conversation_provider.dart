import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/services/app_review_service.dart';

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
  DateTime? selectedDate;
  String? selectedFolderId;

  String previousQuery = '';
  int totalSearchPages = 1;
  int currentSearchPage = 1;

  Timer? _processingConversationWatchTimer;

  // Add debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 60); // Minimum time between refreshes

  List<ServerConversation> processingConversations = [];

  // Merge functionality state
  Set<String> mergingConversationIds = {};
  bool isSelectionModeActive = false;
  Set<String> selectedConversationIds = {};
  StreamSubscription<MergeCompletedEvent>? _mergeCompletedSubscription;

  final AppReviewService _appReviewService = AppReviewService();

  bool isFetchingConversations = false;

  ConversationProvider() {
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

  Future updateSearchedConvoDetails(String id, DateTime date, int idx) async {
    var convo = await getConversationById(id);
    if (convo != null) {
      updateSpecificGroupedConvo(convo, date, idx);
    }
    notifyListeners();
  }

  void updateSpecificGroupedConvo(ServerConversation convo, DateTime date, int idx) {
    groupedConversations[date]![idx] = convo;
    notifyListeners();
  }

  Future<void> searchConversations(String query, {bool showShimmer = false}) async {
    if (query.isEmpty) {
      previousQuery = "";
      currentSearchPage = 0;
      totalSearchPages = 0;
      searchedConversations = [];
      groupConversationsByDate();
      return;
    }

    if (showShimmer) {
      setLoadingConversations(true);
    } else {
      setIsFetchingConversations(true);
    }

    previousQuery = query;
    var (convos, current, total) = await searchConversationsServer(query, includeDiscarded: showDiscardedConversations);
    convos.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
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

  Future<void> searchMoreConversations() async {
    if (totalSearchPages < currentSearchPage + 1) {
      return;
    }
    setLoadingConversations(true);
    var (newConvos, current, total) = await searchConversationsServer(
      previousQuery,
      page: currentSearchPage + 1,
      includeDiscarded: showDiscardedConversations,
    );
    searchedConversations.addAll(newConvos);
    searchedConversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    totalSearchPages = total;
    currentSearchPage = current;
    groupSearchConvosByDate();
    setLoadingConversations(false);
    notifyListeners();
  }

  int groupedSearchConvoIndex(ServerConversation convo) {
    var convoDate = convo.startedAt ?? convo.createdAt;
    var date = DateTime(convoDate.year, convoDate.month, convoDate.day);
    if (groupedConversations.containsKey(date)) {
      return groupedConversations[date]!.indexWhere((element) => element.id == convo.id);
    }
    return -1;
  }

  void addProcessingConversation(ServerConversation conversation) {
    processingConversations.add(conversation);
    notifyListeners();
  }

  void removeProcessingConversation(String conversationId) {
    processingConversations.removeWhere((m) => m.id == conversationId);
    notifyListeners();
  }

  void onConversationTap(int idx) {
    if (idx < 0 || idx > conversations.length - 1) {
      return;
    }
    var changed = false;
    if (conversations[idx].isNew) {
      conversations[idx].isNew = false;
      changed = true;
    }
    if (changed) {
      groupConversationsByDate();
    }
  }

  void toggleDiscardConversations() {
    showDiscardedConversations = !showDiscardedConversations;
    SharedPreferencesUtil().showDiscardedMemories = showDiscardedConversations;

    // Clear grouped conversations to show shimmer effect while loading
    groupedConversations = {};
    notifyListeners();

    if (previousQuery.isNotEmpty) {
      searchConversations(previousQuery, showShimmer: true);
    } else {
      fetchConversations();
    }

    MixpanelManager().showDiscardedMemoriesToggled(showDiscardedConversations);
  }

  void toggleShortConversations() {
    showShortConversations = !showShortConversations;
    SharedPreferencesUtil().showShortConversations = showShortConversations;

    // Clear and refresh to reflect the change
    groupedConversations = {};
    notifyListeners();

    if (previousQuery.isNotEmpty) {
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

    if (previousQuery.isNotEmpty) {
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
  Future<void> checkHasDailySummaries() async {
    final summaries = await getDailySummaries(limit: 1, offset: 0);
    hasDailySummaries = summaries.isNotEmpty;
    notifyListeners();
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
      debugPrint(
          'Skipping conversations refresh - too soon since last refresh (${now.difference(_lastRefreshTime!).inSeconds}s ago)');
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
    setLoadingConversations(true);
    List<ServerConversation> newConversations = await _getConversationsFromServer();
    setLoadingConversations(false);

    List<ServerConversation> upsertConvos = [];

    // processing convos
    upsertConvos = newConversations
        .where((c) =>
            c.status == ConversationStatus.processing &&
            processingConversations.indexWhere((cc) => cc.id == c.id) == -1)
        .toList();
    if (upsertConvos.isNotEmpty) {
      processingConversations.insertAll(0, upsertConvos);
    }

    // completed convos
    upsertConvos = newConversations
        .where((c) => c.status == ConversationStatus.completed && conversations.indexWhere((cc) => cc.id == c.id) == -1)
        .toList();
    if (upsertConvos.isNotEmpty) {
      // Check if this is the first conversation
      bool wasEmpty = conversations.isEmpty;

      conversations.insertAll(0, upsertConvos);

      // Mark first conversation for app review
      if (wasEmpty && await _appReviewService.isFirstConversation()) {
        await _appReviewService.markFirstConversation();
      }
    }

    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  Future fetchConversations() async {
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    setLoadingConversations(true);
    conversations = await _getConversationsFromServer();
    setLoadingConversations(false);

    // processing convos
    processingConversations = conversations.where((m) => m.status == ConversationStatus.processing).toList();

    // completed convos
    conversations = conversations.where((m) => m.status == ConversationStatus.completed).toList();

    // Only use cache when no folder filter is applied
    if (conversations.isEmpty && selectedFolderId == null) {
      conversations = SharedPreferencesUtil().cachedConversations;
    } else if (selectedFolderId == null) {
      // Only cache when viewing all folders
      SharedPreferencesUtil().cachedConversations = conversations;
    }
    if (searchedConversations.isEmpty) {
      searchedConversations = conversations;
    }
    _groupConversationsByDateWithoutNotify();

    notifyListeners();
  }

  Future getInitialConversations() async {
    await fetchConversations();
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

      // Apply date filter if selected
      if (selectedDate != null) {
        var effectiveDate = convo.startedAt ?? convo.createdAt;
        var convoDate = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
        var filterDate = DateTime(selectedDate!.year, selectedDate!.month, selectedDate!.day);
        if (convoDate != filterDate) {
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

  /// Filter conversations by a specific date
  Future<void> filterConversationsByDate(DateTime date) async {
    selectedDate = date;

    // Clear search when applying date filter
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
    selectedDate = null;

    // Clear search when clearing date filter
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    groupedConversations = {};
    notifyListeners();

    await fetchConversations();
  }

  void _groupSearchConvosByDateWithoutNotify() {
    groupedConversations = {};
    for (var conversation in _filterOutConvos(searchedConversations)) {
      var effectiveDate = conversation.startedAt ?? conversation.createdAt;
      var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(conversation);
    }

    // Sort
    for (final date in groupedConversations.keys) {
      groupedConversations[date]?.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    }
  }

  void _groupConversationsByDateWithoutNotify() {
    groupedConversations = {};
    for (var conversation in _filterOutConvos(conversations)) {
      var effectiveDate = conversation.startedAt ?? conversation.createdAt;
      var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(conversation);
    }

    // Sort
    for (final date in groupedConversations.keys) {
      groupedConversations[date]?.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    }
  }

  void groupConversationsByDate() {
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  void groupSearchConvosByDate() {
    _groupSearchConvosByDateWithoutNotify();
    notifyListeners();
  }

  (DateTime?, DateTime?) _getDateFilterRange() {
    if (selectedDate == null) return (null, null);
    final date = selectedDate!;
    return (
      DateTime(date.year, date.month, date.day, 0, 0, 0),
      DateTime(date.year, date.month, date.day, 23, 59, 59),
    );
  }

  Future _getConversationsFromServer() async {
    final (startDate, endDate) = _getDateFilterRange();

    return await getConversations(
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
  }

  void updateActionItemState(String convoId, bool state, int i, DateTime date) {
    conversations.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed = state;
    groupedConversations[date]!.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed =
        state;
    notifyListeners();
  }

  Future getMoreConversationsFromServer() async {
    if (conversations.length % 50 != 0) return;
    if (isLoadingConversations) return;
    setLoadingConversations(true);

    // Date filter if selected
    final (startDate, endDate) = _getDateFilterRange();

    var newConversations = await getConversations(
      offset: conversations.length,
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
    conversations.addAll(newConversations);
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    _groupConversationsByDateWithoutNotify();
    setLoadingConversations(false);
    notifyListeners();
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
    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    if (groupedConversations.containsKey(date)) {
      int idx = groupedConversations[date]!.indexWhere((element) => element.id == conversation.id);
      if (idx != -1) {
        groupedConversations[date]![idx] = conversation;
      }
    }
    notifyListeners();
  }

  (int, DateTime) addConversationWithDateGrouped(ServerConversation conversation) {
    conversations.insert(0, conversation);
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    int idx;
    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var memDate = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    if (groupedConversations.containsKey(memDate)) {
      var convoEffectiveDate = conversation.startedAt ?? conversation.createdAt;
      idx = groupedConversations[memDate]!
          .indexWhere((element) => (element.startedAt ?? element.createdAt).isBefore(convoEffectiveDate));
      if (idx == -1) {
        groupedConversations[memDate]!.insert(0, conversation);
        idx = 0;
      } else {
        groupedConversations[memDate]!.insert(idx, conversation);
      }
    } else {
      groupedConversations[memDate] = [conversation];
      groupedConversations =
          Map.fromEntries(groupedConversations.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
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
    _groupConversationsByDateWithoutNotify();
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

  void deleteConversationLocally(ServerConversation conversation, int index, DateTime date) {
    if (lastDeletedConversationId != null &&
        memoriesToDelete.containsKey(lastDeletedConversationId) &&
        DateTime.now().difference(deleteTimestamps[lastDeletedConversationId]!) < const Duration(seconds: 3)) {
      deleteConversationOnServer(lastDeletedConversationId!);
    }

    memoriesToDelete[conversation.id] = conversation;
    lastDeletedConversationId = conversation.id;
    deleteTimestamps[conversation.id] = DateTime.now();
    conversations.removeWhere((element) => element.id == conversation.id);
    groupedConversations[date]!.removeAt(index);
    if (groupedConversations[date]!.isEmpty) {
      groupedConversations.remove(date);
    }
    notifyListeners();
    Future.delayed(const Duration(seconds: 3), () {
      if (memoriesToDelete.containsKey(conversation.id) && lastDeletedConversationId == conversation.id) {
        deleteConversationOnServer(conversation.id);
      }
    });
  }

  void deleteConversationOnServer(String conversationId) {
    deleteConversationServer(conversationId);
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

  void deleteConversation(ServerConversation conversation, int index) {
    conversations.removeWhere((element) => element.id == conversation.id);
    deleteConversationServer(conversation.id);
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  @override
  void dispose() {
    _processingConversationWatchTimer?.cancel();
    _refreshDebounceTimer?.cancel();
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
      ServerConversation conversation, String actionItemDescription, bool newState) async {
    final convoId = conversation.id;
    bool conversationFoundAndUpdated = false;

    final originalConvoIndex = conversations.indexWhere((c) => c.id == convoId);
    if (originalConvoIndex != -1) {
      final itemIndex = conversations[originalConvoIndex]
          .structured
          .actionItems
          .indexWhere((item) => item.description == actionItemDescription);
      if (itemIndex != -1) {
        conversations[originalConvoIndex].structured.actionItems[itemIndex].completed = newState;
        conversationFoundAndUpdated = true;
      }
    }

    var effectiveDate = conversation.startedAt ?? conversation.createdAt;
    var dateKey = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
    if (groupedConversations.containsKey(dateKey)) {
      final groupIndex = groupedConversations[dateKey]!.indexWhere((c) => c.id == convoId);
      if (groupIndex != -1) {
        final itemIndex = groupedConversations[dateKey]![groupIndex]
            .structured
            .actionItems
            .indexWhere((item) => item.description == actionItemDescription);
        if (itemIndex != -1) {
          groupedConversations[dateKey]![groupIndex].structured.actionItems[itemIndex].completed = newState;
        }
      }
    }

    if (conversationFoundAndUpdated) {
      // Find the item index for the server call
      final itemIndex =
          conversation.structured.actionItems.indexWhere((item) => item.description == actionItemDescription);
      if (itemIndex != -1) {
        await setConversationActionItemState(convoId, [itemIndex], [newState]);
      }
      notifyListeners();
    } else {
      debugPrint("Error: Conversation or action item not found for updateGlobalActionItemState.");
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
    final date = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);

    final list = groupedConversations[date];
    if (list == null) return null;

    final idx = list.indexWhere((e) => e.id == conversation.id);
    if (idx == -1) return null;

    return (date, idx);
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
        return (
          conversation: currentDayList[convoIndexInDay + 1],
          date: sortedDates[dateIndex],
        );
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
        return (
          conversation: currentDayList[convoIndexInDay - 1],
          date: sortedDates[dateIndex],
        );
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
    MixpanelManager().conversationMergeSelectionModeEntered();
    notifyListeners();
  }

  /// Exit selection mode and clear selections
  void exitSelectionMode() {
    isSelectionModeActive = false;
    selectedConversationIds.clear();
    MixpanelManager().conversationMergeSelectionModeExited();
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
      MixpanelManager().conversationSelectedForMerge(conversationId, selectedConversationIds.length);
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
    MixpanelManager().conversationMergeInitiated(idsToMerge);

    if (response == null) {
      MixpanelManager().conversationMergeFailed(idsToMerge);
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

    MixpanelManager().conversationMergeCompleted(mergedConversationId, removedConversationIds);

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
