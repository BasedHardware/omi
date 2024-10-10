import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';

class MemoryProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  List<ServerMemory> memories = [];
  Map<DateTime, List<ServerMemory>> groupedMemories = {};

  bool isLoadingMemories = false;
  bool hasNonDiscardedMemories = true;

  String previousQuery = '';

  Timer? _processingMemoryWatchTimer;

  List<ServerMemory> processingMemories = [];

  IWalService get _walService => ServiceManager.instance().wal;

  List<Wal> _missingWals = [];
  List<Wal> get missingWals => _missingWals;
  int get missingWalsInSeconds =>
      _missingWals.isEmpty ? 0 : _missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

  double _walsSyncedProgress = 0.0;
  double get walsSyncedProgress => _walsSyncedProgress;

  bool isSyncing = false;
  bool syncCompleted = false;
  Map<String, dynamic>? syncResult;
  Map<String, List<ServerMemory?>>? syncedMemories;
  Map<String, List<Record>>? syncedMemoriesPointers;

  MemoryProvider() {
    _walService.subscribe(this, this);
    _preload();
  }

  _preload() async {
    _missingWals = await _walService.getMissingWals();
    notifyListeners();
  }

  void addProcessingMemory(ServerMemory memory) {
    processingMemories.add(memory);
    notifyListeners();
  }

  void removeProcessingMemory(String memoryId) {
    processingMemories.removeWhere((m) => m.id == memoryId);
    notifyListeners();
  }

  void onMemoryTap(int idx) {
    if (idx < 0 || idx > memories.length - 1) {
      return;
    }
    var changed = false;
    if (memories[idx].isNew) {
      memories[idx].isNew = false;
      changed = true;
    }
    if (changed) {
      filterGroupedMemories('');
    }
  }

  void toggleDiscardMemories() {
    MixpanelManager().showDiscardedMemoriesToggled(!SharedPreferencesUtil().showDiscardedMemories);
    SharedPreferencesUtil().showDiscardedMemories = !SharedPreferencesUtil().showDiscardedMemories;
    filterGroupedMemories('');
    notifyListeners();
  }

  void setLoadingMemories(bool value) {
    isLoadingMemories = value;
    notifyListeners();
  }

  Future getInitialMemories() async {
    memories = await getMemoriesFromServer();

    processingMemories = memories.where((m) => m.status == MemoryStatus.processing).toList();

    memories = memories.where((m) => m.status == MemoryStatus.completed).toList();

    if (memories.isEmpty) {
      memories = SharedPreferencesUtil().cachedMemories;
    } else {
      SharedPreferencesUtil().cachedMemories = memories;
    }
    _groupMemoriesByDateWithoutNotify();
    notifyListeners();
  }

  void _groupMemoriesByDateWithoutNotify() {
    groupedMemories = {};
    for (var memory in memories) {
      if (SharedPreferencesUtil().showDiscardedMemories && memory.discarded && !memory.isNew) continue;
      var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
      if (!groupedMemories.containsKey(date)) {
        groupedMemories[date] = [];
      }
      groupedMemories[date]?.add(memory);
    }
    // Sort
    for (final date in groupedMemories.keys) {
      groupedMemories[date]?.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    }
  }

  void groupMemoriesByDate() {
    _groupMemoriesByDateWithoutNotify();
    notifyListeners();
  }

  void _filterGroupedMemoriesWithoutNotify(String query) {
    if (query.isEmpty) {
      groupedMemories = {};
      _groupMemoriesByDateWithoutNotify();
    } else {
      groupedMemories = {};
      for (var memory in memories) {
        var date = memory.createdAt;
        if (!groupedMemories.containsKey(date)) {
          groupedMemories[date] = [];
        }
        if ((memory.getTranscript() + memory.structured.title + memory.structured.overview)
            .toLowerCase()
            .contains(query.toLowerCase())) {
          groupedMemories[date]?.add(memory);
        }
      }
    }
  }

  void filterGroupedMemories(String query) {
    _filterGroupedMemoriesWithoutNotify(query);
    notifyListeners();
  }

  Future getMemoriesFromServer() async {
    setLoadingMemories(true);
    var mem = await getMemories();
    memories = mem;
    memories.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    createEventsForMemories();
    setLoadingMemories(false);
    notifyListeners();
    return memories;
  }

  void createEventsForMemories() {
    for (var memory in memories) {
      if (memory.structured.events.isNotEmpty &&
          !memory.structured.events.first.created &&
          memory.startedAt!.isAfter(DateTime.now().add(const Duration(days: -1)))) {
        _handleCalendarCreation(memory);
      }
    }
  }

  Future getMoreMemoriesFromServer() async {
    if (memories.length % 50 != 0) return;
    if (isLoadingMemories) return;
    setLoadingMemories(true);
    var newMemories = await getMemories(offset: memories.length);
    memories.addAll(newMemories);
    memories.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    filterGroupedMemories('');
    setLoadingMemories(false);
    notifyListeners();
  }

  void addMemory(ServerMemory memory) {
    memories.insert(0, memory);
    addMemoryToGroupedMemories(memory);
    notifyListeners();
  }

  void upsertMemory(ServerMemory memory) {
    int idx = memories.indexWhere((m) => m.id == memory.id);
    if (idx < 0) {
      addMemory(memory);
    } else {
      updateMemory(memory, idx);
    }
  }

  void addMemoryToGroupedMemories(ServerMemory memory) {
    var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    if (groupedMemories.containsKey(date)) {
      groupedMemories[date]!.insert(0, memory);
      groupedMemories[date]!.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    } else {
      groupedMemories[date] = [memory];
      groupedMemories = Map.fromEntries(groupedMemories.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
    }
    notifyListeners();
  }

  void updateMemoryInSortedList(ServerMemory memory) {
    var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    if (groupedMemories.containsKey(date)) {
      int idx = groupedMemories[date]!.indexWhere((element) => element.id == memory.id);
      if (idx != -1) {
        groupedMemories[date]![idx] = memory;
      }
    }
    notifyListeners();
  }

  (int, DateTime) addMemoryWithDateGrouped(ServerMemory memory) {
    memories.insert(0, memory);
    memories.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    int idx;
    var memDate = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    if (groupedMemories.containsKey(memDate)) {
      idx = groupedMemories[memDate]!.indexWhere((element) => element.createdAt.isBefore(memory.createdAt));
      if (idx == -1) {
        groupedMemories[memDate]!.insert(0, memory);
        idx = 0;
      } else {
        groupedMemories[memDate]!.insert(idx, memory);
      }
    } else {
      groupedMemories[memDate] = [memory];
      groupedMemories = Map.fromEntries(groupedMemories.entries.toList()..sort((a, b) => b.key.compareTo(a.key)));
      idx = 0;
    }
    return (idx, memDate);
  }

  void updateMemory(ServerMemory memory, [int? index]) {
    if (index != null) {
      memories[index] = memory;
    } else {
      int i = memories.indexWhere((element) => element.id == memory.id);
      if (i != -1) {
        memories[i] = memory;
      }
    }
    memories.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    filterGroupedMemories('');
    notifyListeners();
  }

  _handleCalendarCreation(ServerMemory memory) {
    if (!SharedPreferencesUtil().calendarEnabled) return;
    if (SharedPreferencesUtil().calendarType != 'auto') return;

    List<Event> events = memory.structured.events;
    if (events.isEmpty) return;

    List<int> indexes = events.mapIndexed((index, e) => index).toList();
    setMemoryEventsState(memory.id, indexes, indexes.map((_) => true).toList());
    for (var i = 0; i < events.length; i++) {
      if (events[i].created) continue;
      events[i].created = true;
      CalendarUtil().createEvent(
        events[i].title,
        events[i].startsAt,
        events[i].duration,
        description: events[i].description,
      );
    }
  }

  /////////////////////////////////////////////////////////////////
  ////////// Delete Memory With Undo Functionality ///////////////

  Map<String, ServerMemory> memoriesToDelete = {};

  void deleteMemoryLocally(ServerMemory memory, int index, DateTime date) {
    memoriesToDelete[memory.id] = memory;
    memories.removeWhere((element) => element.id == memory.id);
    groupedMemories[date]!.removeAt(index);
    if (groupedMemories[date]!.isEmpty) {
      groupedMemories.remove(date);
    }
    notifyListeners();
  }

  void deleteMemoryOnServer(String memoryId) {
    deleteMemoryServer(memoryId);
    memoriesToDelete.remove(memoryId);
  }

  void undoDeleteMemory(String memoryId, int index) {
    if (memoriesToDelete.containsKey(memoryId)) {
      ServerMemory memory = memoriesToDelete.remove(memoryId)!;
      memories.insert(0, memory);
      addMemoryToGroupedMemories(memory);
    }
    notifyListeners();
  }

  /////////////////////////////////////////////////////////////////

  void deleteMemory(ServerMemory memory, int index) {
    memories.removeWhere((element) => element.id == memory.id);
    deleteMemoryServer(memory.id);
    filterGroupedMemories('');
    notifyListeners();
  }

  @override
  void dispose() {
    _processingMemoryWatchTimer?.cancel();
    _walService.unsubscribe(this);
    super.dispose();
  }

  @override
  void onNewMissingWal(Wal wal) async {
    _missingWals = await _walService.getMissingWals();
    notifyListeners();
  }

  @override
  void onWalSynced(Wal wal, {ServerMemory? memory}) async {
    _missingWals = await _walService.getMissingWals();
    notifyListeners();
  }

  @override
  void onStatusChanged(WalServiceStatus status) {}

  @override
  void onWalSyncedProgress(double percentage) {
    _walsSyncedProgress = percentage;
  }

  Future<Map<String, dynamic>?> syncWals() async {
    _walsSyncedProgress = 0.0;
    setIsSyncing(true);
    var res = await _walService.syncAll(progress: this);
    syncResult = res.$1;
    if (syncResult != null) {
      if (syncResult!['new_memories'] != [] || syncResult!['updated_memories']) {
        syncedMemories = {};
        await getSyncedMemoriesData();
        addSyncedMemoriesToGroupedMemories();
      }
    }
    syncCompleted = true;
    setIsSyncing(false);
    notifyListeners();
    return res.$1;
  }

  Future getSyncedMemoriesData() async {
    List<dynamic> newMemories = syncResult!['new_memories'] ?? [];
    List<dynamic> updatedMemories = syncResult!['updated_memories'] ?? [];

    List<Future<ServerMemory?>> newMemoriesFutures = newMemories.map((item) => getMemoryDetails(item)).toList();

    List<Future<ServerMemory?>> updatedMemoriesFutures = updatedMemories.map((item) => getMemoryDetails(item)).toList();
    try {
      final newMemoriesResponses = await Future.wait(newMemoriesFutures);
      syncedMemories!['new_memories'] = newMemoriesResponses;

      final updatedMemoriesResponses = await Future.wait(updatedMemoriesFutures);
      syncedMemories!['updated_memories'] = updatedMemoriesResponses;
    } catch (e) {
      print('Error during API calls: $e');
    }
  }

  void addSyncedMemoriesToGroupedMemories() {
    syncedMemoriesPointers = {'new_memories': [], 'updated_memories': []};
    if (syncedMemories == null) return;
    if (syncedMemories!['new_memories'] != null) {
      for (var memory in syncedMemories!['new_memories']!) {
        if (memory != null) {
          addMemory(memory);
          syncedMemoriesPointers!['new_memories']!.add(getMemoryDateAndIndex(memory));
        }
      }
    }
    if (syncedMemories!['updated_memories'] != null) {
      for (var memory in syncedMemories!['updated_memories']!) {
        if (memory != null && memory.status == MemoryStatus.completed) {
          updateMemoryInSortedList(memory);
          syncedMemoriesPointers!['updated_memories']!.add(getMemoryDateAndIndex(memory));
        }
      }
    }
  }

  void updateSyncedMemory(ServerMemory memory) {
    if (syncedMemoriesPointers!['updated_memories'] != null) {
      var idx = syncedMemoriesPointers!['updated_memories']!.indexWhere((element) {
        dynamic e = element;
        return e.$3.id == memory.id;
      });
      if (idx != -1) {
        updateMemory(memory);
        syncedMemoriesPointers!['updated_memories']![idx] = getMemoryDateAndIndex(memory);
      }
    }
  }

  (DateTime, int, ServerMemory) getMemoryDateAndIndex(ServerMemory memory) {
    var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
    var idx = groupedMemories[date]!.indexWhere((element) => element.id == memory.id);
    if (idx == -1 && groupedMemories.containsKey(date)) {
      groupedMemories[date]!.add(memory);
    }
    return (date, idx, memory);
  }

  Future<ServerMemory?> getMemoryDetails(String memoryId) async {
    var memory = await getMemoryById(memoryId);
    return memory;
  }

  void clearSyncResult() {
    syncResult = null;
    syncCompleted = false;
    notifyListeners();
  }

  void setIsSyncing(bool value) {
    isSyncing = value;
    notifyListeners();
  }
}
