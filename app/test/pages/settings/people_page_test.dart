import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

final _now = DateTime.now();

Person _person(
  String id,
  String name, {
  int? conversations,
  DateTime? lastHeard,
  String voice = 'not_learned',
}) =>
    Person(
      id: id,
      name: name,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      voiceReadiness: voice,
      conversationCount: conversations,
      lastHeardAt: lastHeard,
      talkSeconds: conversations == null ? null : conversations * 60.0,
    );

final _people = [
  _person('p-ana', 'Ana Silva', conversations: 12, lastHeard: _now.subtract(const Duration(days: 1)), voice: 'ready'),
  _person('p-ben', 'Ben Okafor', conversations: 3, lastHeard: _now),
  _person('p-cy', 'Cy', conversations: 0),
];

Future<PeopleProvider> _pump(
  WidgetTester tester, {
  List<Person>? people,
  Future<bool> Function(String)? deletePersonById,
}) async {
  final provider = PeopleProvider(
    loadPeople: () async => people ?? _people,
    deletePersonById: deletePersonById ?? (_) async => true,
  );
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<PeopleProvider>.value(value: provider),
      ChangeNotifierProvider<SpeakerTagPromptsProvider>(
        create: (_) => SpeakerTagPromptsProvider(
          fetchSettings: () => Completer<ApiResult<GeneratedVoiceProfileSettings>>().future,
        ),
      ),
    ],
    child: const MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: UserPeoplePage(),
    ),
  ));
  await tester.pumpAndSettle();
  return provider;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('groups heard people (newest first) above people not heard yet, with stats', (tester) async {
    await _pump(tester);

    expect(find.text('Recent'), findsOneWidget);
    expect(find.text('3 conversations · Today'), findsOneWidget);
    expect(find.text('12 conversations · Yesterday'), findsOneWidget);
    // Row order: Ben (now), Ana (yesterday), then Cy under Not Heard Yet.
    final ben = tester.getTopLeft(find.text('Ben Okafor')).dy;
    final ana = tester.getTopLeft(find.text('Ana Silva')).dy;
    final notHeardHeader = tester.getTopLeft(find.text('Not Heard Yet').last).dy;
    final cy = tester.getTopLeft(find.text('Cy')).dy;
    expect(ben < ana && ana < notHeardHeader && notHeardHeader < cy, isTrue);
    // A person with no conversations says what Omi knows of their voice instead.
    expect(find.text('Voice not learned'), findsOneWidget);
    // Initials on the avatar.
    expect(find.text('AS'), findsOneWidget);
  });

  testWidgets('filters narrow the list and search matches names', (tester) async {
    await _pump(tester);

    // Needs Voice: Ben and Cy have no learned voice.
    await tester.tap(find.byKey(const Key('people_filter_needsVoice')));
    await tester.pumpAndSettle();
    expect(find.text('Ana Silva'), findsNothing);
    expect(find.text('Ben Okafor'), findsOneWidget);
    expect(find.text('Cy'), findsOneWidget);

    await tester.tap(find.byKey(const Key('people_filter_all')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'ana');
    await tester.pumpAndSettle();
    expect(find.text('Ana Silva'), findsOneWidget);
    expect(find.text('Ben Okafor'), findsNothing);

    await tester.enterText(find.byType(TextField), 'zed');
    await tester.pumpAndSettle();
    expect(find.text('No Matching People'), findsOneWidget);
    await tester.tap(find.text('Clear Search'));
    await tester.pumpAndSettle();
    expect(find.text('Ben Okafor'), findsOneWidget);
  });

  testWidgets('select mode: select all, confirm, and delete', (tester) async {
    final deleted = <String>[];
    final provider = await _pump(tester, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });

    await tester.tap(find.byKey(const Key('people_select')));
    await tester.pumpAndSettle();
    expect(provider.selecting, isTrue);
    expect(find.text('0 selected'), findsOneWidget);

    await tester.tap(find.byKey(const Key('people_select_all')));
    await tester.pumpAndSettle();
    expect(find.text('3 selected'), findsOneWidget);
    expect(find.text('Deselect All'), findsOneWidget);

    // One row toggles off, then back on.
    await tester.tap(find.text('Cy'));
    await tester.pumpAndSettle();
    expect(find.text('2 selected'), findsOneWidget);
    await tester.tap(find.text('Cy'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('people_delete_selected')));
    await tester.pumpAndSettle();
    expect(find.text('Delete 3 People?'), findsOneWidget);
    await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text('Delete')));
    await tester.pumpAndSettle();

    expect(deleted.toSet(), {'p-ana', 'p-ben', 'p-cy'});
    expect(provider.selecting, isFalse);
    expect(find.text('No People Yet'), findsOneWidget);
  });

  testWidgets('cancelling the confirmation deletes nothing', (tester) async {
    final deleted = <String>[];
    await _pump(tester, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });

    await tester.tap(find.byKey(const Key('people_select')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ana Silva'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('people_delete_selected')));
    await tester.pumpAndSettle();
    await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text('Cancel')));
    await tester.pumpAndSettle();

    expect(deleted, isEmpty);
    expect(find.text('1 selected'), findsOneWidget);
  });

  testWidgets('a failed first load with nothing cached offers Try Again', (tester) async {
    final provider = PeopleProvider(loadPeople: () async => null);
    await tester.pumpWidget(ChangeNotifierProvider<PeopleProvider>.value(
      value: provider,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: UserPeoplePage(),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Try Again'), findsOneWidget);
  });
}
