import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/ui/format/omi_date_format.dart';

void main() {
  testWidgets('active date range empty state uses localized date text instead of the new-user message', (tester) async {
    final start = DateTime(2026, 7, 1);
    final end = DateTime(2026, 7, 3);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) => Scaffold(
          body: EmptyConversationsWidget(
            dateFilterLabel: '${OmiDateFormat.of(context).date(start)} – ${OmiDateFormat.of(context).date(end)}',
          ),
        ),
      ),
    ));

    expect(find.text('No conversations on Jul 1, 2026 – Jul 3, 2026'), findsOneWidget);
    expect(find.text('No conversations yet'), findsNothing);
  });
}
