import 'dart:convert';
import 'dart:math';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:friend_private/backend/utils.dart';

class Structured {
  String title;
  String overview;
  List<String> actionItems;
  List<String> pluginsResponse;
  String emoji;
  String category;

  Structured({
    this.title = "",
    this.overview = "",
    required this.actionItems,
    required this.pluginsResponse,
    this.emoji = '',
    this.category = '',
  });

  factory Structured.fromJson(Map<String, dynamic> json) => Structured(
      title: json['title'] ?? '',
      overview: json['overview'] ?? '',
      actionItems: List<String>.from(json['action_items'] ?? []),
      pluginsResponse: List<String>.from(json['pluginsResponse'] ?? []),
      category: json['category'] ?? '',
      emoji: json['emoji'] ?? '');

  Map<String, dynamic> toJson() => {
        'title': title,
        'overview': overview,
        'action_items': List<dynamic>.from(actionItems),
        'pluginsResponse': List<dynamic>.from(pluginsResponse),
        'emoji': emoji,
        'category': category,
      };

  getEmoji() {
    try {
      return utf8.decode(emoji.toString().codeUnits);
    } catch (e) {
      return ['🧠', '😎', '🧑‍💻', '🎂'][Random().nextInt(4)];
    }
  }

  @override
  String toString() {
    var str = '';
    str += '${getEmoji()} $title ($category)\n\nSummary: $overview\n\n';
    if (actionItems.isNotEmpty) {
      str += 'Action Items:\n';
      for (var item in actionItems) {
        str += '- $item\n';
      }
    }
    return str;
  }
}

class MemoryRecord {
  String id;
  DateTime createdAt;
  String transcript;
  String? recordingFilePath;
  Structured structured;
  bool discarded;

  MemoryRecord({
    required this.transcript,
    required this.id,
    required this.createdAt,
    required this.structured,
    this.recordingFilePath,
    this.discarded = false,
  });

  factory MemoryRecord.fromJson(Map<String, dynamic> json) => MemoryRecord(
        transcript: json['transcript'],
        id: json['id'],
        recordingFilePath: json['recording_file_path'],
        createdAt: DateTime.parse(json['created_at']),
        structured: Structured.fromJson(json['structured']),
        discarded: json['discarded'] ?? false,
      );

  Map<String, dynamic> toJson() => {
        'transcript': transcript,
        'id': id,
        'created_at': createdAt.toIso8601String(),
        'structured': structured.toJson(),
        'recording_audio_path': recordingFilePath,
        'discarded': discarded,
      };

  static List<MemoryRecord> fromJsonList(List<dynamic> jsonList) {
    List<MemoryRecord> memories = [];
    for (var json in jsonList) {
      memories.add(MemoryRecord.fromJson(json));
    }
    return memories;
  }

  String getStructuredString() => structured.toString();

  static String memoriesToString(List<MemoryRecord> memories) => memories
    .map((e) {
      var memoryString = '''
        ${e.createdAt.toIso8601String().split('.')[0]}
        Title: ${e.structured.title}
        Summary: ${e.structured.overview}
        ${e.structured.actionItems.isNotEmpty ? 'Action Items:' : ''}
        ${e.structured.actionItems.map((item) => '  - $item').join('\n')}
        ${e.structured.pluginsResponse.isNotEmpty ? 'Plugins Response:' : ''}
        ${e.structured.pluginsResponse.map((response) => '  - $response').join('\n')}
        Category: ${e.structured.category}
      ''';
      return cleanPrompt(memoryString);
    })
    .join('\n\n');
  }

class MemoryStorage {
  static const String _storageKey = '_memories';

  static Future<void> addMemory(MemoryRecord memory) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    allMemories.add(jsonEncode(memory.toJson()));
    await prefs.setStringList(_storageKey, allMemories);
  }

  static Future<List<MemoryRecord>> getAllMemories({includeDiscarded = false}) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    List<MemoryRecord> memories =
        allMemories.reversed.map((memory) => MemoryRecord.fromJson(jsonDecode(memory))).toList();
    if (includeDiscarded) return memories.where((memory) => memory.transcript.split(' ').length > 10).toList();
    return memories.where((memory) => !memory.discarded).toList();
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
    var filtered = allMemories.where((memory) => memory.createdAt.isAfter(timeLimit)).toList();
    if (filtered.length > count) {
      filtered = filtered.sublist(0, count);
    }
    return filtered;
  }

  static Future<void> updateWholeMemory(MemoryRecord newMemory) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    int index = allMemories.indexWhere((memory) => MemoryRecord.fromJson(jsonDecode(memory)).id == newMemory.id);
    if (index >= 0 && index < allMemories.length) {
      allMemories[index] = jsonEncode(newMemory.toJson());
      await prefs.setStringList(_storageKey, allMemories);
    }
  }

  static Future<void> updateMemory(String memoryId, String updatedTitle, String updatedDescription) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    List<String> allMemories = prefs.getStringList(_storageKey) ?? [];
    int index = allMemories.indexWhere((memory) => MemoryRecord.fromJson(jsonDecode(memory)).id == memoryId);
    if (index >= 0 && index < allMemories.length) {
      MemoryRecord oldMemory = MemoryRecord.fromJson(jsonDecode(allMemories[index]));
      MemoryRecord updatedRecord = MemoryRecord(
        id: oldMemory.id,
        createdAt: oldMemory.createdAt,
        transcript: oldMemory.transcript,
        recordingFilePath: oldMemory.recordingFilePath,
        structured: Structured(
          title: updatedTitle,
          overview: updatedDescription,
          actionItems: oldMemory.structured.actionItems,
          pluginsResponse: oldMemory.structured.pluginsResponse,
          category: oldMemory.structured.category,
        ),
        discarded: oldMemory.discarded,
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
    return allMemories.where((memory) => isSameDay(memory.createdAt, day)).toList();
  }

  static Future<List<MemoryRecord>> getMemoriesOfLastWeek() async {
    DateTime now = DateTime.now();
    DateTime lastWeekStart = now.subtract(Duration(days: now.weekday + 6));
    List<MemoryRecord> allMemories = await getAllMemories();
    return allMemories
        .where((memory) => memory.createdAt.isAfter(lastWeekStart) && memory.createdAt.isBefore(now))
        .toList();
  }

  static Future<List<MemoryRecord>> getMemoriesOfLastMonth() async {
    DateTime now = DateTime.now();
    DateTime lastMonthStart = DateTime(now.year, now.month - 1, 1);
    List<MemoryRecord> allMemories = await getAllMemories();
    return allMemories
        .where((memory) => memory.createdAt.isAfter(lastMonthStart) && memory.createdAt.isBefore(now))
        .toList();
  }

  static bool isSameDay(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month && a.day == b.day;
  }
}
