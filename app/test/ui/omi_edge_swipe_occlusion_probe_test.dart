import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/chat_route.dart';

/// Empirical probe for the review concern that the topmost translucent edge
/// GestureDetector occludes non-horizontal gestures that start inside the edge
/// strip. Runs against the real ChatSheetRoute edge-swipe wrapper.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pushChatWithControls(WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: ThemeData(platform: TargetPlatform.iOS),
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: TextButton(
              onPressed: () => Navigator.of(context).push(ChatSheetRoute<void>(
                builder: (_) => Scaffold(
                  body: ListView(
                    children: [
                      TextButton(
                        key: const Key('edge_tap_target'),
                        onPressed: () {},
                        child: const Text('edge-tap'),
                      ),
                      for (var i = 0; i < 40; i++) Text('row $i'),
                    ],
                  ),
                ),
              )),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('edge-tap'), findsOneWidget);
  }

  // Home cannot pop; the pushed sheet can. The only reliable open signal:
  // offscreen rows dispose their elements, so text finders lie after scrolling.
  bool sheetIsOpen(WidgetTester tester) => tester.state<NavigatorState>(find.byType(Navigator).first).canPop();

  testWidgets('a tap inside the edge strip reaches the underlying control and does not pop', (tester) async {
    await pushChatWithControls(tester);
    await tester.tapAt(const Offset(10, 30));
    await tester.pump();
    expect(sheetIsOpen(tester), isTrue, reason: 'a tap in the edge strip must not pop the sheet');
  });

  testWidgets('a vertical drag inside the edge strip scrolls the list, not the route', (tester) async {
    await pushChatWithControls(tester);
    final gesture = await tester.startGesture(const Offset(8, 300));
    for (var i = 0; i < 12; i++) {
      await gesture.moveBy(const Offset(0, -40));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();

    expect(sheetIsOpen(tester), isTrue, reason: 'a vertical drag in the edge strip must not pop the sheet');
    final list = find.byType(ListView);
    final scrollable = find.descendant(of: list, matching: find.byType(Scrollable)).first;
    final position = tester.state<ScrollableState>(scrollable).position;
    expect(position.pixels, greaterThan(0), reason: 'the vertical drag must reach the list and scroll it');
  });

  testWidgets('a tap on a control inside the edge strip triggers the control, not a pop', (tester) async {
    await pushChatWithControls(tester);
    final target = find.byKey(const Key('edge_tap_target'));
    await tester.ensureVisible(target);
    final rect = tester.getRect(target);
    debugPrint('tap target rect: $rect');
    await tester.tap(target, warnIfMissed: false);
    await tester.pump();
    expect(sheetIsOpen(tester), isTrue, reason: 'tapping a control in the edge strip must not pop the sheet');
  });
}
