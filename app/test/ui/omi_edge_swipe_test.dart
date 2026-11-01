import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/search/global_search.dart';

Future<void> _pushChat(WidgetTester tester, {String tag = 'chat-page', bool disableAnimations = false}) async {
  await tester.pumpWidget(MediaQuery(
    data: MediaQueryData.fromView(tester.view).copyWith(disableAnimations: disableAnimations),
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: ThemeData(platform: TargetPlatform.iOS),
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: TextButton(
              onPressed: () =>
                  Navigator.of(context).push(ChatSheetRoute<void>(builder: (_) => Scaffold(body: Text(tag)))),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  expect(find.text(tag), findsOneWidget);
}

Future<void> _pushSearch(WidgetTester tester) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: ThemeData(platform: TargetPlatform.iOS),
    home: Builder(
      builder: (context) => Scaffold(
        body: Center(
          child: TextButton(
            onPressed: () =>
                Navigator.of(context).push(SearchDropRoute<void>(builder: (_) => const Text('search-page'))),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  expect(find.text('search-page'), findsOneWidget);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a left-edge drag past a third of the width pops a ChatSheetRoute', (tester) async {
    await _pushChat(tester);
    final gesture = await tester.startGesture(const Offset(2, 400));
    for (var i = 0; i < 8; i++) {
      await gesture.moveBy(const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(find.text('chat-page'), findsOneWidget);
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsNothing, reason: 'a decisive edge swipe dismisses the sheet');
    expect(find.text('open'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a left-edge drag past a third of the width pops a SearchDropRoute', (tester) async {
    await _pushSearch(tester);
    final gesture = await tester.startGesture(const Offset(2, 400));
    for (var i = 0; i < 8; i++) {
      await gesture.moveBy(const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('search-page'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the page tracks the finger horizontally before the gesture settles', (tester) async {
    await _pushChat(tester);
    final before = tester.getTopLeft(find.text('chat-page'));
    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(200, 0));
    await tester.pump();
    final during = tester.getTopLeft(find.text('chat-page'));
    await gesture.up();
    await tester.pumpAndSettle();
    expect(during.dx, greaterThan(before.dx), reason: 'the sheet follows the finger to the right');
  });

  testWidgets('a short edge drag cancels back onto the screen', (tester) async {
    await _pushChat(tester);
    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(60, 0));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsOneWidget, reason: 'a short drag springs back instead of popping');
    expect(tester.getTopLeft(find.text('chat-page')).dx, 0,
        reason: 'the cancelled swipe restores the sheet to the left edge');
    expect(Navigator.of(tester.element(find.text('open'))).userGestureInProgress, isFalse,
        reason: 'a cancelled swipe releases the navigator gesture');
  });

  testWidgets('a cancelled edge drag on a SearchDropRoute also releases the gesture', (tester) async {
    await _pushSearch(tester);
    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(60, 0));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('search-page'), findsOneWidget);
    expect(Navigator.of(tester.element(find.text('open'))).userGestureInProgress, isFalse);
  });

  testWidgets('reduced motion still tracks the finger and pops a ChatSheetRoute', (tester) async {
    await _pushChat(tester, disableAnimations: true);
    final before = tester.getTopLeft(find.text('chat-page'));
    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(200, 0));
    await tester.pump();
    expect(tester.getTopLeft(find.text('chat-page')).dx, greaterThan(before.dx),
        reason: 'reduced motion must not freeze the edge swipe');
    await gesture.moveBy(const Offset(200, 0));
    await tester.pump();
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsNothing);
    expect(Navigator.of(tester.element(find.text('open'))).userGestureInProgress, isFalse);
  });

  testWidgets('reduced motion still pops a SearchDropRoute', (tester) async {
    await tester.pumpWidget(MediaQuery(
      data: MediaQueryData.fromView(tester.view).copyWith(disableAnimations: true),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData(platform: TargetPlatform.iOS),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () =>
                    Navigator.of(context).push(SearchDropRoute<void>(builder: (_) => const Text('search-page'))),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(400, 0));
    await tester.pump();
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('search-page'), findsNothing);
    expect(Navigator.of(tester.element(find.text('open'))).userGestureInProgress, isFalse);
  });

  testWidgets('disposing mid-gesture does not double-stop the navigator gesture', (tester) async {
    await _pushChat(tester);
    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(100, 0));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    await gesture.up();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('a fast short fling still dismisses', (tester) async {
    await _pushChat(tester);
    await tester.flingFrom(const Offset(2, 400), const Offset(120, 0), 1200);
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsNothing, reason: 'velocity over 900 past 32pt dismisses');
  });

  testWidgets('a centre drag never pops', (tester) async {
    await _pushChat(tester);
    final gesture = await tester.startGesture(const Offset(400, 400));
    for (var i = 0; i < 8; i++) {
      await gesture.moveBy(const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsOneWidget);
  });

  testWidgets('a right-edge drag never pops', (tester) async {
    await _pushChat(tester);
    final width = tester.getSize(find.byType(MaterialApp)).width;
    final gesture = await tester.startGesture(Offset(width - 2, 400));
    for (var i = 0; i < 8; i++) {
      await gesture.moveBy(const Offset(-40, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsOneWidget);
  });

  testWidgets('Android gets no edge swipe', (tester) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: ThemeData(platform: TargetPlatform.android),
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: TextButton(
              onPressed: () =>
                  Navigator.of(context).push(ChatSheetRoute<void>(builder: (_) => const Text('chat-page'))),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    final gesture = await tester.startGesture(const Offset(2, 400));
    for (var i = 0; i < 8; i++) {
      await gesture.moveBy(const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsOneWidget, reason: 'the strip is iOS-only');
  });

  testWidgets('a PopScope that blocks the pop also blocks the swipe', (tester) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: ThemeData(platform: TargetPlatform.iOS),
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: TextButton(
              onPressed: () => Navigator.of(context).push(
                  ChatSheetRoute<void>(builder: (_) => const PopScope(canPop: false, child: Text('locked-page')))),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    final gesture = await tester.startGesture(const Offset(2, 400));
    for (var i = 0; i < 8; i++) {
      await gesture.moveBy(const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('locked-page'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a child route on top swallows the gesture; the sheet below stays put', (tester) async {
    await _pushChat(tester, tag: 'parent-page');
    final context = tester.element(find.text('parent-page'));
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const Text('child-page')));
    await tester.pumpAndSettle();
    expect(find.text('child-page'), findsOneWidget);

    final parent = find.text('parent-page', skipOffstage: false);
    final before = tester.getTopLeft(parent);
    final gesture = await tester.startGesture(const Offset(2, 400));
    await gesture.moveBy(const Offset(80, 0));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.text('child-page'), findsOneWidget);
    expect(tester.getTopLeft(parent), before);
  });

  testWidgets('the navigator is clean and reusable after an edge-swipe pop', (tester) async {
    await _pushChat(tester);
    await tester.flingFrom(const Offset(2, 400), const Offset(300, 0), 1200);
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsNothing);
    expect(find.text('open'), findsOneWidget);

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('chat-page'), findsOneWidget, reason: 'the same navigator pushes again after cleanup');
    expect(tester.takeException(), isNull);
  });
}
