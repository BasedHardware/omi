import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/developer_section_header.dart';
import 'package:omi/ui/ui.dart';

Future<void> _pump(WidgetTester tester, {required double textScale, required List<int> created}) async {
  tester.view.physicalSize = const Size(320, 640);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      builder: (context, child) =>
          MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)), child: child!),
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          child: DeveloperSectionHeader(
            title: 'Developer API',
            docs: OmiButton.secondary(label: 'Docs', size: OmiButtonSize.compact, onPressed: () {}),
            onCreateKey: () => created.add(1),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  // #19240: Docs and Create Key sat in a Row that ran off a 320 pt phone at larger text (and in
  // German or French); they now wrap under the title.
  for (final scale in [1.0, 1.3]) {
    testWidgets('Docs and Create Key stay on screen at 320 pt and ${scale}x text', (tester) async {
      final created = <int>[];
      await _pump(tester, textScale: scale, created: created);

      expect(tester.takeException(), isNull, reason: 'no overflow');
      final l10n = AppLocalizations.of(tester.element(find.byType(DeveloperSectionHeader)));
      for (final label in ['Docs', l10n.createKey]) {
        final rect = tester.getRect(find.text(label));
        expect(rect.right, lessThanOrEqualTo(320), reason: '$label is on screen');
      }
    });
  }

  testWidgets('Create Key calls back', (tester) async {
    final created = <int>[];
    await _pump(tester, textScale: 1.0, created: created);
    final l10n = AppLocalizations.of(tester.element(find.byType(DeveloperSectionHeader)));

    await tester.tap(find.text(l10n.createKey));
    await tester.pump();

    expect(created, [1]);
  });
}
