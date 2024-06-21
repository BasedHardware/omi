import 'dart:convert';
import 'dart:io';

import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/objectbox.g.dart';
import 'package:path_provider/path_provider.dart';

class MemoryProvider {
  static final MemoryProvider _instance = MemoryProvider._internal();
  static final Box<Memory> _box = ObjectBoxUtil().box!.store.box<Memory>();
  static final Box<Structured> _boxStructured = ObjectBoxUtil().box!.store.box<Structured>();

  factory MemoryProvider() {
    return _instance;
  }

  MemoryProvider._internal();

  Future<List<Memory>> getMemories() async {
    return _box.getAll();
  }

  Future<List<Memory>> getMemoriesOrdered({bool includeDiscarded = false}) async {
    if (includeDiscarded) {
      // created at descending
      return _box.query().order(Memory_.createdAt).build().find();
    } else {
      return _box
          .query(Memory_.discarded.equals(false))
          .order(Memory_.createdAt, flags: Order.descending)
          .build()
          .find();
    }
  }

  Future<void> saveMemory(Memory memory) async {
    _box.put(memory);
  }

  bool deleteMemory(Memory memory) => _box.remove(memory.id);

  int updateMemory(Memory memory) => _box.put(memory);

  int updateMemoryStructured(Structured structured) => _boxStructured.put(structured);

  Future<Memory?> getMemoryById(int id) async {
    return _box.get(id);
  }

  Future<List<int>> storeMemories(List<Memory> memories) async {
    return _box.putMany(memories);
  }

  Future<int> removeAllMemories() async {
    return _box.removeAll();
  }

  Future<List<Memory>> getMemoriesById(List<int> ids) async {
    List<Memory?> memories = _box.getMany(ids);
    return memories.whereType<Memory>().toList();
  }

  Future<List<Memory>> retrieveRecentMemoriesWithinMinutes({int minutes = 10, int count = 2}) async {
    DateTime timeLimit = DateTime.now().subtract(Duration(minutes: minutes));
    var query = _box.query(Memory_.createdAt.greaterThan(timeLimit.millisecondsSinceEpoch)).build();
    List<Memory> filtered = query.find();
    query.close();

    if (filtered.length > count) filtered = filtered.sublist(0, count);
    return filtered;
  }

  Future<List<Memory>> retrieveDayMemories(DateTime day) async {
    DateTime start = DateTime(day.year, day.month, day.day);
    DateTime end = DateTime(day.year, day.month, day.day, 23, 59, 59);
    var query = _box.query(Memory_.createdAt.between(start.millisecondsSinceEpoch, end.millisecondsSinceEpoch)).build();
    List<Memory> filtered = query.find();
    query.close();
    return filtered;
  }

  Future<File> exportMemoriesToFile() async {
    List<Memory> memories = await getMemories();
    String json = getPrettyJSONString(memories.map((m) => m.toJson()).toList());
    final directory = await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/memories.json');
    await file.writeAsString(json);
    return file;
  }
}

String getPrettyJSONString(jsonObject) {
  var encoder = const JsonEncoder.withIndent("     ");
  return encoder.convert(jsonObject);
}
