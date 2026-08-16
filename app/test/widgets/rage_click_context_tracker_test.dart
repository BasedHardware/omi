import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/analytics/rage_click_context_tracker.dart';

void main() {
  testWidgets('captures the Flutter route and tapped control for native rage clicks', (tester) async {
    RageClickContext? captured;

    await tester.pumpWidget(
      RageClickContextTracker(
        onContext: ({screenName, required target}) {
          captured = RageClickContext(screenName: screenName, target: target);
        },
        child: MaterialApp(
          home: Scaffold(
            appBar: AppBar(title: const Text('Settings')),
            body: Center(
              child: ElevatedButton(onPressed: () {}, child: const Text('Retry sync')),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Retry sync'));

    expect(captured?.screenName, 'Settings');
    expect(captured?.target, 'Retry sync');
  });

  testWidgets('falls back safely when a tapped surface has no semantic label', (tester) async {
    RageClickContext? captured;

    await tester.pumpWidget(
      RageClickContextTracker(
        onContext: ({screenName, required target}) {
          captured = RageClickContext(screenName: screenName, target: target);
        },
        child: MaterialApp(
          home: Scaffold(
            body: GestureDetector(onTap: () {}, child: const SizedBox.expand()),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tapAt(const Offset(20, 20));

    expect(captured, isNotNull);
    expect(captured!.target, anyOf('tap_target', 'unlabeled_surface'));
  });
}
