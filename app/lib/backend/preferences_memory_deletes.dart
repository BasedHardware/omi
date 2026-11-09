// Owner-scoped deletion receipts protect memory caches and pending drafts.
// A confirmed delete stays hidden even when one projection write fails.
part of 'preferences.dart';

extension MemoryDeletionPreferences on SharedPreferencesUtil {
  /// Last owner-scoped memory projection used for offline/restart rendering.
  /// Memory.toJson deliberately includes optional temporal fields so a cached
  /// assessment is never mistaken for a newly computed one after restart.
  List<Memory> get cachedMemories {
    final ownerUid = uid;
    if (ownerUid.isEmpty) return [];
    _scopeLegacyUserData(ownerUid);
    final deleted = confirmedMemoryDeletionIds;
    return _decodeCachedList(
      _userScopedKey('cachedMemories', ownerUid),
      (json) => Memory.fromJson(json),
    ).where((memory) => memory.uid == ownerUid && !deleted.contains(memory.id)).toList();
  }

  set cachedMemories(List<Memory> value) {
    final ownerUid = uid;
    if (ownerUid.isEmpty) return;
    final deleted = confirmedMemoryDeletionIds;
    saveStringList(
      _userScopedKey('cachedMemories', ownerUid),
      value.where((memory) => !deleted.contains(memory.id)).map((memory) => jsonEncode(memory.toJson())).toList(),
    );
  }

  /// Confirmed server deletes fence every cached projection, including a
  /// refresh racing cache eviction. IDs are scoped to the signed-in owner.
  Set<String> get confirmedMemoryDeletionIds {
    final ownerUid = uid;
    if (ownerUid.isEmpty) return {};
    return getStringList(_userScopedKey('confirmedMemoryDeletes', ownerUid)).toSet();
  }

  /// Write the marker before removing the cached row. If that write is refused,
  /// try pruning the cache itself; never treat an in-memory preference update
  /// as proof that a confirmed delete will stay hidden after restart.
  Future<void> recordConfirmedMemoryDelete(String id, {required String ownerUid}) async {
    final key = _userScopedKey('confirmedMemoryDeletes', ownerUid);
    var markerSaved = false;
    try {
      markerSaved = await saveStringList(key, {...getStringList(key), id}.toList());
    } catch (error) {
      Logger.debug('Memory deletion marker write failed: ${error.runtimeType}');
    }
    var projectionsSaved = true;
    for (final projection in ['cachedMemories', 'pendingMemories']) {
      final key = _userScopedKey(projection, ownerUid);
      try {
        if (!await saveStringList(
            key, getStringList(key).where((row) => !SharedPreferencesUtil._hasId(row, id)).toList())) {
          projectionsSaved = false;
        }
      } catch (error) {
        Logger.debug('Memory deletion projection write failed: ${error.runtimeType}');
        projectionsSaved = false;
      }
    }
    if (!markerSaved && !projectionsSaved) throw StateError('Could not persist confirmed memory deletion');
  }
}
