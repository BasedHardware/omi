import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';
import 'package:nooto_v2/plan/widgets/plan_row.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';

ActionItem _jiraItem({
  String id = 'PROJ-1',
  String description = 'Fix the bug',
  String? status = 'In Review',
  String? statusType = 'indeterminate',
  String? projectKey = 'PROJ',
  String? priority,
  DateTime? statusChangedAt,
}) {
  return ActionItem(
    id: id,
    description: description,
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
    await tester.pumpWidget(_harness(PlanRow(item: _jiraItem(), onCheckboxTap: () async {})));

    expect(find.text('In Review'), findsOneWidget);
    // PROJ appears once: in the metadata strip (no project pill split unless onProjectTap is set).
    expect(find.text('PROJ'), findsOneWidget);
  });

  testWidgets('Jira row hides "Medium" priority but shows "P1"', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(priority: 'Medium'),
          onCheckboxTap: () async {},
        ),
      ),
    );
    expect(find.text('Medium'), findsNothing);

    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(priority: 'P1'),
          onCheckboxTap: () async {},
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
          onCheckboxTap: () async {},
        ),
      ),
    );

    expect(find.text('5d at status'), findsOneWidget);
  });

  testWidgets('Transcript row in mixed-source group renders "From conversation" prefix', (tester) async {
    await tester.pumpWidget(
      _harness(PlanRow(item: _transcriptItem(), onCheckboxTap: () async {}, sectionHasMixedSources: true)),
    );

    expect(find.text('From conversation'), findsOneWidget);
    expect(find.text('2d ago'), findsOneWidget);
  });

  testWidgets('Transcript row in single-source group drops "From conversation" prefix', (tester) async {
    await tester.pumpWidget(
      _harness(PlanRow(item: _transcriptItem(), onCheckboxTap: () async {}, sectionHasMixedSources: false)),
    );

    // Suppression rule: when no Jira items are visible in the group, the
    // source prefix is noise. Render only the relative age.
    expect(find.text('From conversation'), findsNothing);
    expect(find.text('2d ago'), findsOneWidget);
  });

  testWidgets('Transcript row with no createdAt shows no metadata strip', (tester) async {
    final noAge = ActionItem(id: 't2', description: 'no age', completed: false);
    await tester.pumpWidget(_harness(PlanRow(item: noAge, onCheckboxTap: () async {})));

    expect(find.text('From conversation'), findsNothing);
  });

  // REGRESSION: row body tap must NOT mark the item complete. The prior
  // behavior (whole-row InkWell → onToggle) caused silent Jira desyncs:
  // tapping a Jira row called the local-only `complete()` PATCH without
  // firing a Jira transition, so the row disappeared from Plan while the
  // Jira ticket stayed open. Locking the regression here so that path can
  // never come back even though the row-body InkWell is back (now wired to
  // onRowBodyTap, NOT onCheckboxTap).
  testWidgets('tap on row body does NOT trigger onCheckboxTap (regression)', (tester) async {
    var checkboxTapped = false;
    var bodyTapped = false;
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(),
          onCheckboxTap: () async {
            checkboxTapped = true;
          },
          onRowBodyTap: () {
            bodyTapped = true;
          },
        ),
      ),
    );

    await tester.tap(find.text('Fix the bug'));
    await tester.pumpAndSettle();

    // Row body fires its OWN handler (open-Jira-URL in production); never
    // the completion handler.
    expect(checkboxTapped, isFalse, reason: 'row body must never trigger completion');
    expect(bodyTapped, isTrue, reason: 'row body should fire its own callback');
  });

  testWidgets('row InkWell is disabled when onRowBodyTap is null (transcript rows)', (tester) async {
    var checkboxTapped = false;
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _transcriptItem(),
          onCheckboxTap: () async {
            checkboxTapped = true;
          },
          // onRowBodyTap omitted → defaults to null → InkWell disabled.
        ),
      ),
    );

    await tester.tap(find.text('Talk to designer about onboarding'));
    await tester.pumpAndSettle();

    expect(checkboxTapped, isFalse);
  });

  testWidgets('tap on checkbox triggers onCheckboxTap and not onRowBodyTap', (tester) async {
    var checkboxTapped = false;
    var bodyTapped = false;
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(),
          onCheckboxTap: () async {
            checkboxTapped = true;
          },
          onRowBodyTap: () {
            bodyTapped = true;
          },
        ),
      ),
    );

    // The checkbox lives inside a Semantics(button:true, label:'Mark complete')
    // wrapper. Its GestureDetector(behavior:opaque) intercepts taps before the
    // row InkWell catches them.
    await tester.tap(find.bySemanticsLabel('Mark complete'));
    await tester.pumpAndSettle();

    expect(checkboxTapped, isTrue);
    expect(bodyTapped, isFalse, reason: 'checkbox must not propagate to row body');
  });

  testWidgets('checkbox hit region is HIG-compliant vertically + at least the original spacingM gap horizontally', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRow(item: _jiraItem(), onCheckboxTap: () async {}),
      ),
    );

    // The Semantics wrapper sits directly above the GestureDetector +
    // SizedBox(32, 44). Width is intentionally 32pt (20 visual + 12 gap)
    // so the description still lands at 32pt from the row's left edge —
    // matching the layout that shipped before the gesture refactor. The
    // row's outer InkWell extends the *effective* tap area horizontally
    // by routing taps anywhere outside the checkbox to the row-body
    // handler (open-Jira-URL on Jira items), so there's no dead zone for
    // big thumbs even at 32pt nominal width.
    final hitTarget = tester.getSize(find.bySemanticsLabel('Mark complete'));
    expect(hitTarget.height, greaterThanOrEqualTo(44.0), reason: 'HIG vertical minimum');
    expect(hitTarget.width, greaterThanOrEqualTo(32.0), reason: 'matches checkbox + spacingM');
  });

  testWidgets('onProjectTap renders splits the chip and tapping the project pill calls back', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      _harness(PlanRow(item: _jiraItem(), onCheckboxTap: () async {}, onProjectTap: () => tapped = true)),
    );

    // Project pill has the "PROJ" text in a separate widget. Tap on the
    // first occurrence in the chip area.
    final projectPills = find.text('PROJ');
    expect(projectPills, findsWidgets); // chip + meta strip both render PROJ
    await tester.tap(projectPills.first);
    await tester.pumpAndSettle();

    expect(tapped, isTrue);
  });

  // U1 — title clamp.
  testWidgets('long title clamps to 2 lines with ellipsis (with chip)', (tester) async {
    final longTitle =
        'A very long Jira summary that definitely exceeds two lines on a normal phone width '
        'and would otherwise wrap into three or four lines eating valuable vertical space '
        'in the dense-packed plan list view that we are tightening here.';
    await tester.pumpWidget(
      _harness(
        SizedBox(
          width: 320,
          child: PlanRow(item: _jiraItem(description: longTitle), onCheckboxTap: () async {}),
        ),
      ),
    );
    final titleFinder = find.text(longTitle);
    expect(titleFinder, findsOneWidget);
    final titleWidget = tester.widget<Text>(titleFinder);
    expect(titleWidget.maxLines, 2);
    expect(titleWidget.overflow, TextOverflow.ellipsis);
  });

  testWidgets('long title clamps to 2 lines with ellipsis (no chip)', (tester) async {
    final longTitle = 'A long transcript-derived task description ' * 4;
    final transcript = ActionItem(
      id: 't-long',
      description: longTitle,
      completed: false,
      createdAt: DateTime.now().subtract(const Duration(days: 1)),
    );
    await tester.pumpWidget(
      _harness(
        SizedBox(
          width: 320,
          child: PlanRow(item: transcript, onCheckboxTap: () async {}),
        ),
      ),
    );
    final titleFinder = find.text(longTitle);
    expect(titleFinder, findsOneWidget);
    final titleWidget = tester.widget<Text>(titleFinder);
    expect(titleWidget.maxLines, 2);
    expect(titleWidget.overflow, TextOverflow.ellipsis);
  });

  // U2 — pivot=byProject suppresses the project chip pill.
  testWidgets('pivot=byProject hides project pill on chip but keeps id pill', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(),
          onCheckboxTap: () async {},
          onProjectTap: () {},
          pivot: PlanPivot.byProject,
        ),
      ),
    );

    // The id pill ("PROJ-1") is the tap-to-open hook — must remain.
    expect(find.text('PROJ-1'), findsOneWidget);
    // Project pill is suppressed: "PROJ" only appears in the metadata
    // strip, not as a separate tappable pill on the chip. With showProject
    // false the chip falls back to single-pill rendering (id only), so
    // "PROJ" should appear exactly once (in the meta strip).
    expect(find.text('PROJ'), findsOneWidget);
  });

  // U2 — pivot=byStatus drops the status segment from the metadata strip.
  testWidgets('pivot=byStatus drops status from metadata strip but keeps project + days', (tester) async {
    final threeDaysAgo = DateTime.now().subtract(const Duration(days: 3, hours: 2));
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(status: 'Backlog', statusChangedAt: threeDaysAgo),
          onCheckboxTap: () async {},
          pivot: PlanPivot.byStatus,
        ),
      ),
    );

    // Status name is suppressed (the section header already shows it).
    expect(find.text('Backlog'), findsNothing);
    // Other fields still render.
    expect(find.text('PROJ'), findsOneWidget);
    expect(find.text('3d at status'), findsOneWidget);
  });

  testWidgets('pivot=byStatus still renders priority when set', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(status: 'Backlog', priority: 'P1'),
          onCheckboxTap: () async {},
          pivot: PlanPivot.byStatus,
        ),
      ),
    );

    expect(find.text('Backlog'), findsNothing);
    expect(find.text('P1'), findsOneWidget);
  });

  // U2 — pivot=byDate (the default) renders everything (regression).
  testWidgets('pivot=byDate renders status AND project chip pill (regression)', (tester) async {
    await tester.pumpWidget(
      _harness(
        PlanRow(
          item: _jiraItem(),
          onCheckboxTap: () async {},
          onProjectTap: () {},
          pivot: PlanPivot.byDate,
        ),
      ),
    );

    // Status visible in meta strip.
    expect(find.text('In Review'), findsOneWidget);
    // PROJ appears twice: once on the chip's project pill, once in the meta strip.
    expect(find.text('PROJ'), findsNWidgets(2));
  });

  // U3 — _stripProjectPrefix unit tests.
  group('stripProjectPrefix', () {
    ExternalSource source(String key) => ExternalSource(
      source: 'jira',
      externalId: '$key-1',
      url: 'https://x/$key-1',
      metadata: {'project_key': key},
    );

    test('strips "<Project Name>: [<KEY>-NN] " prefix', () {
      final stripped = PlanRow.stripProjectPrefix('WarpNG ERP: [WPNG-12] Add Partner hooks', source('WPNG'));
      expect(stripped, 'Add Partner hooks');
    });

    test('strips when bracket token has the key plus letters/digits', () {
      final stripped = PlanRow.stripProjectPrefix('Project: [TASK-123] Do the thing', source('TASK'));
      expect(stripped, 'Do the thing');
    });

    test('does not strip when the bracket token does not start with the key (conservative)', () {
      // "P4-T04" does not start with "WPNG" — the regex stays conservative.
      // The redundancy here is acceptable; better than mis-stripping into
      // garbage.
      final stripped = PlanRow.stripProjectPrefix('WarpNG ERP: [P4-T04] Add Partner-aware hooks', source('WPNG'));
      expect(stripped, 'WarpNG ERP: [P4-T04] Add Partner-aware hooks');
    });

    test('preserves description with no project prefix', () {
      final stripped = PlanRow.stripProjectPrefix('Talk to designer about onboarding', source('PROJ'));
      expect(stripped, 'Talk to designer about onboarding');
    });

    test('returns original when source is null', () {
      final stripped = PlanRow.stripProjectPrefix('PROJ: [PROJ-1] hello', null);
      expect(stripped, 'PROJ: [PROJ-1] hello');
    });

    test('returns original when source has no project_key', () {
      final ext = ExternalSource(source: 'jira', externalId: 'X-1', url: 'https://x/X-1', metadata: {});
      final stripped = PlanRow.stripProjectPrefix('PROJ: [PROJ-1] hello', ext);
      expect(stripped, 'PROJ: [PROJ-1] hello');
    });

    test('refuses to strip when the result would be empty/near-empty', () {
      // After stripping, only "ok" remains (2 chars) — defensive guard kicks
      // in and returns the original. "[P4-T04]" alone is worse than the
      // prefix duplication.
      final stripped = PlanRow.stripProjectPrefix('Title: [WPNG-1] ok', source('WPNG'));
      expect(stripped, 'Title: [WPNG-1] ok');
    });
  });
}
