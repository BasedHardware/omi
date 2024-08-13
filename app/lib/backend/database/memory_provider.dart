import 'dart:convert';

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

  List<Memory> getMemories() => _box.getAll();

  List<int> storeMemories(List<Memory> memories) => _box.putMany(memories);
}

String getPrettyJSONString(jsonObject) {
  var encoder = const JsonEncoder.withIndent("     ");
  return encoder.convert(jsonObject);
}
