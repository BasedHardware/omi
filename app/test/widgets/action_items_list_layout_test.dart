import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/typed_action_items_screen.dart';

/// One clock for the fixture and the expected labels, captured once when the file loads.
final DateTime _now = DateTime.now();

/// A due time on the day [offset] days from today. Today's own entry has to stay in the future
/// for the whole test, so it is the last instant of today (or just after now in the final second).
DateTime _day(int offset) {
  final endOfDay = DateTime(_now.year, _now.month, _now.day + offset, 23, 59, 59, 999);
  if (offset == 0 && !endOfDay.isAfter(_now)) return _now.add(const Duration(milliseconds: 100));
  return endOfDay;
}

Future<ActionItemsResponse?> _items({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    ActionItemsResponse(
      actionItems: completed == true
          ? const []
          : [
              ActionItemWithMetadata(id: 'late', description: 'Call Sam back', completed: false, dueAt: _day(-1)),
              ActionItemWithMetadata(id: 'today', description: 'Draft the update', completed: false, dueAt: _day(0)),
              ActionItemWithMetadata(id: 'today2', description: 'Open the PR', completed: false, dueAt: _day(0)),
              ActionItemWithMetadata(id: 'soon', description: 'Book the dentist', completed: false, dueAt: _day(3)),
              ActionItemWithMetadata(id: 'far', description: 'Renew the passport', completed: false, dueAt: _day(13)),
            ],
    );

/// The Tasks list reads top-down from what slipped: Overdue first, quiet sentence-case headings, and
/// the due day only where the heading leaves it open (#19859).
void main() {
  setUp(() {
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<ActionItemsProvider> pumpPage(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final provider = ActionItemsProvider(getActionItems: _items);
    addTearDown(provider.dispose);
    await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
    await provider.ensureLoaded();
    await tester.pumpAndSettle();
    return provider;
  }

  testWidgets('Overdue is the first section and headings are sentence case', (tester) async {
    await pumpPage(tester);
    expect(find.text('Overdue'), findsOneWidget);
    expect(find.text('OVERDUE'), findsNothing);
    expect(find.text('TODAY'), findsNothing);
    final overdueTop = tester.getTopLeft(find.text('Overdue')).dy;
    expect(overdueTop, lessThan(tester.getTopLeft(find.text('Today')).dy));
    expect(overdueTop, lessThan(tester.getTopLeft(find.text('Later')).dy));
    expect(tester.getTopLeft(find.text('Call Sam back')).dy,
        lessThan(tester.getTopLeft(find.text('Draft the update')).dy));
  });

  testWidgets('the due day shows on Overdue and Later rows only, red while overdue', (tester) async {
    await pumpPage(tester);
    String weekday(int offset) => DateFormat.E('en').format(_day(offset));
    final late = find.text(weekday(-1));
    expect(late, findsOneWidget);
    expect(tester.widget<Text>(late).style!.color, OmiColors.danger);
    expect(find.text(weekday(3)), findsOneWidget);
    expect(find.text(DateFormat.MMMd('en').format(_day(13))), findsOneWidget);
    expect(tester.widget<Text>(find.text(weekday(3))).style!.color, OmiColors.textTertiary);
    expect(find.text(weekday(0)), findsNothing, reason: 'Today already names the day');
  });

  testWidgets('rows in a section are split by a hairline, the last one is not', (tester) async {
    await pumpPage(tester);
    final hairlines = find.byWidgetPredicate((w) => w is Container && w.constraints?.maxHeight == 0.5);
    // Today has two rows and Later has two: one hairline each.
    expect(hairlines, findsNWidgets(2));
  });
}
