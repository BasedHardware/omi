import 'package:friend_private/backend/storage/dvdb/collection.dart';

class DVDB {
  DVDB._internal();

  static final DVDB _shared = DVDB._internal();

  factory DVDB() {
    return _shared;
  }

  final Map<String, Collection> _collections = {};

  Collection collection(String name) {
    if (_collections.containsKey(name)) {
      return _collections[name]!;
    }

    final Collection collection = Collection(name);
    _collections[name] = collection;
    collection.load();
    return collection;
  }

  Collection? getCollection(String name) {
    return _collections[name];
  }

  void releaseCollection(String name) {
    _collections.remove(name);
  }

  void reset() {
    for (final Collection collection in _collections.values) {
      collection.clear();
    }
    _collections.clear();
  }
}
