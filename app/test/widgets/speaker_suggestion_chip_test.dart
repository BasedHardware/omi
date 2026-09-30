import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/widgets/speaker_suggestion_chip.dart';

void main() {
  final maya = Person(
    id: 'p-maya',
    name: 'Maya Chen',
    createdAt: DateTime(2026, 1, 1),
    updatedAt: DateTime(2026, 1, 1),
    pinned: true,
  );

  Future<(List<String>, List<String>)> pump(WidgetTester tester) async {
    final yes = <String>[];
    final other = <String>[];
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: SpeakerSuggestionChip(
          person: maya,
          onYes: () => yes.add('yes'),
          onSomeoneElse: () => other.add('other'),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    return (yes, other);
  }

  testWidgets('collapsed it asks with a chip; expanded it offers Yes and Someone Else…', (tester) async {
    final (yes, other) = await pump(tester);
    expect(find.text('Maya Chen?'), findsOneWidget);
    expect(find.byKey(const Key('speaker_suggestion_panel')), findsNothing);
    expect(tester.getSize(find.byKey(const Key('speaker_suggestion_chip'))).height, greaterThanOrEqualTo(44));

    await tester.tap(find.byKey(const Key('speaker_suggestion_chip')));
    await tester.pumpAndSettle();
    expect(find.text('Is this Maya Chen?'), findsOneWidget);
    expect(find.text('Applies to every line from this speaker'), findsOneWidget);
    await tester.tap(find.byKey(const Key('speaker_suggestion_yes')));
    await tester.tap(find.byKey(const Key('speaker_suggestion_someone_else')));
    expect(yes, ['yes']);
    expect(other, ['other']);

    await tester.tap(find.byTooltip('Collapse'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_suggestion_panel')), findsNothing);
  });

  test('a pinned near-miss event carries suggested_person_id; older payloads do not', () {
    final event = SpeakerLabelSuggestionEvent.fromJson(const {
      'speaker_id': 3,
      'person_id': '',
      'person_name': 'Maya Chen',
      'segment_id': 's1',
      'suggested_person_id': 'p-maya',
    });
    expect(event.personId, '');
    expect(event.suggestedPersonId, 'p-maya');
    final legacy = SpeakerLabelSuggestionEvent.fromJson(const {
      'speaker_id': 3,
      'person_id': 'p-maya',
      'person_name': 'Maya Chen',
      'segment_id': 's1',
    });
    expect(legacy.suggestedPersonId, isNull);
  });

  testWidgets('the suggestion can be expanded through its accessibility action', (tester) async {
    final handle = tester.ensureSemantics();
    await pump(tester);
    final node = tester.getSemantics(find.bySemanticsLabel('Is this Maya Chen?'));
    expect(node.getSemanticsData().hasAction(SemanticsAction.tap), isTrue);
    tester.binding.pipelineOwner.semanticsOwner!.performAction(node.id, SemanticsAction.tap);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_suggestion_panel')), findsOneWidget);
    handle.dispose();
  });
}
