import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/ui.dart';

import 'ui_test_app.dart';

void main() {
  Widget pushedPage(Widget leading) => Scaffold(appBar: AppBar(leading: leading, title: const Text('Detail')));

  testWidgets('OmiBackButton is a labelled 44pt target that pops the page', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpUi(tester, PushHost(page: pushedPage(const OmiBackButton())));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Detail'), findsOneWidget);

    final target = tester.getSize(find.byType(OmiIconButton));
    expect(target.width, greaterThanOrEqualTo(44));
    expect(target.height, greaterThanOrEqualTo(44));

    final data = tester.getSemantics(find.bySemanticsLabel('Back')).getSemanticsData();
    expect(data.flagsCollection.isButton, isTrue);
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    expect(find.byTooltip('Back'), findsOneWidget);

    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    expect(find.text('Detail'), findsNothing);
    expect(find.text('open'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('OmiBackButton uses the platform back glyph', (tester) async {
    await pumpUi(tester, pushedPage(const OmiBackButton()), platform: TargetPlatform.iOS);
    expect(find.byIcon(Icons.arrow_back_ios_new_rounded), findsOneWidget);

    await pumpUi(tester, pushedPage(const OmiBackButton()), platform: TargetPlatform.android);
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.arrow_back), findsOneWidget);
  });

  testWidgets('OmiBackButton.circled paints a circle inside the same 44pt target and honours onPressed',
      (tester) async {
    var pressed = 0;
    // In a floating header the control sits in plain layout, not an AppBar slot.
    await pumpUi(tester, Scaffold(body: Center(child: OmiBackButton.circled(onPressed: () => pressed++))));
    final target = tester.getRect(find.byType(OmiIconButton));
    expect(target.size, const Size(44, 44));
    final circle = tester.getRect(find.descendant(of: find.byType(OmiIconButton), matching: find.byType(Container)));
    expect(circle.size, const Size(kOmiIconCircleDiameter, kOmiIconCircleDiameter));
    expect(circle.center, target.center);

    await tester.tapAt(target.topLeft + const Offset(2, 2));
    expect(pressed, 1, reason: 'the corner of the target, outside the circle, still counts');
  });

  testWidgets('OmiCloseButton is labelled Close and dismisses the route', (tester) async {
    await pumpUi(
      tester,
      PushHost(page: Scaffold(appBar: AppBar(title: const Text('Viewer'), actions: const [OmiCloseButton()]))),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Close'), findsOneWidget);
    expect(find.byIcon(Icons.close), findsOneWidget);
    expect(tester.getSize(find.byType(OmiIconButton)).height, greaterThanOrEqualTo(44));

    await tester.tap(find.byType(OmiCloseButton));
    await tester.pumpAndSettle();
    expect(find.text('Viewer'), findsNothing);
  });
}
