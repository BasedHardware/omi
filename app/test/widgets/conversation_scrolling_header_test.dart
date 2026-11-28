import 'package:flutter/material.dart';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversation_detail/widgets/conversation_scrolling_header.dart';

/// The conversation page's header scrolling with the open tab (experimental design).
void main() {
  late ConversationScrollingHeaderController controller;
  var headerTaps = 0;

  setUp(() {
    controller = ConversationScrollingHeaderController(2);
    headerTaps = 0;
  });
  tearDown(() => controller.dispose());

  Widget page(String name, {bool pinned = false}) => Builder(
        builder: (context) {
          final list = ListView.builder(
            key: PageStorageKey(name),
            itemCount: 60,
            itemBuilder: (context, index) => index == 0 && !pinned
                ? SizedBox(height: ConversationScrollingHeader.insetOf(context))
                : SizedBox(height: 50, child: Text('$name $index')),
          );
          return ConversationScrollingHeaderPinned(pinned: pinned, child: list);
        },
      );

  Future<void> pump(WidgetTester tester, {bool secondPinned = false}) async {
    await tester.pumpWidget(
      MaterialApp(
        home: DefaultTabController(
          length: 2,
          child: Builder(
            builder: (context) => Scaffold(
              body: ConversationScrollingHeader(
                controller: controller,
                tabAnimation: DefaultTabController.of(context).animation!,
                header: SizedBox(
                  key: const Key('header'),
                  height: 120,
                  child: Align(
                    alignment: Alignment.topLeft,
                    child: TextButton(onPressed: () => headerTaps++, child: const Text('Header button')),
                  ),
                ),
                body: TabBarView(
                  children: [
                    ConversationScrollingHeader.tab(controller, 0, page('a')),
                    ConversationScrollingHeader.tab(controller, 1, page('b', pinned: secondPinned)),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  double headerTop(WidgetTester tester) => tester.getTopLeft(find.byKey(const Key('header'))).dy;

  testWidgets('the first line starts under the header and both scroll away together', (tester) async {
    await pump(tester);
    expect(controller.height.value, 120);
    expect(headerTop(tester), 0);
    expect(tester.getTopLeft(find.text('a 1')).dy, 120);

    await tester.drag(find.text('a 5'), const Offset(0, -70));
    await tester.pump();
    // Part of the drag is spent on recognising it; what matters is that the two moved as one.
    expect(headerTop(tester), inInclusiveRange(-70, -40));
    expect(tester.getTopLeft(find.text('a 1')).dy, headerTop(tester) + 120);

    await tester.drag(find.text('a 8'), const Offset(0, -300));
    await tester.pump();
    // Gone, and no further than its own height.
    expect(headerTop(tester), -120);

    await tester.drag(find.text('a 12'), const Offset(0, 1000));
    await tester.pumpAndSettle();
    expect(headerTop(tester), 0);
  });

  testWidgets('a drag that starts on the header scrolls the page, and its button still taps', (tester) async {
    await pump(tester);
    await tester.dragFrom(const Offset(300, 60), const Offset(0, -40));
    await tester.pump();
    expect(headerTop(tester), lessThan(0));
    expect(tester.getTopLeft(find.text('a 1')).dy, headerTop(tester) + 120);

    await tester.tap(find.text('Header button'));
    expect(headerTaps, 1);
  });

  testWidgets('each tab keeps its own place; the header follows the open one', (tester) async {
    await pump(tester);
    await tester.drag(find.text('a 5'), const Offset(0, -300));
    await tester.pump();
    expect(headerTop(tester), -120);

    DefaultTabController.of(tester.element(find.byType(TabBarView))).animateTo(1);
    await tester.pumpAndSettle();
    expect(headerTop(tester), 0);
    expect(tester.getTopLeft(find.text('b 1')).dy, 120);

    DefaultTabController.of(tester.element(find.byType(TabBarView))).animateTo(0);
    await tester.pumpAndSettle();
    expect(headerTop(tester), -120);
  });

  testWidgets('a pinned tab leaves the header in place while its list scrolls under it', (tester) async {
    await pump(tester, secondPinned: true);
    DefaultTabController.of(tester.element(find.byType(TabBarView))).animateTo(1);
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('b 0')).dy, 120);

    await tester.drag(find.text('b 5'), const Offset(0, -200));
    await tester.pump();
    expect(headerTop(tester), 0);
    expect(find.text('b 0').hitTestable(), findsNothing);
  });
}
