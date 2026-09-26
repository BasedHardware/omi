import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/people_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final alice = Person(
    id: 'person-alice',
    name: 'Alice',
    createdAt: DateTime(2026, 1, 1),
    updatedAt: DateTime(2026, 1, 1),
  );

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().cachedPeople = [alice];
  });

  test('a failed people fetch keeps the cached people', () async {
    final provider = PeopleProvider();

    await provider.setPeople();

    expect(provider.loading, isFalse);
    expect(provider.people.map((person) => person.id), [alice.id]);
    expect(SharedPreferencesUtil().cachedPeople.map((person) => person.id), [alice.id]);
  });

  test('a failed people refresh on the home screen keeps the cached people', () async {
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    await provider.setUserPeople();

    expect(SharedPreferencesUtil().cachedPeople.map((person) => person.id), [alice.id]);
  });
}
