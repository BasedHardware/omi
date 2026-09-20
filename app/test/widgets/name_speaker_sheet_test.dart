import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/providers/people_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('name-only suggestion survives initialization; failed save stays open and bulk includes corrections',
      (tester) async {
    final segments = [
      TranscriptSegment(
          id: 'first',
          text: 'First synthetic speech',
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: 0,
          end: 2,
          translations: []),
      TranscriptSegment(
          id: 'wrong',
          text: 'Wrongly assigned speech',
          speaker: 'SPEAKER_00',
          isUser: true,
          personId: null,
          start: 2,
          end: 4,
          translations: []),
    ];
    final calls = <({String name, List<String> ids, bool whole})>[];
    await tester.pumpWidget(ChangeNotifierProvider(
        create: (_) => PeopleProvider(),
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
              body: NameSpeakerBottomSheet(
                  speakerId: 0,
                  segmentId: 'first',
                  segments: segments,
                  suggestion:
                      SpeakerLabelSuggestionEvent(speakerId: 0, personId: '', personName: 'Alex', segmentId: 'first'),
                  onSpeakerAssigned: (speaker, person, name, ids, whole) async {
                    calls.add((name: name, ids: ids, whole: whole));
                    return false;
                  })),
        )));
    await tester.pumpAndSettle();
    expect(find.text('Alex'), findsOneWidget);
    final save = find.byType(ElevatedButton);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(calls.single.name, 'Alex');
    expect(calls.single.ids, ['first']);
    expect(calls.single.whole, isFalse);
    expect(find.byType(NameSpeakerBottomSheet), findsOneWidget);
    final bulk = find.byType(CheckboxListTile).first;
    await tester.ensureVisible(bulk);
    await tester.tap(bulk);
    await tester.pumpAndSettle();
    expect(find.textContaining('Wrongly assigned speech'), findsOneWidget);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(calls.last.ids, ['first', 'wrong']);
    expect(calls.last.whole, isTrue);
  });
}
