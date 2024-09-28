import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';

class MemoryProvider extends ChangeNotifier {
  List<ServerMemory> memories = [];
  Map<DateTime, List<ServerMemory>> groupedMemories = {};

  bool isLoadingMemories = false;
  bool hasNonDiscardedMemories = true;

  String previousQuery = '';

  List<ServerProcessingMemory> processingMemories = [];
  Timer? _processingMemoryWatchTimer;

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
    if (memories.isEmpty) {
      memories = SharedPreferencesUtil().cachedMemories;
    } else {
      SharedPreferencesUtil().cachedMemories = memories;
    }
    _groupMemoriesByDateWithoutNotify();

    // Processing memories
    var pms = await getProcessingMemories();
    await _setProcessingMemories(pms);

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

  Future _setProcessingMemories(List<ServerProcessingMemory> pms) async {
    processingMemories = pms;
    notifyListeners();

    if (processingMemories.isEmpty) {
      _processingMemoryWatchTimer?.cancel();
      return;
    }

    _trackProccessingMemories();
    return;
  }

  Future onNewCombiningMemory(ServerProcessingMemory pm) async {
    if (pm.memoryId == null) {
      debugPrint("Processing Memory Id is not found ${pm.id}");
      return;
    }
    int idx = memories.indexWhere((m) => m.id == pm.memoryId);
    if (idx < 0) {
      return;
    }
    memories.removeAt(idx);

    filterGroupedMemories('');
  }

  Future onNewProcessingMemory(ServerProcessingMemory processingMemory) async {
    if (processingMemories.indexWhere((pm) => pm.id == processingMemory.id) >= 0) {
      // existed
      debugPrint("Processing memory is existed");
      return;
    }
    if (processingMemory.status != ServerProcessingMemoryStatus.processing) {
      // track processing status only
      debugPrint("Processing memory status is not processing");
      return;
    }
    processingMemories.insert(0, processingMemory);
    _setProcessingMemories(List.from(processingMemories));
  }

  Future onProcessingMemoryDone(ServerProcessingMemory pm) async {
    if (pm.memoryId == null) {
      debugPrint("Processing Memory Id is not found ${pm.id}");
      return;
    }
    var memory = await getMemoryById(pm.memoryId!);
    if (memory == null) {
      debugPrint("Memory is not found ${pm.memoryId}");
      return;
    }

    // local labling
    memory.isNew = true;

    int idx = memories.indexWhere((m) => m.id == memory.id);
    if (idx < 0) {
      memories.insert(0, memory);
    } else {
      memories[idx] = memory;
    }

    filterGroupedMemories('');
  }

  Future _updateProcessingMemories(List<ServerProcessingMemory> pms) async {
    for (var i = 0; i < processingMemories.length; i++) {
      var pm = pms.firstWhereOrNull((m) => m.id == processingMemories[i].id);
      if (pm != null) {
        processingMemories[i] = pm;
      }
    }
    _setProcessingMemories(List.from(processingMemories));
  }

  void _trackProccessingMemories() {
    if (_processingMemoryWatchTimer?.isActive ?? false) {
      return;
    }
    _processingMemoryWatchTimer?.cancel();
    _processingMemoryWatchTimer = Timer(const Duration(seconds: 7), () async {
      debugPrint("processing memory tracking...");
      var filterIds = processingMemories
          .where((m) => m.status == ServerProcessingMemoryStatus.processing)
          .map((m) => m.id)
          .toList();
      if (filterIds.isEmpty) {
        return;
      }

      var pms = await getProcessingMemories(filterIds: filterIds);
      for (var i = 0; i < pms.length; i++) {
        if (pms[i].status == ServerProcessingMemoryStatus.done) {
          onProcessingMemoryDone(pms[i]);
        }
      }
      _updateProcessingMemories(pms);
    });
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
    super.dispose();
  }
}
