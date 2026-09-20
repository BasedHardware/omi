import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/env/env.dart';
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
  final bob = Person(id: 'person-bob', name: 'Bob', createdAt: DateTime(2026, 1, 1), updatedAt: DateTime(2026, 1, 1));

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().cachedPeople = [alice, bob];
  });

  test('accepted rename preserves verified sample metadata in provider and cache', () async {
    final person = Person(
        id: 'voice',
        name: 'Old',
        createdAt: DateTime(2026),
        updatedAt: DateTime(2026),
        speechSamples: ['sample.wav'],
        speechSampleTranscripts: ['Synthetic sample'],
        speechSamplesVersion: 3,
        colorIdx: 2);
    SharedPreferencesUtil().cachedPeople = [person];
    final provider = PeopleProvider(renamePerson: (id, name) async => true);
    await provider.updatePersonProvider(person, 'New');
    for (final saved in [provider.people.single, SharedPreferencesUtil().cachedPeople.single]) {
      expect(saved.name, 'New');
      expect(saved.speechSamples, ['sample.wav']);
      expect(saved.speechSampleTranscripts, ['Synthetic sample']);
      expect(saved.speechSamplesVersion, 3);
      expect(saved.colorIdx, 2);
    }
  });

  test('a rename the server did not accept keeps the old name', () async {
    final provider = PeopleProvider();

    await provider.updatePersonProvider(provider.people.first, 'Alicia');

    expect(provider.loading, isFalse);
    expect(provider.people.map((person) => person.name), ['Alice', 'Bob']);
    expect(SharedPreferencesUtil().cachedPeople.map((person) => person.name), ['Alice', 'Bob']);
  });

  test('a delete the server did not accept puts the person back', () async {
    final provider = PeopleProvider();

    await provider.deletePersonProvider(provider.people.firstWhere((person) => person.id == bob.id));

    expect(provider.people.map((person) => person.id), [alice.id, bob.id]);
    expect(SharedPreferencesUtil().cachedPeople.map((person) => person.id), [alice.id, bob.id]);
  });

  test('deleting one of several samples keeps readiness until refresh', () async {
    final person = Person(
      id: 'voice',
      name: 'Alice',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
      speechSamples: ['a.wav', 'b.wav'],
      speechSamplesVersion: 3,
      voiceReadiness: 'ready',
    );
    SharedPreferencesUtil().cachedPeople = [person];
    final provider = PeopleProvider(
      deleteSample: (id, idx) async => true,
      loadPeople: () async => [
        Person(
          id: 'voice',
          name: 'Alice',
          createdAt: DateTime(2026),
          updatedAt: DateTime(2026),
          speechSamples: ['b.wav'],
          speechSamplesVersion: 3,
          voiceReadiness: 'ready',
        ),
      ],
    );
    provider.people = [
      Person(
        id: person.id,
        name: person.name,
        createdAt: person.createdAt,
        updatedAt: person.updatedAt,
        speechSamples: ['a.wav', 'b.wav'],
        speechSamplesVersion: 3,
        voiceReadiness: 'ready',
      ),
    ];
    await provider.deletePersonSample(0, 0);
    expect(provider.people.single.voiceReadiness, 'ready');
    expect(provider.people.single.speechSamples, ['b.wav']);
  });

  test('deleting the last sample paints not_learned then refreshes', () async {
    final person = Person(
      id: 'voice',
      name: 'Alice',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
      speechSamples: ['a.wav'],
      speechSamplesVersion: 3,
      voiceReadiness: 'ready',
    );
    SharedPreferencesUtil().cachedPeople = [person];
    Person? optimistic;
    final provider = PeopleProvider(
      deleteSample: (id, idx) async => true,
      loadPeople: () async {
        optimistic = SharedPreferencesUtil().cachedPeople.single;
        return [
          Person(
            id: 'voice',
            name: 'Alice',
            createdAt: DateTime(2026),
            updatedAt: DateTime(2026),
            speechSamples: const [],
            speechSamplesVersion: 3,
            voiceReadiness: 'not_learned',
          ),
        ];
      },
    );
    provider.people = [
      Person(
        id: person.id,
        name: person.name,
        createdAt: person.createdAt,
        updatedAt: person.updatedAt,
        speechSamples: ['a.wav'],
        speechSamplesVersion: 3,
        voiceReadiness: 'ready',
      ),
    ];
    await provider.deletePersonSample(0, 0);
    expect(optimistic?.voiceReadiness, 'not_learned');
    expect(provider.people.single.voiceReadiness, 'not_learned');
    expect(provider.people.single.speechSamples, isEmpty);
  });
}
