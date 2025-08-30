import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/services/app_review_service.dart';

class ConversationProvider extends ChangeNotifier {
  List<ServerConversation> conversations = [];
  List<ServerConversation> searchedConversations = [];
  Map<DateTime, List<ServerConversation>> groupedConversations = {};

  bool isLoadingConversations = false;
  bool showDiscardedConversations = false;
  DateTime? selectedDate;

  String previousQuery = '';
  int totalSearchPages = 1;
  int currentSearchPage = 1;

  Timer? _processingConversationWatchTimer;

  // Add debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 60); // Minimum time between refreshes

  List<ServerConversation> processingConversations = [];

  final AppReviewService _appReviewService = AppReviewService();

  bool isFetchingConversations = false;

  ConversationProvider() {
    _preload();
  }

  _preload() async {
    // Initialization logic if needed
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
    convos.sort((a, b) => b.createdAt.compareTo(a.createdAt));
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
    searchedConversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    totalSearchPages = total;
    currentSearchPage = current;
    groupSearchConvosByDate();
    setLoadingConversations(false);
    notifyListeners();
  }

  int groupedSearchConvoIndex(ServerConversation convo) {
    var date = DateTime(convo.createdAt.year, convo.createdAt.month, convo.createdAt.day);
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
    if (conversations.isEmpty) {
      conversations = SharedPreferencesUtil().cachedConversations;
    } else {
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
  }

  List<ServerConversation> _filterOutConvos(List<ServerConversation> convos) {
    return convos.where((convo) {
      // Filter by discarded status
      if (showDiscardedConversations) {
        // When showing discarded conversations, only show discarded ones
        if (!convo.discarded) {
          return false;
        }
      } else {
        // When not showing discarded conversations, only show non-discarded ones
        if (convo.discarded) {
          return false;
        }
      }

      // Apply date filter if selected
      if (selectedDate != null) {
        var convoDate = DateTime(convo.createdAt.year, convo.createdAt.month, convo.createdAt.day);
        var filterDate = DateTime(selectedDate!.year, selectedDate!.month, selectedDate!.day);
        if (convoDate != filterDate) {
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

    // Re-apply grouping with date filter
    groupConversationsByDate();
    notifyListeners();
  }

  /// Clear the date filter
  Future<void> clearDateFilter() async {
    selectedDate = null;

    // Clear search when clearing date filter
    previousQuery = "";
    currentSearchPage = 0;
    totalSearchPages = 0;
    searchedConversations = [];

    // Re-apply grouping without date filter
    groupConversationsByDate();
    notifyListeners();
  }

  void _groupSearchConvosByDateWithoutNotify() {
    groupedConversations = {};
    for (var conversation in _filterOutConvos(searchedConversations)) {
      var date = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(conversation);
    }

    // Sort
    for (final date in groupedConversations.keys) {
      groupedConversations[date]?.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    }
  }

  void _groupConversationsByDateWithoutNotify() {
    groupedConversations = {};
    for (var conversation in _filterOutConvos(conversations)) {
      var date = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(conversation);
    }

    // Sort
    for (final date in groupedConversations.keys) {
      groupedConversations[date]?.sort((a, b) => b.createdAt.compareTo(a.createdAt));
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

  Future _getConversationsFromServer() async {
    return await getConversations(includeDiscarded: showDiscardedConversations);
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
    var newConversations =
        await getConversations(offset: conversations.length, includeDiscarded: showDiscardedConversations);
    conversations.addAll(newConversations);
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
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
    var date = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
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
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    int idx;
    var memDate = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
    if (groupedConversations.containsKey(memDate)) {
      idx = groupedConversations[memDate]!.indexWhere((element) => element.createdAt.isBefore(conversation.createdAt));
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
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
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
      conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
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

    var dateKey = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
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

  (DateTime, int) getConversationDateAndIndex(ServerConversation conversation) {
    var date = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
    var idx = groupedConversations[date]!.indexWhere((element) => element.id == conversation.id);
    if (idx == -1 && groupedConversations.containsKey(date)) {
      groupedConversations[date]!.add(conversation);
    }
    return (date, idx);
  }

  void updateSyncedConversation(ServerConversation conversation) {
    updateConversationInSortedList(conversation);
    notifyListeners();
  }
}
