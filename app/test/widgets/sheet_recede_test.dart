import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';

/// Motion N2: the page behind a bottom sheet shrinks to 92% and comes back when it closes.
class _Counter extends StatefulWidget {
  const _Counter();

  @override
  State<_Counter> createState() => _CounterState();
}

class _CounterState extends State<_Counter> {
  int taps = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextButton(onPressed: () => setState(() => taps++), child: Text('taps $taps')),
            TextButton(
              onPressed: () => showOmiSheet<void>(
                context: context,
                builder: (sheetContext) => Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('sheet body'),
                    // A settings row: its page opens on top of the sheet.
                    TextButton(
                      onPressed: () => Navigator.of(sheetContext)
                          .push(omiPageRoute<void>(builder: (_) => const Scaffold(body: Text('section page')))),
                      child: const Text('open section'),
                    ),
                  ],
                ),
              ),
              child: const Text('open'),
            ),
          ],
        ),
      ),
    );
  }
}

void main() {
  Widget app({bool reduceMotion = false}) => MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        navigatorObservers: [OmiSheetObserver()],
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion), child: child!),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => Navigator.of(context).push(omiPageRoute<void>(builder: (_) => const _Counter())),
                child: const Text('push'),
              ),
            ),
          ),
        ),
      );

  double pageScale(WidgetTester tester) {
    final transform = tester.widget<Transform>(
      find.descendant(of: find.byType(OmiSheetRecede), matching: find.byType(Transform)).first,
    );
    return transform.transform.storage[0]; // x scale
  }

  testWidgets('the page shrinks to 92% behind a sheet, keeps its state, and comes back', (tester) async {
    await tester.pumpWidget(app());
    await tester.tap(find.text('push'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('taps 0'));
    await tester.pump();
    expect(pageScale(tester), 1);

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('sheet body'), findsOneWidget);
    expect(pageScale(tester), closeTo(0.92, 0.001));
    expect(OmiSheetDepth.value.value, 1);

    Navigator.of(tester.element(find.text('sheet body'))).pop();
    await tester.pumpAndSettle();
    expect(pageScale(tester), 1);
    expect(OmiSheetDepth.value.value, 0);
    // Same page, same state: the recede never rebuilt it.
    expect(find.text('taps 1'), findsOneWidget);
  });

  testWidgets('a page opened from a sheet sits in front of it at full size (Settings → a section)', (tester) async {
    await tester.pumpWidget(app());
    await tester.tap(find.text('push'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('open section'));
    await tester.pumpAndSettle();
    expect(find.text('section page'), findsOneWidget);
    double scaleOf(String text) => tester
        .widget<Transform>(find
            .ancestor(
                of: find.text(text, skipOffstage: false),
                matching: find.descendant(
                    of: find.byType(OmiSheetRecede, skipOffstage: false),
                    matching: find.byType(Transform, skipOffstage: false)))
            .first)
        .transform
        .storage[0];
    expect(scaleOf('section page'), 1, reason: 'no black frame around a section');
    expect(scaleOf('taps 0'), closeTo(0.92, 0.001), reason: 'the page under the sheet stays back');

    // Back to the sheet, then closing it brings the page under it forward again.
    Navigator.of(tester.element(find.text('section page'))).pop();
    await tester.pumpAndSettle();
    expect(scaleOf('taps 0'), closeTo(0.92, 0.001));
    Navigator.of(tester.element(find.text('sheet body'))).pop();
    await tester.pumpAndSettle();
    expect(scaleOf('taps 0'), 1);
  });

  testWidgets('Reduce Motion leaves the page where it is', (tester) async {
    await tester.pumpWidget(app(reduceMotion: true));
    await tester.tap(find.text('push'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('sheet body'), findsOneWidget);
    expect(pageScale(tester), 1);
    Navigator.of(tester.element(find.text('sheet body'))).pop();
    await tester.pumpAndSettle();
    expect(OmiSheetDepth.value.value, 0);
  });
}
