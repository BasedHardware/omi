import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/pages/settings/integration_selection_card.dart';
import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/ui/ui.dart';

import '../ui/ui_test_app.dart';

void main() {
  group('IntegrationSelectionCard', () {
    testWidgets('announces a selectable button with its selected state and a >=44pt target', (tester) async {
      final handle = tester.ensureSemantics();
      var taps = 0;
      await pumpUi(
        tester,
        Scaffold(
          body: Column(
            children: [
              IntegrationSelectionCard(label: 'Work', isSelected: true, onTap: () => taps++),
              IntegrationSelectionCard(label: 'Personal', isSelected: false, onTap: () => taps++),
            ],
          ),
        ),
      );

      expect(
        tester.getSemantics(find.bySemanticsLabel('Work')),
        matchesSemantics(
          label: 'Work',
          isButton: true,
          hasSelectedState: true,
          isSelected: true,
          isInMutuallyExclusiveGroup: true,
          hasTapAction: true,
        ),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Personal')),
        matchesSemantics(
          label: 'Personal',
          isButton: true,
          hasSelectedState: true,
          isSelected: false,
          isInMutuallyExclusiveGroup: true,
          hasTapAction: true,
        ),
      );

      expect(tester.getSize(find.byType(InkWell).first).height, greaterThanOrEqualTo(44));

      await tester.tap(find.text('Personal'));
      expect(taps, 1);
      handle.dispose();
    });
  });

  group('IntegrationSettingsPage disconnect', () {
    testWidgets('confirms with a destructive Disconnect and shows no spinner while the dialog is open', (tester) async {
      var disconnectCalls = 0;
      await pumpUi(
        tester,
        IntegrationSettingsPage(
          appName: 'Todoist',
          appKey: 'todoist',
          disconnectService: () async => disconnectCalls++,
        ),
      );

      await tester.tap(find.widgetWithText(OmiButton, 'Disconnect'));
      await tester.pumpAndSettle();

      expect(find.text('Disconnect from Todoist?'), findsOneWidget);
      final confirm = tester.widget<TextButton>(
          find.widgetWithText(TextButton, 'Disconnect').last); // the dialog's, above the page button
      expect(confirm.style!.foregroundColor!.resolve({}), omiDialogDangerColor);
      // The page's button must not be busy just because the confirm is showing.
      expect(find.byType(OmiSpinner), findsNothing);

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(disconnectCalls, 0);
      expect(find.byType(OmiSpinner), findsNothing);
      expect(find.widgetWithText(OmiButton, 'Disconnect'), findsOneWidget);
    });
  });

  group('importJobTimestampLabel', () {
    testWidgets('follows the locale clock instead of a hand-built D/M/Y "at" string', (tester) async {
      late OmiDateFormat dates;
      await pumpUi(
        tester,
        Builder(
          builder: (context) {
            dates = OmiDateFormat.of(context);
            return const SizedBox();
          },
        ),
      );
      final createdAt = DateTime(2020, 7, 20, 21, 5).toUtc();

      final label = importJobTimestampLabel(dates, createdAt);

      expect(label, dates.timestamp(createdAt.toLocal()));
      expect(label, isNot(contains(' at ')));
      expect(label, contains('9:05'));
      expect(label, contains('2020'));
    });
  });
}
