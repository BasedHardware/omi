import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';

const _prompt = 'Summarize every meeting into action items and send them to my team on Slack each evening';

Future<List<String>> _pump(WidgetTester tester, double textScale) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final tried = <String>[];
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      builder: (context, child) =>
          MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)), child: child!),
      home: Scaffold(
        body: Column(
          children: [
            AiSuggestionStrip(prompts: const [_prompt, 'Remind me'], loading: false, onTry: tried.add)
          ],
        ),
      ),
    ),
  );
  await tester.pump();
  return tried;
}

void main() {
  // #19239: the strip was a fixed 160 pt, so three lines and Try it overflowed at larger text.
  for (final scale in [1.0, 1.15, 1.3, 1.5]) {
    testWidgets('three lines and Try it fit at ${scale}x text', (tester) async {
      await _pump(tester, scale);
      expect(tester.takeException(), isNull, reason: 'no overflow');
    });
  }

  testWidgets('Try it hands its suggestion back', (tester) async {
    final tried = await _pump(tester, 1.0);
    final l10n = AppLocalizations.of(tester.element(find.byType(AiSuggestionStrip)));

    await tester.tap(find.text(l10n.tryIt).first);
    await tester.pump();

    expect(tried, [_prompt]);
  });
}
