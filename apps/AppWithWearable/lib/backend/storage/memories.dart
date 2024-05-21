import 'package:audioplayers/audioplayers.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:shared_preferences/shared_preferences.dart';

class MemoryRecord {
  String id;
  DateTime date;
  String rawMemory;
  String structuredMemory;
  bool isEmpty;
  bool isUseless;
  String? audioFileName;
  PlayerState playerState = PlayerState.stopped;

  MemoryRecord({
    required this.id,
    required this.date,
    required this.rawMemory,
    required this.structuredMemory,
    required this.isEmpty,
    required this.isUseless,
    this.audioFileName,
  });

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'date': date.toIso8601String(),
      'rawMemory': rawMemory,
      'structuredMemory': structuredMemory,
      'isEmpty': isEmpty,
      'isUseless': isUseless,
      'audioFileName': audioFileName ?? '',
    };
  }

  factory MemoryRecord.fromJson(Map<String, dynamic> json) {
    return MemoryRecord(
      id: json['id'],
      date: DateTime.parse(json['date']),
      rawMemory: json['rawMemory'],
      structuredMemory: json['structuredMemory'],
      isEmpty: json['isEmpty'],
      isUseless: json['isUseless'],
      audioFileName: json['audioFileName'],
    );
  }

  static String memoriesToString(List<MemoryRecord> memories) =>
      memories.map((e) => '${e.date.toIso8601String().split('.')[0]}\n${e.structuredMemory}').join('\n\n');
}

class MemoryStorage {
  static const String _storageKey = 'memories';

  static Future<void> addMemory(MemoryRecord memory) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    allMemories.add(jsonEncode(memory.toJson()));
    await prefs.setStringList(_storageKey, allMemories);
  }

  static Future<List<MemoryRecord>> getAllMemories({bool filterOutUseless = true}) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    List<MemoryRecord> memories =
        allMemories.reversed.map((memory) => MemoryRecord.fromJson(jsonDecode(memory))).toList();
    if (!filterOutUseless) {
      return memories.where((memory) => !(memory.rawMemory.split(' ').length < 10)).toList();
    }
    return memories.where((memory) => !memory.isUseless).toList();
  }

  static Future<List<MemoryRecord>> getAllMemoriesByIds(List<String> memoriesId) async {
    List<MemoryRecord> memories = await getAllMemories();
    List<MemoryRecord> filtered = [];
    for (MemoryRecord memory in memories) {
      if (memoriesId.contains(memory.id)) {
        filtered.add(memory);
      }
    }
    return filtered;
  }

  static Future<List<MemoryRecord>> retrieveRecentMemoriesWithinMinutes({int minutes = 10, int count = 2}) async {
    List<MemoryRecord> allMemories = await getAllMemories();
    DateTime now = DateTime.now();
    DateTime timeLimit = now.subtract(Duration(minutes: minutes));
    var filtered = allMemories.where((memory) => memory.date.isAfter(timeLimit)).toList();
    if (filtered.length > count) {
      filtered = filtered.sublist(0, count);
    }
    return filtered;
  }

  static Future<void> updateMemory(String memoryId, String updatedMemory) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    int index = allMemories.indexWhere((memory) => MemoryRecord.fromJson(jsonDecode(memory)).id == memoryId);
    if (index >= 0 && index < allMemories.length) {
      MemoryRecord oldMemory = MemoryRecord.fromJson(jsonDecode(allMemories[index]));
      MemoryRecord updatedRecord = MemoryRecord(
        id: oldMemory.id,
        date: oldMemory.date,
        rawMemory: oldMemory.rawMemory,
        structuredMemory: updatedMemory,
        isEmpty: updatedMemory.isEmpty,
        isUseless: updatedMemory.isEmpty,
      );
      allMemories[index] = jsonEncode(updatedRecord.toJson());
      await prefs.setStringList(_storageKey, allMemories);
    }
  }

  static Future<void> deleteMemory(String memoryId) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    int index = allMemories.indexWhere((memory) => MemoryRecord.fromJson(jsonDecode(memory)).id == memoryId);
    if (index >= 0 && index < allMemories.length) {
      allMemories.removeAt(index);
      await prefs.setStringList(_storageKey, allMemories);
    }
  }

  static Future<List<MemoryRecord>> getMemoriesByDay(DateTime day) async {
    List<MemoryRecord> allMemories = await getAllMemories();
    return allMemories.where((memory) => isSameDay(memory.date, day)).toList();
  }

  static Future<List<MemoryRecord>> getMemoriesOfLastWeek() async {
    DateTime now = DateTime.now();
    DateTime lastWeekStart = now.subtract(Duration(days: now.weekday + 6));
    List<MemoryRecord> allMemories = await getAllMemories();
    return allMemories.where((memory) => memory.date.isAfter(lastWeekStart) && memory.date.isBefore(now)).toList();
  }

  static Future<List<MemoryRecord>> getMemoriesOfLastMonth() async {
    DateTime now = DateTime.now();
    DateTime lastMonthStart = DateTime(now.year, now.month - 1, 1);
    List<MemoryRecord> allMemories = await getAllMemories();
    return allMemories.where((memory) => memory.date.isAfter(lastMonthStart) && memory.date.isBefore(now)).toList();
  }

  static bool isSameDay(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month && a.day == b.day;
  }

  static insertMemoryAtIndex(MemoryRecord memory, {int index = 0}) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    allMemories.insert(index, jsonEncode(memory.toJson()));
    await prefs.setStringList(_storageKey, allMemories);
  }

  static setMostRecentMemoryInProgress() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    if (allMemories.isNotEmpty) {
      MemoryRecord firstMemory = MemoryRecord.fromJson(jsonDecode(allMemories[0]));
      if (firstMemory.structuredMemory == 'in_progress') {
        return;
      }
    }
    insertMemoryAtIndex(MemoryRecord(
      id: '1',
      date: DateTime.now(),
      rawMemory: 'in_progress',
      structuredMemory: 'in_progress',
      isEmpty: true,
      isUseless: true,
    ));
  }
}
