import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/chat/widgets/chat_entrance.dart';
import 'package:omi/pages/chat/widgets/chat_starters.dart';
import 'package:omi/pages/chat/widgets/typing_indicator.dart';
import 'package:omi/ui/ui.dart';

Widget host(Widget child, {bool reduced = false, double scale = 1}) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: MediaQuery(
          data: MediaQueryData(
              size: const Size(320, 568), disableAnimations: reduced, textScaler: TextScaler.linear(scale)),
          child: Scaffold(body: child)),
    );

void main() {
  testWidgets('intro settles once and rebuilds retain the draft, focus and animation position', (tester) async {
    final controller = TextEditingController(text: 'my draft');
    final focus = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focus.dispose);
    Widget content() => ChatEntrance(child: ChatRise(child: TextField(controller: controller, focusNode: focus)));
    await tester.pumpWidget(host(content()));
    expect(tester.widget<Opacity>(find.byType(Opacity).first).opacity, 0);
    await tester.pump(const Duration(milliseconds: 1100));
    expect(tester.widget<Opacity>(find.byType(Opacity).first).opacity, 1);
    focus.requestFocus();
    await tester.pump();
    await tester.pumpWidget(host(content()));
    expect(controller.text, 'my draft');
    expect(focus.hasFocus, isTrue);
    expect(tester.widget<Opacity>(find.byType(Opacity).first).opacity, 1);
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('only an explicit new-chat revision replays the intro', (tester) async {
    Widget content(int revision) => ChatEntrance(revision: revision, child: const ChatRise(child: Text('Hello')));
    await tester.pumpWidget(host(content(0)));
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpWidget(host(content(1)));
    expect(tester.widget<Opacity>(find.byType(Opacity).first).opacity, 0);
    await tester.pumpAndSettle();
    expect(tester.widget<Opacity>(find.byType(Opacity).first).opacity, 1);
  });

  testWidgets('Reduce Motion from launch and mid-intro shows content without a running ticker', (tester) async {
    const content = ChatEntrance(child: ChatRise(child: Text('Hello')));
    await tester.pumpWidget(host(content, reduced: true));
    await tester.pumpAndSettle();
    expect(find.text('Hello'), findsOneWidget);
    expect(tester.binding.hasScheduledFrame, isFalse);
    await tester.pumpWidget(host(content));
    await tester.pump();
    expect(tester.widget<Opacity>(find.byType(Opacity).first).opacity, 1,
        reason: 'turning motion back on does not replay');
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(host(content));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpWidget(host(content, reduced: true));
    await tester.pumpAndSettle();
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('typing indicator stops when motion is disabled and resumes when enabled', (tester) async {
    await tester.pumpWidget(host(const TypingIndicator()));
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.binding.hasScheduledFrame, isTrue);
    await tester.pumpWidget(host(const TypingIndicator(), reduced: true));
    await tester.pumpAndSettle();
    final value = tester.widget<SlideTransition>(find.byType(SlideTransition).first).position.value;
    await tester.pump(const Duration(seconds: 1));
    expect(tester.widget<SlideTransition>(find.byType(SlideTransition).first).position.value, value);
    expect(tester.binding.hasScheduledFrame, isFalse);
    await tester.pumpWidget(host(const TypingIndicator()));
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.binding.hasScheduledFrame, isTrue);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('long greeting and suggestion chips fit small screens at 200% and remain editable', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    String? draft;
    await tester.pumpWidget(host(
        Column(children: [
          const Expanded(
              child:
                  ChatGreeting(isConnected: true, name: 'A long name with multiple words', hour: 10, todayCount: 12)),
          ChatSuggestions(hasExistingData: true, isConnected: true, onSelected: (value) => draft = value),
        ]),
        scale: 2,
        reduced: true));
    await tester.tap(find.byKey(const Key('chat_starter_decide')));
    expect(draft, 'What did I decide today?');
    expect(tester.takeException(), isNull);
    expect(tester.getSize(find.byKey(const Key('chat_starter_decide'))).height, greaterThanOrEqualTo(44));
  });

  testWidgets('popup and history Back return to the same parent without rebuilding its state', (tester) async {
    var visits = 0;
    final navigator = GlobalKey<NavigatorState>();
    await tester.pumpWidget(MaterialApp(
        navigatorKey: navigator,
        home: Builder(builder: (context) {
          visits++;
          return Scaffold(
              body: TextButton(
                  onPressed: () => Navigator.of(context).push(ChatSheetRoute(
                      builder: (context) => Scaffold(
                            appBar: AppBar(leading: const OmiCloseButton()),
                            body: TextButton(
                                child: const Text('History'),
                                onPressed: () => Navigator.of(context).push(omiPageRoute(
                                    builder: (_) => Scaffold(
                                        appBar: AppBar(leading: const OmiBackButton()), body: const Text('Past'))))),
                          ))),
                  child: const Text('Open')));
        })));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('History'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    expect(find.text('History'), findsOneWidget);
    await tester.tap(find.byType(OmiCloseButton));
    await tester.pumpAndSettle();
    expect(find.text('Open'), findsOneWidget);
    expect(navigator.currentState!.canPop(), isFalse);
    expect(visits, 1);
  });
}
