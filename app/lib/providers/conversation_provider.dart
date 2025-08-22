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

class ConversationProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
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

  IWalService get _wal => ServiceManager.instance().wal;
  final AppReviewService _appReviewService = AppReviewService();

  List<Wal> _missingWals = [];

  List<Wal> get missingWals => _missingWals;

  int get missingWalsInSeconds => _missingWals.isEmpty ? 0 : _missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

  double _walsSyncedProgress = 0.0;

  double get walsSyncedProgress => _walsSyncedProgress;

  bool isSyncing = false;
  bool syncCompleted = false;
  List<bool> multipleSyncs = [];
  bool isFetchingConversations = false;
  List<SyncedConversationPointer> syncedConversationsPointers = [];

  ConversationProvider() {
    _wal.subscribe(this, this);
    _preload();
  }

  _preload() async {
    _missingWals = await _wal.getSyncs().getMissingWals();
    notifyListeners();
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
      debugPrint('Skipping conversations refresh - too soon since last refresh (${now.difference(_lastRefreshTime!).inSeconds}s ago)');
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
    upsertConvos = newConversations.where((c) => c.status == ConversationStatus.processing && processingConversations.indexWhere((cc) => cc.id == c.id) == -1).toList();
    if (upsertConvos.isNotEmpty) {
      processingConversations.insertAll(0, upsertConvos);
    }

    // completed convos
    upsertConvos = newConversations.where((c) => c.status == ConversationStatus.completed && conversations.indexWhere((cc) => cc.id == c.id) == -1).toList();
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
    groupedConversations[date]!.firstWhere((element) => element.id == convoId).structured.actionItems[i].completed = state;
    notifyListeners();
  }

  Future getMoreConversationsFromServer() async {
    if (conversations.length % 50 != 0) return;
    if (isLoadingConversations) return;
    setLoadingConversations(true);
    var newConversations = await getConversations(offset: conversations.length, includeDiscarded: showDiscardedConversations);
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
      groupedConversations = Map.fromEntries(groupedConversations.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
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
    if (lastDeletedConversationId != null && memoriesToDelete.containsKey(lastDeletedConversationId) && DateTime.now().difference(deleteTimestamps[lastDeletedConversationId]!) < const Duration(seconds: 3)) {
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
    _wal.unsubscribe(this);
    super.dispose();
  }

  @override
  void onMissingWalUpdated() async {
    _missingWals = await _wal.getSyncs().getMissingWals();
    notifyListeners();
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) async {
    _missingWals = await _wal.getSyncs().getMissingWals();
    notifyListeners();
  }

  @override
  void onStatusChanged(WalServiceStatus status) {}

  @override
  void onWalSyncedProgress(double percentage) {
    _walsSyncedProgress = percentage;
  }

  Future syncWals() async {
    debugPrint("provider > syncWals");
    setSyncCompleted(false);
    _walsSyncedProgress = 0.0;
    setIsSyncing(true);
    var res = await _wal.getSyncs().syncAll(progress: this);
    if (res != null) {
      if (res.newConversationIds.isNotEmpty || res.updatedConversationIds.isNotEmpty) {
        await getSyncedConversationsData(res);
      }
    }
    setSyncCompleted(true);
    setIsSyncing(false);
    notifyListeners();
    return;
  }

  Future syncWal(Wal wal) async {
    debugPrint("provider > syncWal ${wal.id}");
    appendMultipleSyncs(true);
    _walsSyncedProgress = 0.0;
    var res = await _wal.getSyncs().syncWal(wal: wal, progress: this);
    if (res != null) {
      if (res.newConversationIds.isNotEmpty || res.updatedConversationIds.isNotEmpty) {
        print('Synced memories: ${res.newConversationIds} ${res.updatedConversationIds}');
        await getSyncedConversationsData(res);
      }
    }
    removeMultipleSyncs();
    notifyListeners();
    return;
  }

  void setSyncCompleted(bool value) {
    syncCompleted = value;
    notifyListeners();
  }

  Future getSyncedConversationsData(SyncLocalFilesResponse syncResult) async {
    List<dynamic> newConversations = syncResult.newConversationIds;
    List<dynamic> updatedConversations = syncResult.updatedConversationIds;
    setIsFetchingConversations(true);
    List<Future<ServerConversation?>> newConversationsFutures = newConversations.map((item) => getConversationDetails(item)).toList();

    List<Future<ServerConversation?>> updatedConversationsFutures = updatedConversations.map((item) => getConversationDetails(item)).toList();
    var syncedConversations = {'new_memories': [], 'updated_memories': []};
    try {
      final newConversationsResponses = await Future.wait(newConversationsFutures);
      syncedConversations['new_memories'] = newConversationsResponses;

      final updatedConversationsResponses = await Future.wait(updatedConversationsFutures);
      syncedConversations['updated_memories'] = updatedConversationsResponses;
      addSyncedConversationsToGroupedConversations(syncedConversations);
      setIsFetchingConversations(false);
    } catch (e) {
      print('Error during API calls: $e');
      setIsFetchingConversations(false);
    }
  }

  void addSyncedConversationsToGroupedConversations(Map syncedConversations) {
    if (syncedConversations['new_memories'] != []) {
      for (var conversation in syncedConversations['new_memories']!) {
        if (conversation != null && conversation.status == ConversationStatus.completed) {
          addConversation(conversation);
        }
      }
    }
    if (syncedConversations['updated_memories'] != []) {
      for (var conversation in syncedConversations['updated_memories']!) {
        if (conversation != null && conversation.status == ConversationStatus.completed) {
          upsertConversation(conversation);
        }
      }
    }
    for (var conversation in syncedConversations['new_memories']!) {
      if (conversation != null && conversation.status == ConversationStatus.completed) {
        var res = getConversationDateAndIndex(conversation);
        syncedConversationsPointers.add(SyncedConversationPointer(type: SyncedConversationType.newConversation, index: res.$2, key: res.$1, conversation: conversation));
      }
    }
    if (syncedConversations['updated_memories'] != []) {
      for (var conversation in syncedConversations['updated_memories']!) {
        if (conversation != null && conversation.status == ConversationStatus.completed) {
          var res = getConversationDateAndIndex(conversation);
          syncedConversationsPointers.add(SyncedConversationPointer(type: SyncedConversationType.newConversation, index: res.$2, key: res.$1, conversation: conversation));
        }
      }
    }
  }

  void updateSyncedConversationPointerIndex(SyncedConversationPointer mem, int index) {
    var oldIdx = syncedConversationsPointers.indexOf(mem);
    syncedConversationsPointers[oldIdx] = mem.copyWith(index: index);
    notifyListeners();
  }

  void updateSyncedConversation(ServerConversation conversation) {
    var id = syncedConversationsPointers.indexWhere((e) => e.conversation.id == conversation.id);
    if (id != -1) {
      syncedConversationsPointers[id] = syncedConversationsPointers[id].copyWith(conversation: conversation);
    }
    updateConversationInSortedList(conversation);
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

  Future<ServerConversation?> getConversationDetails(String conversationId) async {
    var conversation = await getConversationById(conversationId);
    return conversation;
  }

  void clearSyncResult() {
    syncCompleted = false;
    syncedConversationsPointers = [];
    notifyListeners();
  }

  void setIsSyncing(bool value) {
    isSyncing = value;
    notifyListeners();
  }

  void appendMultipleSyncs(bool value) {
    setIsSyncing(true);
    multipleSyncs.add(value);
    notifyListeners();
  }

  void removeMultipleSyncs() {
    if (multipleSyncs.isNotEmpty) {
      multipleSyncs.removeLast();
    } else {
      setIsSyncing(false);
      setSyncCompleted(true);
    }
    notifyListeners();
  }

  void clearMultipleSyncs() {
    multipleSyncs.clear();
    notifyListeners();
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

  Future<void> updateGlobalActionItemState(ServerConversation conversation, String actionItemDescription, bool newState) async {
    final convoId = conversation.id;
    bool conversationFoundAndUpdated = false;

    final originalConvoIndex = conversations.indexWhere((c) => c.id == convoId);
    if (originalConvoIndex != -1) {
      final itemIndex = conversations[originalConvoIndex].structured.actionItems.indexWhere((item) => item.description == actionItemDescription);
      if (itemIndex != -1) {
        conversations[originalConvoIndex].structured.actionItems[itemIndex].completed = newState;
        conversationFoundAndUpdated = true;
      }
    }

    var dateKey = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
    if (groupedConversations.containsKey(dateKey)) {
      final groupIndex = groupedConversations[dateKey]!.indexWhere((c) => c.id == convoId);
      if (groupIndex != -1) {
        final itemIndex = groupedConversations[dateKey]![groupIndex].structured.actionItems.indexWhere((item) => item.description == actionItemDescription);
        if (itemIndex != -1) {
          groupedConversations[dateKey]![groupIndex].structured.actionItems[itemIndex].completed = newState;
        }
      }
    }

    if (conversationFoundAndUpdated) {
      // Find the item index for the server call
      final itemIndex = conversation.structured.actionItems.indexWhere((item) => item.description == actionItemDescription);
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
}
