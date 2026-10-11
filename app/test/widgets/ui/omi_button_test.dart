import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/ui.dart';

import 'ui_test_app.dart';

void main() {
  Finder spinner() => find.byType(CircularProgressIndicator);

  testWidgets('shows a spinner while onPressed runs and clears it when it completes', (tester) async {
    final gate = Completer<void>();
    var calls = 0;
    await pumpUi(
      tester,
      Scaffold(
        body: Center(
          child: OmiButton(
            label: 'Save',
            onPressed: () {
              calls++;
              return gate.future;
            },
          ),
        ),
      ),
    );
    await tester.tap(find.byType(OmiButton));
    await tester.pump();
    expect(spinner(), findsOneWidget);

    await tester.tap(find.byType(OmiButton));
    await tester.pump();
    expect(calls, 1, reason: 'taps while loading are ignored');

    gate.complete();
    await tester.pump();
    expect(spinner(), findsNothing);
  });

  testWidgets('clears the spinner and reports the error when onPressed throws', (tester) async {
    var calls = 0;
    await pumpUi(
      tester,
      Scaffold(
        body: Center(
          child: OmiButton.secondary(
            label: 'Retry',
            onPressed: () async {
              calls++;
              await Future<void>.delayed(const Duration(milliseconds: 10));
              throw StateError('network down');
            },
          ),
        ),
      ),
    );
    await tester.tap(find.byType(OmiButton));
    await tester.pump();
    expect(spinner(), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 20));
    expect(tester.takeException(), isA<StateError>());
    expect(spinner(), findsNothing, reason: 'a failed action must not leave the button spinning forever');

    await tester.tap(find.byType(OmiButton));
    await tester.pump();
    expect(calls, 2, reason: 'the button is usable again after a failure');
    await tester.pump(const Duration(milliseconds: 20));
    tester.takeException();
  });

  testWidgets('keeps the label in the semantics tree while loading and is disabled without onPressed', (tester) async {
    await pumpUi(
      tester,
      const Scaffold(
        body: Column(
          children: [
            OmiButton(label: 'Connect', onPressed: null),
            OmiButton(label: 'Saving', onPressed: _noop, isLoading: true),
          ],
        ),
      ),
    );
    final disabled =
        tester.widget<TextButton>(find.descendant(of: find.byType(OmiButton).first, matching: find.byType(TextButton)));
    expect(disabled.onPressed, isNull);
    expect(find.bySemanticsLabel('Saving'), findsOneWidget);
    expect(spinner(), findsOneWidget);
  });

  testWidgets('regular is 48pt tall and compact keeps a >=44pt target around its 36pt visual', (tester) async {
    await pumpUi(
      tester,
      const Scaffold(
        body: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            OmiButton(label: 'Primary', onPressed: _noop),
            OmiButton.tertiary(label: 'Compact', onPressed: _noop, size: OmiButtonSize.compact),
          ],
        ),
      ),
    );
    expect(tester.getSize(find.byType(OmiButton).first).height, 48);
    expect(tester.getSize(find.byType(OmiButton).last).height, greaterThanOrEqualTo(44));
  });

  testWidgets('an async action that throws clears the spinner (the old loading button spun forever)', (tester) async {
    await pumpUi(
      tester,
      Scaffold(
        body: Center(
          child: OmiButton(
            label: 'Connect',
            onPressed: () async {
              await Future<void>.delayed(const Duration(milliseconds: 10));
              throw Exception('stripe unavailable');
            },
          ),
        ),
      ),
    );
    await tester.tap(find.byType(OmiButton));
    await tester.pump();
    expect(spinner(), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 20));
    expect(tester.takeException(), isException);
    expect(spinner(), findsNothing);
  });
}

void _noop() {}
