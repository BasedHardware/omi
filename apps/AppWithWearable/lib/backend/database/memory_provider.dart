import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/objectbox.g.dart';

class MemoryProvider {
  static final MemoryProvider _instance = MemoryProvider._internal();
  static final Box<Memory> _box = ObjectBoxUtil().box!.store.box<Memory>();

  factory MemoryProvider() {
    return _instance;
  }

  MemoryProvider._internal();

  Future<List<Memory>> getMemories() async {
    return _box.getAll();
  }

  Future<List<Memory>> getMemoriesOrdered({bool includeDiscarded = false}) async {
    if (includeDiscarded) {
      return _box.query().build().find();
    } else {
      return _box.query(Memory_.discarded.equals(false)).build().find();
    }
  }

  Future<void> saveMemory(Memory memory) async {
    _box.put(memory);
  }

  Future<void> deleteMemory(Memory memory) async {
    _box.remove(memory.id);
  }

  Future<void> updateMemory(Memory memory) async {
    _box.put(memory);
  }

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
}
