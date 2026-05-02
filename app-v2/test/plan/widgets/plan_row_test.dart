import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/plan/widgets/plan_row.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';

ActionItem _jiraItem({
  String id = 'PROJ-1',
  String? status = 'In Review',
  String? statusType = 'indeterminate',
  String? projectKey = 'PROJ',
  String? priority,
  DateTime? statusChangedAt,
}) {
  return ActionItem(
    id: id,
    description: 'Fix the bug',
    completed: false,
    createdAt: DateTime(2026, 4, 1),
    externalSource: ExternalSource(
      source: 'jira',
      externalId: id,
      url: 'https://x/$id',
      metadata: {
        if (status != null) 'status': status,
        if (statusType != null) 'status_type': statusType,
        if (projectKey != null) 'project_key': projectKey,
        if (priority != null) 'priority': priority,
        if (statusChangedAt != null) 'status_changed_at': statusChangedAt.toUtc().toIso8601String(),
      },
    ),
  );
}

ActionItem _transcriptItem({DateTime? createdAt}) => ActionItem(
  id: 't1',
  description: 'Talk to designer about onboarding',
  completed: false,
  createdAt: createdAt ?? DateTime.now().subtract(const Duration(days: 2)),
);

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('Jira row renders status text in metadata strip', (tester) async {
    await tester.pumpWidget(_harness(PlanRow(item: _jiraItem(), onToggle: () async {})));

    expect(find.text('In Review'), findsOneWidget);
    // PROJ appears once: in the metadata strip (no project pill split unless onProjectTap is set).
    expect(find.text('PROJ'), findsOneWidget);
  });

  testWidgets('Jira row hides "Medium" priority but shows "P1"', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(priority: 'Medium'),
          onToggle: () async {},
        ),
      ),
    );
    expect(find.text('Medium'), findsNothing);

    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(priority: 'P1'),
          onToggle: () async {},
        ),
      ),
    );
    expect(find.text('P1'), findsOneWidget);
  });

  testWidgets('Jira row shows "Xd at status" when daysAtStatus > 0', (tester) async {
    final fiveDaysAgo = DateTime.now().subtract(const Duration(days: 5, hours: 2));
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(statusChangedAt: fiveDaysAgo),
          onToggle: () async {},
        ),
      ),
    );

    expect(find.text('5d at status'), findsOneWidget);
  });

  testWidgets('Transcript row in mixed-source group renders "From conversation" prefix', (tester) async {
    await tester.pumpWidget(
      _harness(PlanRow(item: _transcriptItem(), onToggle: () async {}, sectionHasMixedSources: true)),
    );

    expect(find.text('From conversation'), findsOneWidget);
    expect(find.text('2d ago'), findsOneWidget);
  });

  testWidgets('Transcript row in single-source group drops "From conversation" prefix', (tester) async {
    await tester.pumpWidget(
      _harness(PlanRow(item: _transcriptItem(), onToggle: () async {}, sectionHasMixedSources: false)),
    );

    // Suppression rule: when no Jira items are visible in the group, the
    // source prefix is noise. Render only the relative age.
    expect(find.text('From conversation'), findsNothing);
    expect(find.text('2d ago'), findsOneWidget);
  });

  testWidgets('Transcript row with no createdAt shows no metadata strip', (tester) async {
    final noAge = ActionItem(id: 't2', description: 'no age', completed: false);
    await tester.pumpWidget(_harness(PlanRow(item: noAge, onToggle: () async {})));

    expect(find.text('From conversation'), findsNothing);
  });

  testWidgets('tap on row triggers onToggle', (tester) async {
    var toggled = false;
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(),
          onToggle: () async {
            toggled = true;
          },
        ),
      ),
    );

    // Tap on the description text — the InkWell wraps the whole row.
    await tester.tap(find.text('Fix the bug'));
    await tester.pumpAndSettle();

    expect(toggled, isTrue);
  });

  testWidgets('onProjectTap renders splits the chip and tapping the project pill calls back', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      _harness(PlanRow(item: _jiraItem(), onToggle: () async {}, onProjectTap: () => tapped = true)),
    );

    // Project pill has the "PROJ" text in a separate widget. Tap on the
    // first occurrence in the chip area.
    final projectPills = find.text('PROJ');
    expect(projectPills, findsWidgets); // chip + meta strip both render PROJ
    await tester.tap(projectPills.first);
    await tester.pumpAndSettle();

    expect(tapped, isTrue);
  });
}
