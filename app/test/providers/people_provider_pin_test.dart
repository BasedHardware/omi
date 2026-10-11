import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/people_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().cachedPeople = [
      for (final id in ['a', 'b']) Person(id: id, name: id, createdAt: DateTime(2026), updatedAt: DateTime(2026)),
    ];
  });

  test('pin requests are serialized per person while different people remain independent', () async {
    final first = Completer<bool>();
    final second = Completer<bool>();
    final calls = <(String, bool)>[];
    final provider = PeopleProvider(setPinned: (id, value) {
      calls.add((id, value));
      if (id == 'b') return Future.value(true);
      return calls.where((c) => c.$1 == 'a').length == 1 ? first.future : second.future;
    });
    addTearDown(provider.dispose);
    final pin = provider.setPinned('a', true);
    final unpin = provider.setPinned('a', false);
    expect(calls, [('a', true)]);
    expect(await provider.setPinned('b', true), isTrue);
    first.complete(true);
    expect(await pin, isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(calls, [('a', true), ('b', true), ('a', false)]);
    second.complete(true);
    expect(await unpin, isTrue);
    expect(provider.people.first.pinned, isFalse);
    expect(SharedPreferencesUtil().cachedPeople.first.pinned, isFalse);
  });

  for (final throws in [false, true]) {
    test('an older pin failure (throws=$throws) cannot roll back a newer pin', () async {
      final first = Completer<bool>();
      var calls = 0;
      final provider = PeopleProvider(setPinned: (_, __) => ++calls == 1 ? first.future : Future.value(true));
      addTearDown(provider.dispose);
      final older = provider.setPinned('a', true);
      final newer = provider.setPinned('a', true);
      if (throws) {
        first.completeError(Exception('offline'));
      } else {
        first.complete(false);
      }
      expect(await older, isFalse);
      expect(await newer, isTrue);
      expect(calls, 2);
      expect(provider.people.first.pinned, isTrue);
    });
  }
}
