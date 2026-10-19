import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Fixed "today" so dated copy is stable: Monday, Oct 19, 2026.
final DateTime testToday = DateTime(2026, 10, 19);

void setSize(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// Pumps ~1.2 s of frames (long enough for Android's 800 ms page transition);
/// screens with looping animations never "settle".
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 8; i++) {
    await tester.pump(const Duration(milliseconds: 150));
  }
}

Future<void> tapFinder(WidgetTester tester, Finder finder, {String? what}) async {
  expect(finder, findsOneWidget, reason: 'expected exactly one ${what ?? finder} on screen');
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.tap(finder);
  await settle(tester);
}

Future<void> tapText(WidgetTester tester, String text) => tapFinder(tester, find.text(text), what: '"$text"');

Future<void> tapTooltip(WidgetTester tester, String tooltip) =>
    tapFinder(tester, find.byTooltip(tooltip).hitTestable(), what: 'tooltip "$tooltip"');

/// Scrolls the main (first) list until [finder] is built and on screen.
Future<void> scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).first);
  await settle(tester);
}
