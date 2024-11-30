import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/conversations.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class ConversationProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  List<ServerConversation> conversations = [];
  Map<DateTime, List<ServerConversation>> groupedConversations = {};

  bool isLoadingConversations = false;
  bool hasNonDiscardedConversations = true;
  bool showDiscardedConversations = false;

  String previousQuery = '';

  Timer? _processingMemoryWatchTimer;

  List<ServerConversation> processingConversations = [];

  IWalService get _wal => ServiceManager.instance().wal;

  List<Wal> _missingWals = [];

  List<Wal> get missingWals => _missingWals;

  int get missingWalsInSeconds =>
      _missingWals.isEmpty ? 0 : _missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

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

  void addProcessingMemory(ServerConversation memory) {
    processingConversations.add(memory);
    notifyListeners();
  }

  void removeProcessingMemory(String memoryId) {
    processingConversations.removeWhere((m) => m.id == memoryId);
    notifyListeners();
  }

  void onMemoryTap(int idx) {
    if (idx < 0 || idx > conversations.length - 1) {
      return;
    }
    var changed = false;
    if (conversations[idx].isNew) {
      conversations[idx].isNew = false;
      changed = true;
    }
    if (changed) {
      filterGroupedConversations('');
    }
  }

  void toggleDiscardConversations() {
    MixpanelManager().showDiscardedMemoriesToggled(!SharedPreferencesUtil().showDiscardedMemories);
    SharedPreferencesUtil().showDiscardedMemories = !SharedPreferencesUtil().showDiscardedMemories;
    showDiscardedConversations = SharedPreferencesUtil().showDiscardedMemories;
    // filterGroupedMemories('');
    notifyListeners();
  }

  void setLoadingConversations(bool value) {
    isLoadingConversations = value;
    notifyListeners();
  }

  Future getInitialConversations() async {
    conversations = await getConversationsFromServer();

    processingConversations = conversations.where((m) => m.status == MemoryStatus.processing).toList();

    conversations = conversations.where((m) => m.status == MemoryStatus.completed).toList();
    if (conversations.isEmpty) {
      conversations = SharedPreferencesUtil().cachedMemories;
    } else {
      SharedPreferencesUtil().cachedMemories = conversations;
    }
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  void _groupConversationsByDateWithoutNotify() {
    groupedConversations = {};
    for (var memory in conversations) {
      // if (SharedPreferencesUtil().showDiscardedMemories && memory.discarded && !memory.isNew) continue;
      var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
      if (!groupedConversations.containsKey(date)) {
        groupedConversations[date] = [];
      }
      groupedConversations[date]?.add(memory);
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

  void _filterGroupedConversationsWithoutNotify(String query) {
    if (query.isEmpty) {
      groupedConversations = {};
      _groupConversationsByDateWithoutNotify();
    } else {
      groupedConversations = {};
      for (var memory in conversations) {
        var date = memory.createdAt;
        if (!groupedConversations.containsKey(date)) {
          groupedConversations[date] = [];
        }
        if ((memory.getTranscript() + memory.structured.title + memory.structured.overview)
            .toLowerCase()
            .contains(query.toLowerCase())) {
          groupedConversations[date]?.add(memory);
        }
      }
    }
  }

  void filterGroupedConversations(String query) {
    // _filterGroupedConversationsWithoutNotify(query);
    _groupConversationsByDateWithoutNotify();
    notifyListeners();
  }

  Future getConversationsFromServer() async {
    setLoadingConversations(true);
    var mem = await getConversations();
    conversations = mem;
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    setLoadingConversations(false);
    notifyListeners();
    return conversations;
  }

  // void createEventsForMemories() {
  //   for (var memory in memories) {
  //     if (memory.structured.events.isNotEmpty &&
  //         !memory.structured.events.first.created &&
  //         memory.startedAt != null &&
  //         memory.startedAt!.isAfter(DateTime.now().add(const Duration(days: -1)))) {
  //       _handleCalendarCreation(memory);
  //     }
  //   }
  // }

  Future getMoreConversationsFromServer() async {
    if (conversations.length % 50 != 0) return;
    if (isLoadingConversations) return;
    setLoadingConversations(true);
    var newConversations = await getConversations(offset: conversations.length);
    conversations.addAll(newConversations);
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    filterGroupedConversations('');
    setLoadingConversations(false);
    notifyListeners();
  }

  void addMemory(ServerConversation memory) {
    conversations.insert(0, memory);
    addMemoryToGroupedConversations(memory);
    notifyListeners();
  }

  void upsertMemory(ServerConversation memory) {
    int idx = conversations.indexWhere((m) => m.id == memory.id);
    if (idx < 0) {
      addMemory(memory);
    } else {
      updateMemory(memory, idx);
    }
  }

  void addMemoryToGroupedConversations(ServerConversation memory) {
    var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    if (groupedConversations.containsKey(date)) {
      groupedConversations[date]!.insert(0, memory);
      groupedConversations[date]!.sort((a, b) => b.createdAt.compareTo(a.createdAt));
      if (syncedConversationsPointers.isNotEmpty) {
        // if the synced memory pointers contain a memory on this date, then update their index
        // This usually happens when a memory is added to the grouped memories while/after syncing
        if (syncedConversationsPointers.where((element) => element.key == date).isNotEmpty) {
          var len = syncedConversationsPointers.where((element) => element.key == date).length;
          for (var i = 0; i < len; i++) {
            var mem = syncedConversationsPointers.where((element) => element.key == date).elementAt(i);
            var newIdx = groupedConversations[date]!.indexWhere((m) => m.id == mem.memory.id);
            updateSyncedMemoryPointerIndex(mem, newIdx);
          }
        }
      }
    } else {
      groupedConversations[date] = [memory];
      groupedConversations =
          Map.fromEntries(groupedConversations.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
    }
    notifyListeners();
  }

  void updateMemoryInSortedList(ServerConversation memory) {
    var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    if (groupedConversations.containsKey(date)) {
      int idx = groupedConversations[date]!.indexWhere((element) => element.id == memory.id);
      if (idx != -1) {
        groupedConversations[date]![idx] = memory;
      }
    }
    notifyListeners();
  }

  (int, DateTime) addMemoryWithDateGrouped(ServerConversation memory) {
    conversations.insert(0, memory);
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    int idx;
    var memDate = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    if (groupedConversations.containsKey(memDate)) {
      idx = groupedConversations[memDate]!.indexWhere((element) => element.createdAt.isBefore(memory.createdAt));
      if (idx == -1) {
        groupedConversations[memDate]!.insert(0, memory);
        idx = 0;
      } else {
        groupedConversations[memDate]!.insert(idx, memory);
      }
    } else {
      groupedConversations[memDate] = [memory];
      groupedConversations =
          Map.fromEntries(groupedConversations.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
      idx = 0;
    }
    return (idx, memDate);
  }

  void updateMemory(ServerConversation memory, [int? index]) {
    if (index != null) {
      conversations[index] = memory;
    } else {
      int i = conversations.indexWhere((element) => element.id == memory.id);
      if (i != -1) {
        conversations[i] = memory;
      }
    }
    conversations.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    filterGroupedConversations('');
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

  void deleteMemoryLocally(ServerConversation memory, int index, DateTime date) {
    memoriesToDelete[memory.id] = memory;
    conversations.removeWhere((element) => element.id == memory.id);
    groupedConversations[date]!.removeAt(index);
    if (groupedConversations[date]!.isEmpty) {
      groupedConversations.remove(date);
    }
    notifyListeners();
  }

  void deleteMemoryOnServer(String memoryId) {
    deleteConversationServer(memoryId);
    memoriesToDelete.remove(memoryId);
  }

  void undoDeleteMemory(String memoryId, int index) {
    if (memoriesToDelete.containsKey(memoryId)) {
      ServerConversation memory = memoriesToDelete.remove(memoryId)!;
      conversations.insert(0, memory);
      addMemoryToGroupedConversations(memory);
    }
    notifyListeners();
  }

  /////////////////////////////////////////////////////////////////

  void deleteMemory(ServerConversation memory, int index) {
    conversations.removeWhere((element) => element.id == memory.id);
    deleteConversationServer(memory.id);
    filterGroupedConversations('');
    notifyListeners();
  }

  @override
  void dispose() {
    _processingMemoryWatchTimer?.cancel();
    _wal.unsubscribe(this);
    super.dispose();
  }

  @override
  void onMissingWalUpdated() async {
    _missingWals = await _wal.getSyncs().getMissingWals();
    notifyListeners();
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? memory}) async {
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
      if (res.newMemoryIds.isNotEmpty || res.updatedMemoryIds.isNotEmpty) {
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
      if (res.newMemoryIds.isNotEmpty || res.updatedMemoryIds.isNotEmpty) {
        print('Synced memories: ${res.newMemoryIds} ${res.updatedMemoryIds}');
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
    List<dynamic> newConversations = syncResult.newMemoryIds;
    List<dynamic> updatedConversations = syncResult.updatedMemoryIds;
    setIsFetchingConversations(true);
    List<Future<ServerConversation?>> newConversationsFutures =
        newConversations.map((item) => getMemoryDetails(item)).toList();

    List<Future<ServerConversation?>> updatedConversationsFutures =
        updatedConversations.map((item) => getMemoryDetails(item)).toList();
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
      for (var memory in syncedConversations['new_memories']!) {
        if (memory != null && memory.status == MemoryStatus.completed) {
          addMemory(memory);
        }
      }
    }
    if (syncedConversations['updated_memories'] != []) {
      for (var memory in syncedConversations['updated_memories']!) {
        if (memory != null && memory.status == MemoryStatus.completed) {
          upsertMemory(memory);
        }
      }
    }
    for (var memory in syncedConversations['new_memories']!) {
      if (memory != null && memory.status == MemoryStatus.completed) {
        var res = getMemoryDateAndIndex(memory);
        syncedConversationsPointers.add(SyncedConversationPointer(
            type: SyncedConversationType.newConversation, index: res.$2, key: res.$1, memory: memory));
      }
    }
    if (syncedConversations['updated_memories'] != []) {
      for (var memory in syncedConversations['updated_memories']!) {
        if (memory != null && memory.status == MemoryStatus.completed) {
          var res = getMemoryDateAndIndex(memory);
          syncedConversationsPointers.add(SyncedConversationPointer(
              type: SyncedConversationType.newConversation, index: res.$2, key: res.$1, memory: memory));
        }
      }
    }
  }

  void updateSyncedMemoryPointerIndex(SyncedConversationPointer mem, int index) {
    var oldIdx = syncedConversationsPointers.indexOf(mem);
    syncedConversationsPointers[oldIdx] = mem.copyWith(index: index);
    notifyListeners();
  }

  void updateSyncedMemory(ServerConversation memory) {
    var id = syncedConversationsPointers.indexWhere((element) => element.memory.id == memory.id);
    if (id != -1) {
      syncedConversationsPointers[id] = syncedConversationsPointers[id].copyWith(memory: memory);
    }
    updateMemoryInSortedList(memory);
    notifyListeners();
  }

  (DateTime, int) getMemoryDateAndIndex(ServerConversation memory) {
    var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    var idx = groupedConversations[date]!.indexWhere((element) => element.id == memory.id);
    if (idx == -1 && groupedConversations.containsKey(date)) {
      groupedConversations[date]!.add(memory);
    }
    return (date, idx);
  }

  Future<ServerConversation?> getMemoryDetails(String memoryId) async {
    var memory = await getConversationById(memoryId);
    return memory;
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
}
