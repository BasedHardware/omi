import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/widgets/grow_route.dart';

// The live transcript grows out of Home's record pill: it starts as the pill's shape, widens to
// the screen, runs back into the pill on close, and still leaves with the iOS edge swipe.
void main() {
  final pillKey = GlobalKey();
  const pillRect = Rect.fromLTWH(60, 700, 300, 56);

  Future<void> pump(WidgetTester tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Stack(children: [
            Positioned.fromRect(
              rect: pillRect,
              child: GestureDetector(
                key: pillKey,
                onTap: () => pushGrowingFrom<void>(
                  context,
                  from: pillKey,
                  page: const Scaffold(body: Center(child: Text('transcript'))),
                ),
                child: const ColoredBox(color: Colors.white),
              ),
            ),
          ]),
        ),
      ),
    ));
  }

  Rect clip(WidgetTester tester) {
    final render = tester.renderObject<RenderClipRRect>(
      find
          .ancestor(
              of: find.text('transcript', skipOffstage: false), matching: find.byType(ClipRRect, skipOffstage: false))
          .first,
    );
    return render.clipper!.getClip(render.size).outerRect;
  }

  testWidgets('opens from the pill, widens to the screen, and closes back into it', (tester) async {
    await pump(tester);
    await tester.tap(find.byKey(pillKey));
    await tester.pump();
    // The first frame is the offstage measuring pass; the transition starts on the next one.
    await tester.pump();
    expect(clip(tester), pillRect, reason: 'the first frame is the pill itself');

    await tester.pump(const Duration(milliseconds: 230));
    final mid = clip(tester);
    expect(mid.width, greaterThan(pillRect.width));
    expect(mid.height, greaterThan(pillRect.height));
    expect(mid.height, lessThan(800));

    await tester.pumpAndSettle();
    expect(find.text('transcript'), findsOneWidget);

    Navigator.of(tester.element(find.text('transcript'))).pop();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(clip(tester).height, lessThan(800), reason: 'it shrinks back toward the pill');
    await tester.pumpAndSettle();
    expect(find.text('transcript'), findsNothing);
  });

  testWidgets('the iOS edge swipe still closes it', (tester) async {
    await pump(tester);
    await tester.tap(find.byKey(pillKey));
    await tester.pumpAndSettle();

    final gesture = await tester.startGesture(const Offset(5, 400));
    await gesture.moveBy(const Offset(300, 0));
    await tester.pump();
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('transcript'), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
}
