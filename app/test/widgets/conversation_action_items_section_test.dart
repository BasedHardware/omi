import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_action_items_section.dart';
import 'package:omi/ui/ui.dart';

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));
  late OmiDateFormat dates;
  setUpAll(() async {
    await initializeDateFormatting();
    dates = OmiDateFormat(
      locale: const Locale('en'),
      use24HourFormat: false,
      l10n: l10n,
      clock: () => DateTime(2026, 10, 5, 12),
    );
  });

  group('ActionItemMeta', () {
    test('an item with no owner, due date or context has no metadata, never "Unknown"', () {
      final meta = ActionItemMeta.of(ActionItem('Send the deck'), l10n: l10n, dates: dates);
      expect(meta.owner, isNull);
      expect(meta.due, isNull);
      expect(meta.context, isNull);
      expect(meta.hasOwnerOrDue, isFalse);
    });

    test('the reader\'s own item is "You"; another owner keeps their name', () {
      final mine = ActionItem('Send the deck', captureOwner: 'user', ownerName: 'David');
      final theirs = ActionItem('Share the provider info', captureOwner: 'other', ownerName: 'Eddie Thai');
      expect(ActionItemMeta.of(mine, l10n: l10n, dates: dates).owner, 'You');
      expect(ActionItemMeta.of(theirs, l10n: l10n, dates: dates).owner, 'Eddie Thai');
    });

    test('a blank or email-shaped owner name is left out', () {
      for (final name in ['  ', 'eddie@example.com']) {
        final meta = ActionItemMeta.of(ActionItem('x', ownerName: name), l10n: l10n, dates: dates);
        expect(meta.owner, isNull, reason: name);
      }
    });

    test('due date reads as a local day; context is trimmed', () {
      final item = ActionItem('x', dueAt: DateTime(2026, 10, 7, 9), context: '  Eddie will forward it. ');
      final meta = ActionItemMeta.of(item, l10n: l10n, dates: dates);
      expect(meta.due, 'Due Wed, Oct 7');
      expect(meta.context, 'Eddie will forward it.');
      expect(ActionItemMeta.of(ActionItem('x', dueAt: DateTime(2026, 10, 5, 18)), l10n: l10n, dates: dates).due,
          'Due Today');
    });
  });

  group('ConversationActionItemsSection', () {
    Future<void> pump(WidgetTester tester, List<ActionItem> items) async {
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: CustomScrollView(slivers: [ConversationActionItemsSection(items: items)]),
        ),
      ));
    }

    testWidgets('is absent when every item is deleted', (tester) async {
      await pump(tester, [ActionItem('gone', deleted: true)]);
      expect(find.byKey(const ValueKey('conversation_action_items_section')), findsNothing);
    });

    testWidgets('shows owner, due and context, and no "Unknown" placeholder', (tester) async {
      await pump(tester, [
        ActionItem(
          'Share the wind-down provider information with David.',
          captureOwner: 'other',
          ownerName: 'Eddie Thai',
          dueAt: DateTime(2026, 10, 7),
          context: 'Eddie said they would follow up about Simple Closure.',
        ),
        ActionItem('Send investors an update on the wind-down plan.', captureOwner: 'user'),
        ActionItem('Something with no metadata at all.'),
      ]);
      expect(find.text('Tasks'), findsOneWidget);
      expect(find.text('Eddie Thai'), findsOneWidget);
      expect(find.text('ET'), findsOneWidget);
      expect(find.text('Eddie said they would follow up about Simple Closure.'), findsOneWidget);
      expect(find.text('You'), findsOneWidget);
      // A known due date renders; the undated rows still never say "Due".
      expect(find.textContaining('Due'), findsOneWidget);
      expect(find.text('Due Wed, Oct 7'), findsOneWidget);
      expect(find.textContaining('Unknown'), findsNothing);
    });
  });
}
