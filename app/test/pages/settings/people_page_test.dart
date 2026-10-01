import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/people_wire.g.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

final _now = DateTime.now();

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Person _person(
  String id,
  String name, {
  int? conversations,
  DateTime? lastHeard,
  String voice = 'not_learned',
  String confidence = 'unverified',
  Map<String, int> reasons = const {},
  bool pinned = false,
  int? labelsToConfirm,
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
      confidence: confidence,
      confidenceReasons: [
        for (final entry in reasons.entries) GeneratedPersonConfidenceReason(code: entry.key, count: entry.value),
      ],
      pinned: pinned,
      labelsToConfirm: labelsToConfirm,
    );

final _people = [
  _person('p-maya', 'Maya Chen',
      conversations: 24,
      lastHeard: _now,
      voice: 'ready',
      confidence: 'confirmed',
      reasons: {'manual_labels': 6},
      pinned: true),
  _person('p-sam', 'Sam Okafor',
      conversations: 5,
      lastHeard: _now.subtract(const Duration(days: 2)),
      voice: 'ready',
      confidence: 'likely',
      reasons: {'card_picks': 2, 'auto_corrected': 1, 'auto_unconfirmed': 3},
      labelsToConfirm: 1),
  _person('p-because', 'Because',
      conversations: 3, lastHeard: _now.subtract(const Duration(days: 1)), reasons: {'auto_unconfirmed': 3}),
  _person('p-cs', 'Cs',
      conversations: 2, lastHeard: _now.subtract(const Duration(days: 9)), reasons: {'never_confirmed': 1}),
  _person('p-ines', 'Inês Moreira', conversations: 0, reasons: {'never_confirmed': 1}),
];

class _Pins {
  final calls = <(String, bool)>[];
  bool ok = true;

  Future<bool> call(String id, bool pinned) async {
    calls.add((id, pinned));
    return ok;
  }
}

Future<PeopleProvider> _pump(
  WidgetTester tester, {
  List<Person>? people,
  Future<bool> Function(String)? deletePersonById,
  _Pins? pins,
}) async {
  // Tall enough that every group is built and hittable without scrolling.
  tester.view.physicalSize = const Size(900, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final provider = PeopleProvider(
    loadPeople: () async => [...(people ?? _people)],
    deletePersonById: deletePersonById ?? (_) async => true,
    setPinned: (pins ?? _Pins()).call,
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

Future<void> _confirmDialog(WidgetTester tester, String label) async {
  await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.text(label)));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('pinned first, then recent by last heard, then not heard yet; rows say why Omi is sure', (tester) async {
    await _pump(tester);

    expect(find.text('1 pinned'), findsOneWidget);
    final maya = tester.getTopLeft(find.text('Maya Chen')).dy;
    final because = tester.getTopLeft(find.text('Because')).dy;
    final sam = tester.getTopLeft(find.text('Sam Okafor')).dy;
    final cs = tester.getTopLeft(find.text('Cs')).dy;
    final notHeard = tester.getTopLeft(find.text('Not Heard Yet').last).dy;
    final ines = tester.getTopLeft(find.text('Inês Moreira')).dy;
    expect(maya < because && because < sam && sam < cs && cs < notHeard && notHeard < ines, isTrue);

    expect(find.text('You labeled 6 times · voice ready'), findsOneWidget);
    expect(find.text('Picked in 2 suggestions · voice ready'), findsOneWidget);
    expect(find.text('Only auto-matched, never confirmed · needs voice'), findsOneWidget);
    expect(find.text('Never confirmed · not heard yet'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp(r'^Maya Chen, Pinned, Confidence: Confirmed')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp(r'^Because, Confidence: Unverified')), findsOneWidget);
  });

  testWidgets('filters narrow the list and search matches names', (tester) async {
    await _pump(tester);

    await tester.tap(find.byKey(const Key('people_filter_lowConfidence')));
    await tester.pumpAndSettle();
    expect(find.text('Maya Chen'), findsNothing);
    expect(find.text('Sam Okafor'), findsNothing);
    expect(find.text('Because'), findsOneWidget);
    expect(find.text('Inês Moreira'), findsOneWidget);

    await tester.tap(find.byKey(const Key('people_filter_pinned')));
    await tester.pumpAndSettle();
    expect(find.text('Maya Chen'), findsOneWidget);
    expect(find.text('Because'), findsNothing);

    await tester.tap(find.byKey(const Key('people_filter_all')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'sam');
    await tester.pumpAndSettle();
    expect(find.text('Sam Okafor'), findsOneWidget);
    expect(find.text('Because'), findsNothing);

    await tester.enterText(find.byType(TextField), 'zed');
    await tester.pumpAndSettle();
    expect(find.text('No Matching People'), findsOneWidget);
    await tester.tap(find.text('Clear Search'));
    await tester.pumpAndSettle();
    expect(find.text('Because'), findsOneWidget);
  });

  testWidgets('Select All skips pinned people and the delete confirms', (tester) async {
    final deleted = <String>[];
    final provider = await _pump(tester, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });

    await tester.tap(find.byKey(const Key('people_select')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Select People'));
    await tester.pumpAndSettle();
    expect(provider.selecting, isTrue);
    expect(find.text('Select All skips pinned people. Delete them one at a time from their page.'), findsOneWidget);

    await tester.tap(find.byKey(const Key('people_select_all')));
    await tester.pumpAndSettle();
    expect(find.text('4 selected'), findsOneWidget);
    // A pinned row cannot be ticked.
    await tester.tap(find.text('Maya Chen'));
    await tester.pumpAndSettle();
    expect(provider.selectedIds.contains('p-maya'), isFalse);

    await tester.tap(find.byKey(const Key('people_delete_selected')));
    await tester.pumpAndSettle();
    expect(find.text('Delete 4 People?'), findsOneWidget);
    await _confirmDialog(tester, 'Delete');

    expect(deleted.toSet(), {'p-sam', 'p-because', 'p-cs', 'p-ines'});
    expect(provider.people.map((p) => p.id), ['p-maya']);
  });

  testWidgets('Clean Up preselects unsure unpinned people, lets one be kept, and confirms', (tester) async {
    final deleted = <String>[];
    final provider = await _pump(tester, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });

    expect(find.text('3 people Omi is unsure about'), findsOneWidget);
    await tester.tap(find.byKey(const Key('people_clean_up_review')));
    await tester.pumpAndSettle();
    expect(find.text('Clean Up'), findsOneWidget);
    expect(find.text('Maya Chen'), findsNothing, reason: 'pinned people are never included');
    expect(find.text('Sam Okafor'), findsNothing, reason: 'only Unverified people are offered');
    expect(find.text('Delete 3 People'), findsOneWidget);

    await tester.tap(find.byKey(const Key('people_clean_up_row_p-ines')));
    await tester.pumpAndSettle();
    expect(find.text('Delete 2 People'), findsOneWidget);

    await tester.tap(find.byKey(const Key('people_clean_up_delete')));
    await tester.pumpAndSettle();
    expect(find.text('Delete 2 People?'), findsOneWidget);
    await _confirmDialog(tester, 'Delete');

    expect(deleted.toSet(), {'p-because', 'p-cs'});
    expect(provider.people.map((p) => p.id), containsAll(['p-maya', 'p-sam', 'p-ines']));
    // Back on the list, below the banner threshold.
    expect(find.text('People'), findsOneWidget);
    expect(find.byKey(const Key('people_clean_up_banner')), findsNothing);
  });

  testWidgets('cancelling the Clean Up confirmation deletes nothing', (tester) async {
    final deleted = <String>[];
    await _pump(tester, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });
    await tester.tap(find.byKey(const Key('people_clean_up_review')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('people_clean_up_delete')));
    await tester.pumpAndSettle();
    await _confirmDialog(tester, 'Cancel');
    expect(deleted, isEmpty);
    expect(find.text('Delete 3 People'), findsOneWidget);
  });

  testWidgets('long-press Pin moves a person into Pinned; a refused pin rolls back', (tester) async {
    final pins = _Pins();
    final provider = await _pump(tester, pins: pins);

    await tester.longPress(find.text('Sam Okafor'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pin'));
    await tester.pumpAndSettle();
    expect(pins.calls, [('p-sam', true)]);
    expect(find.text('2 pinned'), findsOneWidget);
    expect(find.text('Sam Okafor pinned'), findsOneWidget);

    pins.ok = false;
    await tester.longPress(find.text('Because'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pin'));
    await tester.pumpAndSettle();
    expect(provider.people.firstWhere((p) => p.id == 'p-because').pinned, isFalse);
  });

  testWidgets('a leading swipe pins the row instead of removing it', (tester) async {
    final pins = _Pins();
    await _pump(tester, pins: pins);

    await tester.drag(find.text('Cs'), const Offset(500, 0));
    await tester.pumpAndSettle();
    expect(pins.calls, [('p-cs', true)]);
    expect(find.text('Cs'), findsOneWidget);
    expect(find.text('2 pinned'), findsOneWidget);
  });

  testWidgets('the Why sheet lists evidence with what each piece is worth', (tester) async {
    await _pump(tester);

    await tester.longPress(find.text('Sam Okafor'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Why Likely?'));
    await tester.pumpAndSettle();

    expect(find.text('Confidence'), findsOneWidget);
    expect(find.text("Omi usually recognizes Sam Okafor's voice, but you've only confirmed it a few times."),
        findsOneWidget);
    expect(find.text('Picked in 2 suggestions'), findsWidgets);
    expect(find.text('Counts'), findsWidgets);
    expect(find.text('1 match moved to someone else'), findsOneWidget);
    expect(find.text('Counts against'), findsOneWidget);
    expect(find.text('3 automatic matches nobody confirmed'), findsOneWidget);
    expect(find.text('Barely counts'), findsOneWidget);
    expect(find.text('Label them in 1 more conversation.'), findsOneWidget);
  });

  testWidgets('Person page: Pin switch with the honest line, and a pinned delete names the person', (tester) async {
    final pins = _Pins();
    final deleted = <String>[];
    await _pump(tester, pins: pins, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });
    await tester.tap(find.text('Maya Chen'));
    await tester.pumpAndSettle();

    expect(find.text('Pin Maya Chen'), findsOneWidget);
    expect(find.text('Omi will ask you to confirm close matches instead of guessing.'), findsOneWidget);
    await tester.tap(find.byKey(const Key('person_confidence_pill')));
    await tester.pumpAndSettle();
    expect(find.text('Maya Chen is Confirmed. Omi keeps learning from each label.'), findsOneWidget);
    Navigator.of(tester.element(find.text('Confidence'))).pop();
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Delete person'));
    await tester.pumpAndSettle();
    expect(find.text('Delete Maya Chen?'), findsOneWidget);
    expect(find.textContaining('Maya Chen is pinned.'), findsOneWidget);
    await _confirmDialog(tester, 'Delete Maya Chen');
    expect(deleted, ['p-maya']);
  });

  testWidgets('a failed first load with nothing cached offers Try Again', (tester) async {
    final provider = PeopleProvider(loadPeople: () async => null);
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

    expect(find.text('Try Again'), findsOneWidget);
  });

  testWidgets('legacy people are unknown and never offered by Clean Up', (tester) async {
    final legacy = Person.fromJson({
      'id': 'legacy',
      'name': 'Legacy',
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': '2026-01-01T00:00:00Z',
    });
    final provider = await _pump(tester, people: [legacy, ..._people]);
    expect(legacy.confidence, 'unknown');
    expect(provider.cleanUpCandidates.map((p) => p.id), isNot(contains('legacy')));
    expect(find.bySemanticsLabel(RegExp(r'^Legacy, Confidence: Unknown')), findsOneWidget);
  });

  testWidgets('bulk deletion protects current pins even with stale selected ids', (tester) async {
    final deleted = <String>[];
    final provider = await _pump(tester, deletePersonById: (id) async {
      deleted.add(id);
      return true;
    });
    expect(await provider.deletePeople(['p-maya', 'p-cs']), 1);
    expect(deleted, ['p-cs']);
    expect(provider.people.map((p) => p.id), contains('p-maya'));
  });

  testWidgets('failed optimistic single delete restores the person and cache', (tester) async {
    final result = Completer<bool>();
    final provider = await _pump(tester, deletePersonById: (_) => result.future);
    final person = provider.people.first;
    final deleting = provider.deletePersonProvider(person);
    expect(provider.people.map((p) => p.id), isNot(contains(person.id)));
    result.complete(false);
    await deleting;
    expect(provider.people.map((p) => p.id), contains(person.id));
    expect(SharedPreferencesUtil().cachedPeople.map((p) => p.id), contains(person.id));
  });

  testWidgets('Clean Up reacts when a reviewed person becomes pinned', (tester) async {
    final provider = await _pump(tester);
    await tester.tap(find.byKey(const Key('people_clean_up_review')));
    await tester.pumpAndSettle();
    await provider.setPinned('p-cs', true);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('people_clean_up_row_p-cs')), findsNothing);
    expect(find.text('Delete 2 People'), findsOneWidget);
  });
}
