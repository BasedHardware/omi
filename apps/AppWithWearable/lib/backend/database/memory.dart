import '../../objectbox.g.dart';
import 'box.dart';

@Entity()
class Memory {
  @Id()
  int id = 0;

  @Index()
  @Property(type: PropertyType.date)
  DateTime? createdAt;

  String? transcript;
  String? recordingFilePath;
  Structured? structured;

  @Index()
  bool discarded = false;
}

@Entity()
class Structured {
  @Id()
  int id = 0;

  String title = '';
  String overview = '';
  List<String> actionItems = [];
  List<String> pluginsResponse = [];
  String emoji = '';
  String category = 'other';
}

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

  Future<List<Memory>> getMemoriesOrdered() async {
    return _box.query().order(Memory_.createdAt).build().find();
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
    var memories = _box.getMany(ids);
    return memories.where((element) => element != null).toList() as List<Memory>;
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
