import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/plan/plan_screen.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';

ActionItem _jiraItem({String id = 'PROJ-1', String? statusType = 'indeterminate'}) => ActionItem(
  id: id,
  description: 'Fix $id',
  completed: false,
  externalSource: ExternalSource(
    source: 'jira',
    externalId: id,
    url: 'https://x/$id',
    metadata: {'status': 'In Progress', if (statusType != null) 'status_type': statusType, 'project_key': 'PROJ'},
  ),
);

ActionItem _transcriptItem() => ActionItem(
  id: 't1',
  description: 'Talk to designer',
  completed: false,
  createdAt: DateTime.now().subtract(const Duration(days: 2)),
);

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('two-way-sync OFF wraps Jira rows WITHOUT Dismissible', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRowSwipeWrapper(
          item: _jiraItem(),
          sectionHasMixedSources: false,
          onToggle: () async {},
          onProjectTap: null,
          jiraSwipeEnabled: false,
          onTransition: () async {},
          onSnooze: () async {},
          onLongPress: () async {},
        ),
      ),
    );

    expect(find.text('Fix PROJ-1'), findsOneWidget);
    expect(find.byType(Dismissible), findsNothing);
  });

  testWidgets('two-way-sync ON wraps Jira rows WITH Dismissible', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRowSwipeWrapper(
          item: _jiraItem(),
          sectionHasMixedSources: false,
          onToggle: () async {},
          onProjectTap: null,
          jiraSwipeEnabled: true,
          onTransition: () async {},
          onSnooze: () async {},
          onLongPress: () async {},
        ),
      ),
    );

    expect(find.text('Fix PROJ-1'), findsOneWidget);
    expect(find.byType(Dismissible), findsOneWidget);
  });

  testWidgets('transcript items never get a Dismissible even with toggle ON', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRowSwipeWrapper(
          item: _transcriptItem(),
          sectionHasMixedSources: false,
          onToggle: () async {},
          onProjectTap: null,
          jiraSwipeEnabled: true,
          onTransition: () async {},
          onSnooze: () async {},
          onLongPress: () async {},
        ),
      ),
    );

    expect(find.text('Talk to designer'), findsOneWidget);
    expect(find.byType(Dismissible), findsNothing);
  });

  testWidgets('long-press on Jira row fires onLongPress (toggle OFF too)', (tester) async {
    var longPressed = false;
    await tester.pumpWidget(
      _harness(
        PlanRowSwipeWrapper(
          item: _jiraItem(),
          sectionHasMixedSources: false,
          onToggle: () async {},
          onProjectTap: null,
          jiraSwipeEnabled: false,
          onTransition: () async {},
          onSnooze: () async {},
          onLongPress: () async {
            longPressed = true;
          },
        ),
      ),
    );

    await tester.longPress(find.text('Fix PROJ-1'));
    await tester.pump();

    expect(longPressed, isTrue);
  });
}
