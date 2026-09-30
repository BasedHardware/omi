import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/people_provider.dart';

Person _person(String id) => Person(id: id, name: id, createdAt: DateTime(2026, 1, 1), updatedAt: DateTime(2026, 1, 1));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().cachedPeople = [_person('a'), _person('b'), _person('c')];
  });

  test('deleteSelected removes accepted deletes, keeps failed ones selected, and updates the cache', () async {
    final provider = PeopleProvider(deletePersonById: (id) async => id != 'b');
    provider.beginSelection('a');
    provider.toggleSelected('b');

    final deleted = await provider.deleteSelected();

    expect(deleted, 1);
    expect(provider.people.map((p) => p.id), ['b', 'c']);
    expect(SharedPreferencesUtil().cachedPeople.map((p) => p.id), ['b', 'c']);
    expect(provider.selectedIds, {'b'});
    expect(provider.selecting, isTrue);
  });

  test('selection ends once everything selected is deleted', () async {
    final provider = PeopleProvider(deletePersonById: (id) async => true);
    provider.beginSelection();
    provider.selectAll(['a', 'c']);

    await provider.deleteSelected();

    expect(provider.people.map((p) => p.id), ['b']);
    expect(provider.selecting, isFalse);
    expect(provider.selectedIds, isEmpty);
  });

  test('a request that throws counts as not deleted', () async {
    final provider = PeopleProvider(deletePersonById: (id) async => throw Exception('offline'));
    provider.beginSelection('a');

    expect(await provider.deleteSelected(), 0);
    expect(provider.people.length, 3);
  });
}
