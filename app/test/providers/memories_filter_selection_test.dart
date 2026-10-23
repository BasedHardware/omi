import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _memory(String id, MemoryCategory category) => Memory(
      id: id,
      uid: 'memories-filter-user',
      content: 'Memory $id',
      category: category,
      createdAt: DateTime(2026, 10, 20),
      updatedAt: DateTime(2026, 10, 20),
      visibility: MemoryVisibility.private,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memories-filter-user'});
    await SharedPreferencesUtil.init();
  });

  MemoriesProvider providerWith(List<Memory> rows) => MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
            GetMemoriesResult(rows, true),
      );

  test('a first visit loads the All view instead of ticking every category', () async {
    final provider = providerWith([]);
    addTearDown(provider.dispose);

    await provider.init();

    // The filter sheet renders All from an empty set. Seeding every category
    // left All unchecked and tapping a category removed it from the list.
    expect(provider.selectedCategories, isEmpty);
  });

  test('a saved selection naming every category loads as All', () async {
    SharedPreferences.setMockInitialValues({
      'uid': 'memories-filter-user',
      'memories_filter_categories': MemoryCategory.values.map((c) => c.name).toList(),
    });
    await SharedPreferencesUtil.init();
    final provider = providerWith([]);
    addTearDown(provider.dispose);

    await provider.init();

    expect(provider.selectedCategories, isEmpty);
  });

  test('a saved selection with an unknown name does not silently check System', () async {
    SharedPreferences.setMockInitialValues({
      'uid': 'memories-filter-user',
      'memories_filter_categories': ['retired_category'],
    });
    await SharedPreferencesUtil.init();
    final provider = providerWith([]);
    addTearDown(provider.dispose);

    await provider.init();

    expect(provider.selectedCategories, isEmpty);
  });

  test('tapping a category from All filters the list to that category', () async {
    final provider = providerWith([
      _memory('system-1', MemoryCategory.system),
      _memory('manual-1', MemoryCategory.manual),
    ]);
    addTearDown(provider.dispose);
    await provider.init();

    await provider.toggleCategoryFilter(MemoryCategory.manual);

    expect(provider.selectedCategories, {MemoryCategory.manual});
    expect(provider.filteredMemories.map((memory) => memory.id), ['manual-1']);
  });

  test('ticking every category returns to All and clears the saved filter', () async {
    final provider = providerWith([]);
    addTearDown(provider.dispose);
    await provider.init();

    for (final category in MemoryCategory.values) {
      await provider.toggleCategoryFilter(category);
    }

    expect(provider.selectedCategories, isEmpty);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('memories_filter_categories'), isNull);
  });
}
