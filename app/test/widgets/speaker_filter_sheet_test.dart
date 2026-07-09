import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/conversations/widgets/speaker_filter_sheet.dart';

void main() {
  final person = Person(id: 'person-1', name: 'Alex', createdAt: DateTime(2026), updatedAt: DateTime(2026));

  Widget buildSheet({String? selectedSpeakerId, required SpeakerSelected onSelected}) {
    return MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: SpeakerFilterSheet(
          people: [person],
          selectedSpeakerId: selectedSpeakerId,
          title: 'Speaker',
          allLabel: 'All',
          userLabel: 'You',
          onSelected: onSelected,
        ),
      ),
    );
  }

  testWidgets('renders all, user, and named speaker options', (tester) async {
    await tester.pumpWidget(buildSheet(onSelected: (_) async {}));

    expect(find.byKey(const Key('speaker_filter_all')), findsOneWidget);
    expect(find.byKey(const Key('speaker_filter_user')), findsOneWidget);
    expect(find.byKey(const Key('speaker_filter_person-1')), findsOneWidget);
    expect(find.text('Alex'), findsOneWidget);
  });

  testWidgets('returns the selected speaker id', (tester) async {
    String? selected;
    await tester.pumpWidget(
      buildSheet(
        onSelected: (speakerId) async {
          selected = speakerId;
        },
      ),
    );

    await tester.tap(find.byKey(const Key('speaker_filter_person-1')));
    await tester.pump();

    expect(selected, 'person-1');
  });

  testWidgets('returns user sentinel when you option is selected', (tester) async {
    String? selected;
    await tester.pumpWidget(
      buildSheet(
        onSelected: (speakerId) async {
          selected = speakerId;
        },
      ),
    );

    await tester.tap(find.byKey(const Key('speaker_filter_user')));
    await tester.pump();

    expect(selected, 'user');
  });

  testWidgets('returns null when all speakers is selected', (tester) async {
    String? selected = 'person-1';
    await tester.pumpWidget(
      buildSheet(
        selectedSpeakerId: 'person-1',
        onSelected: (speakerId) async {
          selected = speakerId;
        },
      ),
    );

    await tester.tap(find.byKey(const Key('speaker_filter_all')));
    await tester.pump();

    expect(selected, isNull);
  });
}
