import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

class _People extends PeopleProvider {
  _People(List<Person> seeded) : super(loadPeople: () async => seeded);

  final List<(int, int)> played = [];
  final List<(int, int)> deletedSamples = [];

  @override
  void initialize() {
    loading = true;
    setPeople();
  }

  @override
  Future<void> playPause(int personIndex, int fileIndex, String path) async => played.add((personIndex, fileIndex));

  @override
  Future<void> deletePersonSample(int personIdx, int sampleIdx) async => deletedSamples.add((personIdx, sampleIdx));
}

/// Tapping a voice sample plays it; deleting is the labelled trailing control behind a confirm
/// (hub #6 — a tap used to open the delete dialog).
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('tapping a sample plays it and delete asks first', (tester) async {
    final people = _People([
      Person(
        id: 'p1',
        name: 'Alex',
        createdAt: DateTime.utc(2026, 9, 1),
        updatedAt: DateTime.utc(2026, 9, 1),
        speechSamples: const ['https://example.invalid/sample-0.wav'],
        speechSampleTranscripts: const ['Hello there'],
      ),
    ]);
    addTearDown(people.dispose);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<PeopleProvider>.value(value: people),
          ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider<SpeakerTagPromptsProvider>(
            create: (_) => SpeakerTagPromptsProvider(
              fetchSettings: () async =>
                  const ApiFailure<GeneratedVoiceProfileSettings>(ApiProblem(ApiProblemKind.transport)),
            ),
          ),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: [Locale('en')],
          home: UserPeoplePage(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Sample 1'), findsOneWidget);
    expect(find.text('Tap to delete'), findsNothing);

    await tester.tap(find.text('Sample 1'));
    await tester.pumpAndSettle();
    expect(people.played, [(0, 0)]);
    expect(find.text('Delete Sample?'), findsNothing, reason: 'a tap plays, it never deletes');

    await tester.tap(find.byTooltip('Delete sample'));
    await tester.pumpAndSettle();
    expect(find.text('Delete Sample?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(people.deletedSamples, isEmpty);

    await tester.tap(find.byTooltip('Delete sample'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(people.deletedSamples, [(0, 0)]);
  });
}
