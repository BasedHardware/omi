import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'b1_route_dismissal.dart';

class _NeverCompletedSheet extends ModalBottomSheetRoute<void> {
  _NeverCompletedSheet() : super(builder: (_) => const Text('sheet'), isScrollControlled: true);

  @override
  Future<void> get completed => Completer<void>().future;
}

void main() {
  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    for (final reverse in [const Duration(milliseconds: 200), const Duration(milliseconds: 1500)]) {
      testWidgets('B1 dismissal waits for route disposal on $platform, reverse=$reverse', (tester) async {
        final key = GlobalKey<NavigatorState>();
        await tester.pumpWidget(MaterialApp(
          navigatorKey: key,
          theme: ThemeData(platform: platform),
          home: const Scaffold(body: CircularProgressIndicator()),
        ));
        final route = ModalBottomSheetRoute<void>(
          builder: (_) => const Text('sheet'),
          isScrollControlled: true,
          sheetAnimationStyle: AnimationStyle(reverseDuration: reverse),
        );
        unawaited(key.currentState!.push(route));
        await tester.pump();
        await tester.pump(route.transitionDuration);
        final page = find.text('sheet').evaluate().single;
        await expectRouteDismissed(tester, route, page, () async {
          key.currentState!.pop();
          // Reproduce the old oracle: wall-clock advance before the first tick
          // still leaves the sheet onstage, despite a successful logical pop.
          await tester.pump(const Duration(seconds: 1));
          expect(route.isActive, isFalse);
          expect(route.animation!.status, AnimationStatus.reverse);
          expect(route.animation!.value, 1);
          expect(find.text('sheet'), findsOneWidget);
        });
        expect(find.text('sheet', skipOffstage: false), findsNothing);
        expect(tester.binding.hasScheduledFrame, isTrue, reason: 'unrelated animation must not block dismissal');
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
    testWidgets('B1 dismissal rejects a no-op control on $platform', (tester) async {
      final key = GlobalKey<NavigatorState>();
      await tester.pumpWidget(MaterialApp(navigatorKey: key, theme: ThemeData(platform: platform), home: Container()));
      final route = ModalBottomSheetRoute<void>(builder: (_) => const Text('sheet'), isScrollControlled: true);
      unawaited(key.currentState!.push(route));
      await tester.pump();
      await tester.pump(route.transitionDuration);
      final page = find.text('sheet').evaluate().single;
      await expectLater(expectRouteDismissed(tester, route, page, () {}), throwsA(isA<TestFailure>()));
      expect(route.isActive, isTrue);
      await tester.pumpWidget(const SizedBox.shrink());
    });
    testWidgets('B1 dismissal rejects absent page without route completion on $platform', (tester) async {
      final key = GlobalKey<NavigatorState>();
      await tester.pumpWidget(MaterialApp(navigatorKey: key, theme: ThemeData(platform: platform), home: Container()));
      final route = _NeverCompletedSheet();
      unawaited(key.currentState!.push(route));
      await tester.pump();
      await tester.pump(route.transitionDuration);
      final page = find.text('sheet').evaluate().single;
      await expectLater(
        expectRouteDismissed(tester, route, page, () => key.currentState!.pop()),
        throwsA(isA<TestFailure>()),
      );
      expect(page.mounted, isFalse);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
