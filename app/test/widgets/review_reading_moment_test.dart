import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/widgets/review_reading_moment.dart';

void main() {
  const readingDuration = Duration(milliseconds: 100);
  const bottomIdleDuration = Duration(milliseconds: 20);

  Future<void> pumpMoment(
    WidgetTester tester, {
    required Widget child,
    required Future<void> Function(ReadingMomentValidator) onFinishedReading,
    VoidCallback? onEngaged,
    bool enabled = true,
    String contentId = 'content-a',
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReviewReadingMoment(
            contentId: contentId,
            enabled: enabled,
            minimumReadingDuration: readingDuration,
            bottomIdleDuration: bottomIdleDuration,
            onFinishedReading: onFinishedReading,
            onEngaged: onEngaged,
            child: SizedBox(height: 300, child: child),
          ),
        ),
      ),
    );
    // The first frame lays out the scrollable and delivers its metrics.
    await tester.pump();
  }

  Widget shortList({Key? key}) {
    return ListView(
      key: key,
      children: const [SizedBox(height: 80, child: Text('Summary'))],
    );
  }

  Widget longList({Key? key, ScrollController? controller}) {
    return ListView.builder(
      key: key,
      controller: controller,
      itemCount: 30,
      itemBuilder: (context, index) => SizedBox(height: 80, child: Text('Row $index')),
    );
  }

  testWidgets('waits for a timed read and bottom idle on short content', (tester) async {
    var requests = 0;
    ReadingMomentValidator? validator;
    var engagements = 0;

    await pumpMoment(
      tester,
      child: shortList(),
      onEngaged: () => engagements++,
      onFinishedReading: (candidate) async {
        requests++;
        validator = candidate;
      },
    );

    expect(engagements, 1);
    await tester.pump(const Duration(milliseconds: 99));
    expect(requests, 0);
    await tester.pump(const Duration(milliseconds: 1));

    expect(requests, 1);
    expect(validator?.call(), isTrue);
  });

  testWidgets('does not finish while a long document is mid-scroll', (tester) async {
    final controller = ScrollController();
    addTearDown(controller.dispose);
    var requests = 0;

    await pumpMoment(
      tester,
      child: longList(controller: controller),
      onFinishedReading: (_) async => requests++,
    );
    await tester.drag(find.byType(ListView), const Offset(0, -180));
    await tester.pump(readingDuration + const Duration(milliseconds: 30));

    expect(controller.offset, greaterThan(0));
    expect(requests, 0);
  });

  testWidgets('a programmatic jump to the end does not count as reading engagement', (tester) async {
    final controller = ScrollController();
    addTearDown(controller.dispose);
    var requests = 0;

    await pumpMoment(
      tester,
      child: longList(controller: controller),
      onFinishedReading: (_) async => requests++,
    );
    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pump(const Duration(milliseconds: 150));

    expect(requests, 0);
  });

  testWidgets('a real drag to the end arms the idle gate', (tester) async {
    var requests = 0;

    await pumpMoment(
      tester,
      child: longList(),
      onFinishedReading: (_) async => requests++,
    );
    await tester.pump(readingDuration);
    await tester.drag(find.byType(ListView), const Offset(0, -3000));
    await tester.pump();

    expect(requests, 0);
    await tester.pump(bottomIdleDuration - const Duration(milliseconds: 1));
    expect(requests, 0);
    await tester.pump(const Duration(milliseconds: 1));
    expect(requests, 1);
  });

  testWidgets('background time is excluded and the validator is invalidated', (tester) async {
    ReadingMomentValidator? validator;
    var requests = 0;

    await pumpMoment(
      tester,
      child: shortList(),
      onFinishedReading: (candidate) async {
        requests++;
        validator = candidate;
      },
    );
    await tester.pump(const Duration(milliseconds: 50));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump(const Duration(milliseconds: 300));
    expect(requests, 0);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump(const Duration(milliseconds: 49));
    expect(requests, 0);
    await tester.pump(const Duration(milliseconds: 1));
    expect(requests, 1);
    expect(validator?.call(), isTrue);
  });

  testWidgets('a pushed reading route records engagement once after its transition', (tester) async {
    final navigator = GlobalKey<NavigatorState>();
    var engagements = 0;
    var requests = 0;
    await tester.pumpWidget(MaterialApp(navigatorKey: navigator, home: const Scaffold()));
    navigator.currentState!.push<void>(MaterialPageRoute<void>(
        builder: (_) => Scaffold(
              body: ReviewReadingMoment(
                contentId: 'pushed-content',
                enabled: true,
                minimumReadingDuration: const Duration(seconds: 1),
                bottomIdleDuration: bottomIdleDuration,
                onEngaged: () => engagements++,
                onFinishedReading: (_) async => requests++,
                child: shortList(),
              ),
            )));
    await tester.pump();
    expect(engagements, 0);
    await tester.pumpAndSettle();
    expect(engagements, 1);
    expect(requests, 0);
    await tester.pump(const Duration(seconds: 1));
    expect(requests, 1);
    expect(engagements, 1);
  });

  testWidgets('a covered route pauses dwell and hidden time cannot complete it', (tester) async {
    var requests = 0;
    final navigatorKey = GlobalKey<NavigatorState>();

    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        home: Scaffold(
          body: ReviewReadingMoment(
            contentId: 'content-a',
            enabled: true,
            minimumReadingDuration: readingDuration,
            bottomIdleDuration: bottomIdleDuration,
            onFinishedReading: (_) async => requests++,
            child: shortList(),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    navigatorKey.currentState!.push<void>(MaterialPageRoute<void>(builder: (_) => const SizedBox()));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 300));
    expect(requests, 0);

    navigatorKey.currentState!.pop();
    await tester.pump();
    expect(requests, 0);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 100));
    expect(requests, 1);
  });

  testWidgets('disabled tab state resets the dwell attempt', (tester) async {
    var enabled = true;
    var requests = 0;

    await tester.pumpWidget(
      StatefulBuilder(
        builder: (context, setState) {
          return MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  ElevatedButton(onPressed: () => setState(() => enabled = false), child: const Text('switch')),
                  Expanded(
                    child: ReviewReadingMoment(
                      contentId: 'content-a',
                      enabled: enabled,
                      minimumReadingDuration: readingDuration,
                      bottomIdleDuration: bottomIdleDuration,
                      onFinishedReading: (_) async => requests++,
                      child: shortList(),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('switch'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(requests, 0);
  });

  testWidgets('content replacement cancels the previous attempt', (tester) async {
    final contentId = ValueNotifier('content-a');
    addTearDown(contentId.dispose);
    var requests = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ValueListenableBuilder<String>(
            valueListenable: contentId,
            builder: (context, id, _) {
              return ReviewReadingMoment(
                contentId: id,
                enabled: true,
                minimumReadingDuration: readingDuration,
                bottomIdleDuration: bottomIdleDuration,
                onFinishedReading: (_) async => requests++,
                child: shortList(key: ValueKey(id)),
              );
            },
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    contentId.value = 'content-b';
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));
    expect(requests, 0);
    await tester.pump(const Duration(milliseconds: 40));
    expect(requests, 1);
  });

  testWidgets('keyboard visibility blocks and then restarts the opportunity', (tester) async {
    var requests = 0;

    await pumpMoment(
      tester,
      child: shortList(),
      onFinishedReading: (_) async => requests++,
    );
    await tester.pump(const Duration(milliseconds: 50));
    tester.view.viewInsets = const FakeViewPadding(bottom: 220);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(requests, 0);

    tester.view.viewInsets = FakeViewPadding.zero;
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 49));
    expect(requests, 0);
    await tester.pump(const Duration(milliseconds: 1));
    expect(requests, 1);
  });

  testWidgets('disposing the surface cancels timers without a late request', (tester) async {
    var requests = 0;

    await pumpMoment(
      tester,
      child: shortList(),
      onFinishedReading: (_) async => requests++,
    );
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(milliseconds: 300));

    expect(requests, 0);
  });
}
