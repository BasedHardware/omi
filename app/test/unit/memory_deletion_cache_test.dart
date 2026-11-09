import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';

class _WriteFault extends InMemorySharedPreferencesStore {
  _WriteFault(super.data, {required this.rejectMarker, required this.throwCache}) : super.withData();
  final bool rejectMarker;
  final bool throwCache;

  @override
  Future<bool> setValue(String type, String key, Object value) async {
    if (rejectMarker && key.contains('confirmedMemoryDeletes')) throw StateError('Marker write failed');
    if (!rejectMarker && (key.contains('cachedMemories:') || key.contains('pendingMemories:'))) {
      if (throwCache) throw StateError('Cache write failed');
      return false;
    }
    return super.setValue(type, key, value);
  }
}

Memory _row(String id, String owner) => Memory(
      id: id,
      uid: owner,
      content: 'Synthetic memory',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      visibility: MemoryVisibility.private,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final rejectMarker in [false, true]) {
    for (final throwCache in [false, true]) {
      test('confirmed deletion survives restart (marker refused: $rejectMarker, cache throws: $throwCache)', () async {
        final encoded = ['deleted', 'keep'].map((id) => jsonEncode(_row(id, 'owner-a').toJson())).toList();
        final store = _WriteFault({
          'flutter.uid': 'owner-a',
          'flutter.cachedMemories:owner-a': encoded,
          'flutter.pendingMemories:owner-a': encoded,
          'flutter.cachedMemories:owner-b': [jsonEncode(_row('deleted', 'owner-b').toJson())],
        }, rejectMarker: rejectMarker, throwCache: throwCache);
        SharedPreferences.setMockInitialValues({});
        SharedPreferencesStorePlatform.instance = store;
        await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
        final prefs = SharedPreferencesUtil();
        await prefs.recordConfirmedMemoryDelete('deleted', ownerUid: 'owner-a');

        final disk = await store.getAll();
        SharedPreferences.setMockInitialValues(disk);
        await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
        expect(prefs.cachedMemories.map((row) => row.id), ['keep']);
        expect(prefs.pendingMemories.map((row) => row.id), ['keep']);
        if (!rejectMarker) {
          prefs.cachedMemories = [_row('deleted', 'owner-a'), _row('keep', 'owner-a')];
          expect(prefs.cachedMemories.map((row) => row.id), ['keep']);
        }
        prefs.uid = 'owner-b';
        expect(prefs.cachedMemories.map((row) => row.id), ['deleted']);
      });
    }
  }
}
