import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/people_provider.dart';

final _heardAt = DateTime(2026, 2, 1, 10);

Person _person(
  String id,
  String name, {
  int? conversationCount,
  DateTime? lastHeardAt,
  double? talkSeconds,
  int? autoConversationCount,
  bool pinned = false,
  String confidence = 'unknown',
  String voiceReadiness = 'not_learned',
  List<String>? speechSamples,
}) =>
    Person(
      id: id,
      name: name,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      conversationCount: conversationCount,
      lastHeardAt: lastHeardAt,
      talkSeconds: talkSeconds,
      autoConversationCount: autoConversationCount,
      pinned: pinned,
      confidence: confidence,
      voiceReadiness: voiceReadiness,
      speechSamples: speechSamples,
    );

void _expectStats(Person person, int? count, DateTime? heard, double? seconds, int? autoCount) {
  expect(person.conversationCount, count);
  expect(person.lastHeardAt, heard);
  expect(person.talkSeconds, seconds);
  expect(person.autoConversationCount, autoCount);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  PeopleProvider provider(
    PeopleListResponse? Function() loadPeople, {
    void Function(ApiFallbackEvent)? fallback,
  }) {
    final created = PeopleProvider(loadPeople: () async => loadPeople(), fallback: fallback);
    addTearDown(created.dispose);
    return created;
  }

  test('a truncated load keeps the cached aggregate stats and applies the fresh row data', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice Old',
          conversationCount: 10,
          lastHeardAt: _heardAt,
          talkSeconds: 600,
          autoConversationCount: 4,
          confidence: 'unverified',
          speechSamples: ['old.wav']),
    ];
    final events = <ApiFallbackEvent>[];
    final people = provider(
        () => PeopleListResponse(
              people: [
                _person('p-a', 'Alice',
                    conversationCount: 2,
                    talkSeconds: 30,
                    pinned: true,
                    confidence: 'confirmed',
                    voiceReadiness: 'ready',
                    speechSamples: ['new.wav']),
              ],
              statsTruncated: true,
            ),
        fallback: events.add);

    await people.setPeople();

    final shown = people.people.single;
    _expectStats(shown, 10, _heardAt, 600, 4);
    expect(shown.name, 'Alice');
    expect(shown.pinned, isTrue);
    expect(shown.confidence, 'confirmed');
    expect(shown.voiceReadiness, 'ready');
    expect(shown.speechSamples, ['new.wav']);

    final persisted = SharedPreferencesUtil().cachedPeople.single;
    _expectStats(persisted, 10, _heardAt, 600, 4);
    expect(persisted.name, 'Alice');

    expect(people.statsTruncated, isTrue);
    expect(SharedPreferencesUtil().cachedPeopleStatsTruncated, isTrue);
    expect(events, hasLength(1));
    expect(events.single.reason, ApiFallbackReason.staleData);
    expect(events.single.outcome, ApiFallbackOutcome.degraded);
  });

  test('a complete load replaces the stats and clears the partial marker', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt, talkSeconds: 600, autoConversationCount: 4),
    ];
    SharedPreferencesUtil().cachedPeopleStatsTruncated = true;
    final events = <ApiFallbackEvent>[];
    var truncated = true;
    final people = provider(() {
      return truncated
          ? PeopleListResponse(people: [_person('p-a', 'Alice', conversationCount: 1)], statsTruncated: true)
          : PeopleListResponse(people: [_person('p-a', 'Alice', conversationCount: 3, talkSeconds: 90)]);
    }, fallback: events.add);

    await people.setPeople();
    expect(people.statsTruncated, isTrue);
    expect(events, hasLength(1));

    truncated = false;
    await people.setPeople();

    final persisted = SharedPreferencesUtil().cachedPeople.single;
    _expectStats(people.people.single, 3, null, 90, null);
    _expectStats(persisted, 3, null, 90, null);
    expect(people.statsTruncated, isFalse);
    expect(SharedPreferencesUtil().cachedPeopleStatsTruncated, isFalse);
    expect(events, hasLength(1));
  });

  test('a truncated load without cached stats keeps the incoming partial fields', () async {
    final people = provider(() => PeopleListResponse(
          people: [_person('p-new', 'New', conversationCount: 2, lastHeardAt: _heardAt)],
          statsTruncated: true,
        ));

    await people.setPeople();

    _expectStats(people.people.single, 2, _heardAt, null, null);
    _expectStats(SharedPreferencesUtil().cachedPeople.single, 2, _heardAt, null, null);
    expect(people.statsTruncated, isTrue);
  });

  test('a cached zero count and missing recency survive a truncated load', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 0, talkSeconds: 0, autoConversationCount: 0),
    ];
    final people = provider(() => PeopleListResponse(
          people: [
            _person('p-a', 'Alice',
                conversationCount: 5, lastHeardAt: _heardAt, talkSeconds: 90, autoConversationCount: 2),
          ],
          statsTruncated: true,
        ));

    await people.setPeople();

    _expectStats(people.people.single, 0, null, 0, 0);
    _expectStats(SharedPreferencesUtil().cachedPeople.single, 0, null, 0, 0);
  });

  test('a cached person with no known stats takes the incoming partial fields', () async {
    SharedPreferencesUtil().cachedPeople = [_person('p-a', 'Alice')];
    final people = provider(() => PeopleListResponse(
          people: [_person('p-a', 'Alice', conversationCount: 4, lastHeardAt: _heardAt, talkSeconds: 120)],
          statsTruncated: true,
        ));

    await people.setPeople();

    _expectStats(people.people.single, 4, _heardAt, 120, null);
  });

  test('an optimistic person stays on screen but out of the persisted list', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt),
    ];
    final people = provider(() => PeopleListResponse(
          people: [_person('p-a', 'Alice', conversationCount: 2)],
          statsTruncated: true,
        ));
    people.addOptimisticPerson(_person('optimistic-person:temp', 'Draft'));

    await people.setPeople();

    expect(people.people.map((p) => p.id), ['p-a', 'optimistic-person:temp']);
    expect(SharedPreferencesUtil().cachedPeople.map((p) => p.id), ['p-a']);
    _expectStats(SharedPreferencesUtil().cachedPeople.single, 10, _heardAt, null, null);
  });

  test('cached people the server no longer returns are not resurrected', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt),
      _person('p-b', 'Bob', conversationCount: 8),
    ];
    final people = provider(() => PeopleListResponse(
          people: [_person('p-a', 'Alice', conversationCount: 1)],
          statsTruncated: true,
        ));

    await people.setPeople();

    expect(people.people.map((p) => p.id), ['p-a']);
    expect(SharedPreferencesUtil().cachedPeople.map((p) => p.id), ['p-a']);
  });

  test('a second truncated load keeps the best-known stats', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt, talkSeconds: 600, autoConversationCount: 4),
    ];
    var incomingCount = 2;
    final people = provider(() => PeopleListResponse(
          people: [_person('p-a', 'Alice', conversationCount: incomingCount)],
          statsTruncated: true,
        ));

    await people.setPeople();
    incomingCount = 7;
    await people.setPeople();

    _expectStats(people.people.single, 10, _heardAt, 600, 4);
    _expectStats(SharedPreferencesUtil().cachedPeople.single, 10, _heardAt, 600, 4);
  });

  test('the partial marker survives a provider recreation and a failed refresh', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt),
    ];
    var fail = false;
    PeopleProvider make() {
      final created = PeopleProvider(
        loadPeople: () async => fail
            ? null
            : PeopleListResponse(people: [_person('p-a', 'Alice', conversationCount: 1)], statsTruncated: true),
      );
      addTearDown(created.dispose);
      return created;
    }

    final first = make();
    await first.setPeople();
    expect(SharedPreferencesUtil().cachedPeopleStatsTruncated, isTrue);

    final second = make();
    expect(second.statsTruncated, isTrue);

    fail = true;
    await second.setPeople();
    expect(second.loadFailed, isTrue);
    expect(second.people.map((p) => p.id), ['p-a']);
    expect(second.statsTruncated, isTrue);
    expect(SharedPreferencesUtil().cachedPeopleStatsTruncated, isTrue);
    _expectStats(SharedPreferencesUtil().cachedPeople.single, 10, _heardAt, null, null);
  });

  test('clearUserData resets the in-memory marker and clearUserDisplayCache clears the persisted one', () async {
    SharedPreferencesUtil().cachedPeople = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt),
    ];
    final people = provider(() => PeopleListResponse(
          people: [_person('p-a', 'Alice', conversationCount: 1)],
          statsTruncated: true,
        ));
    await people.setPeople();
    expect(people.statsTruncated, isTrue);

    people.clearUserData();
    expect(people.statsTruncated, isFalse);

    SharedPreferencesUtil().clearUserDisplayCache();
    expect(SharedPreferencesUtil().cachedPeopleStatsTruncated, isFalse);
    expect(SharedPreferencesUtil().cachedPeople, isEmpty);
  });

  test('each truncated fetch emits exactly one degraded fallback event', () async {
    final events = <ApiFallbackEvent>[];
    var mode = 0;
    final people = provider(() {
      if (mode == 0) {
        return PeopleListResponse(people: [_person('p-a', 'Alice')], statsTruncated: true);
      }
      if (mode == 1) {
        return PeopleListResponse(people: [_person('p-a', 'Alice')]);
      }
      return null;
    }, fallback: events.add);

    await people.setPeople();
    await people.setPeople();
    expect(events, hasLength(2));
    for (final event in events) {
      expect(event.reason, ApiFallbackReason.staleData);
      expect(event.outcome, ApiFallbackOutcome.degraded);
    }

    mode = 1;
    await people.setPeople();
    mode = 2;
    await people.setPeople();
    expect(events, hasLength(2));
  });

  test('preserveCachedPeopleStats keeps cached stats for a stats-less home fetch', () {
    final cached = [
      _person('p-a', 'Alice', conversationCount: 10, lastHeardAt: _heardAt, talkSeconds: 600, autoConversationCount: 4),
      _person('p-b', 'Bob', conversationCount: 8),
    ];
    final incoming = [
      _person('p-a', 'Alice Renamed', pinned: true, confidence: 'confirmed', voiceReadiness: 'ready'),
    ];

    final merged = preserveCachedPeopleStats(incoming, cached);

    expect(merged.map((p) => p.id), ['p-a']);
    final alice = merged.single;
    _expectStats(alice, 10, _heardAt, 600, 4);
    expect(alice.name, 'Alice Renamed');
    expect(alice.pinned, isTrue);
    expect(alice.confidence, 'confirmed');
    expect(alice.voiceReadiness, 'ready');
  });
}
