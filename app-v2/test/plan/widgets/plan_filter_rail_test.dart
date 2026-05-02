import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/plan/widgets/plan_filter_rail.dart';
import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';

Widget _harness({
  required PlanFilter selected,
  required ValueChanged<PlanFilter> onChanged,
  PlanPivot pivot = PlanPivot.byDate,
  ValueChanged<PlanPivot>? onPivotChanged,
  String? activeProjectFilter,
  VoidCallback? onClearProjectFilter,
}) {
  return MaterialApp(
    home: Scaffold(
      body: PlanFilterRail(
        selected: selected,
        onChanged: onChanged,
        pivot: pivot,
        onPivotChanged: onPivotChanged ?? (_) {},
        activeProjectFilter: activeProjectFilter,
        onClearProjectFilter: onClearProjectFilter,
      ),
    ),
  );
}

void main() {
  testWidgets('renders three filter chips (Mine dropped)', (tester) async {
    await tester.pumpWidget(_harness(selected: PlanFilter.all, onChanged: (_) {}));

    expect(find.text('All'), findsOneWidget);
    expect(find.text('Stuck'), findsOneWidget);
    expect(find.text('Due Soon'), findsOneWidget);
    expect(find.text('Mine'), findsNothing);
  });

  testWidgets('renders the leading pivot pill with the active label', (tester) async {
    await tester.pumpWidget(_harness(selected: PlanFilter.all, onChanged: (_) {}, pivot: PlanPivot.byProject));

    expect(find.text('By Project'), findsOneWidget);
    expect(find.byIcon(Icons.arrow_drop_down_rounded), findsOneWidget);
  });

  testWidgets('tapping the pivot pill opens a CupertinoActionSheet', (tester) async {
    await tester.pumpWidget(_harness(selected: PlanFilter.all, onChanged: (_) {}));

    await tester.tap(find.text('By Date'));
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoActionSheet), findsOneWidget);
    expect(find.text('By Project'), findsOneWidget);
    expect(find.text('By Status'), findsOneWidget);
  });

  testWidgets('selecting a different pivot fires onPivotChanged', (tester) async {
    PlanPivot? picked;
    await tester.pumpWidget(_harness(selected: PlanFilter.all, onChanged: (_) {}, onPivotChanged: (p) => picked = p));

    await tester.tap(find.text('By Date'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('By Status'));
    await tester.pumpAndSettle();

    expect(picked, PlanPivot.byStatus);
  });

  testWidgets('tapping a filter chip fires onChanged with that filter', (tester) async {
    PlanFilter? picked;
    await tester.pumpWidget(_harness(selected: PlanFilter.all, onChanged: (f) => picked = f));

    await tester.tap(find.text('Stuck'));
    await tester.pumpAndSettle();

    expect(picked, PlanFilter.stuck);
  });

  testWidgets('selection state changes between chips', (tester) async {
    PlanFilter selected = PlanFilter.all;
    await tester.pumpWidget(
      StatefulBuilder(
        builder: (context, setState) {
          return _harness(selected: selected, onChanged: (f) => setState(() => selected = f));
        },
      ),
    );

    expect(selected, PlanFilter.all);

    await tester.tap(find.text('Due Soon'));
    await tester.pumpAndSettle();

    expect(selected, PlanFilter.dueSoon);
  });

  testWidgets('active project filter renders an extra chip with × label', (tester) async {
    var cleared = false;
    await tester.pumpWidget(
      _harness(
        selected: PlanFilter.all,
        onChanged: (_) {},
        activeProjectFilter: 'PROJ',
        onClearProjectFilter: () => cleared = true,
      ),
    );

    expect(find.text('PROJ ×'), findsOneWidget);

    await tester.tap(find.text('PROJ ×'));
    await tester.pumpAndSettle();

    expect(cleared, isTrue);
  });
}
