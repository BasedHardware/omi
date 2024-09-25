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

  void toggleDiscardMemories() {
    MixpanelManager().showDiscardedMemoriesToggled(!SharedPreferencesUtil().showDiscardedMemories);
    SharedPreferencesUtil().showDiscardedMemories = !SharedPreferencesUtil().showDiscardedMemories;
    filterSortedMemories('');
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
    sortMemoriesByDate();
    notifyListeners();
  }

/////////////////////////////////////////////////////////////////////////////////

  void sortMemoriesByDate() {
    groupedMemories = {};
    for (var memory in memories) {
      if (SharedPreferencesUtil().showDiscardedMemories && memory.discarded) continue;
      var date = DateTime(memory.createdAt.year, memory.createdAt.month, memory.createdAt.day);
      if (!groupedMemories.containsKey(date)) {
        groupedMemories[date] = [];
      }
      groupedMemories[date]!.add(memory);
      groupedMemories[date]!.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    }
    print('grouped memories: ${groupedMemories.length}');
    notifyListeners();
  }

  void filterSortedMemories(String query) {
    if (query.isEmpty) {
      groupedMemories = {};
      sortMemoriesByDate();
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
          groupedMemories[date]!.add(memory);
        }
      }
    }
    notifyListeners();
  }
/////////////////////////////////////////////////////////////////////////////////

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
    filterSortedMemories('');
    setLoadingMemories(false);
    notifyListeners();
  }

  void addMemory(ServerMemory memory) {
    memories.insert(0, memory);
    addMemoryToSortedList(memory);
    notifyListeners();
  }

  void addMemoryToSortedList(ServerMemory memory) {
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
      idx = groupedMemories[memDate]!.indexWhere((element) => element.createdAt.isBefore(memory.createdAt));
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
    filterSortedMemories('');
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
      print('Creating event: ${events[i].title}');
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
      addMemoryToSortedList(memory);
    }
    notifyListeners();
  }
  /////////////////////////////////////////////////////////////////

  void deleteMemory(ServerMemory memory, int index) {
    memories.removeWhere((element) => element.id == memory.id);
    deleteMemoryServer(memory.id);
    // filterMemories('');
    filterSortedMemories('');
    notifyListeners();
  }
}
