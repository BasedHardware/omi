import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a single-day sheet with a callback needs no provider and shows no Remove', (tester) async {
    (DateTime, DateTime)? selected;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showConversationDateRangePicker(
              context,
              initialStartDate: DateTime(2026, 9, 12),
              singleDayOnly: true,
              onSelected: (start, end) => selected = (start, end),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));

    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byKey(const Key('date_range_remove')), findsNothing);
    final calendar = tester.widget<CalendarDatePicker2>(find.byType(CalendarDatePicker2));
    expect(calendar.value, [DateTime(2026, 9, 12)]);
    expect(calendar.displayedMonthDate, DateTime(2026, 9, 12), reason: 'the sheet opens on its selected context month');

    tester.widget<CalendarDatePicker2>(find.byType(CalendarDatePicker2)).onValueChanged?.call([DateTime(2026, 9, 20)]);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const Key('date_range_done')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(selected, (DateTime(2026, 9, 20), DateTime(2026, 9, 20)));
  });

  testWidgets('a single-day chip labels one date and clears through one semantics action', (tester) async {
    var clears = 0;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: OmiDateFilterChip(
          start: DateTime(2026, 9, 12),
          end: DateTime(2026, 9, 12, 23, 59, 59, 999, 999),
          onClear: () => clears++,
        ),
      ),
    ));

    expect(find.textContaining('–'), findsNothing, reason: 'a day-end bound is not a range');
    expect(find.textContaining('Sep'), findsOneWidget);

    await tester.tap(find.byType(OmiDateFilterChip));
    expect(clears, 1);

    final semantics = tester.getSemantics(find.byType(OmiDateFilterChip));
    expect(semantics.label, contains('Remove Filter'));
  });
}
