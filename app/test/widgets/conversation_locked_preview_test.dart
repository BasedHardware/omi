import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

const _title = 'Planning the next team meeting';
const _upgrade = 'Upgrade to Unlimited';

class _Routes extends NavigatorObserver {
  final pushed = <Route<dynamic>>[];

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) => pushed.add(route);
}

void main() {
  late ConversationProvider conversations;
  late UsageProvider usage;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    conversations = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    usage = UsageProvider();
  });

  tearDown(() {
    conversations.dispose();
    usage.dispose();
    OmiColors.active = OmiPalette.light;
  });

  Future<void> pumpRow(
    WidgetTester tester, {
    bool locked = true,
    Brightness brightness = Brightness.light,
    double textScale = 1,
    NavigatorObserver? observer,
  }) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    OmiColors.active = OmiColors.forBrightness(brightness);
    final conversation = ServerConversation(
      id: 'locked-preview',
      createdAt: DateTime.utc(2020, 1, 1, 12),
      startedAt: DateTime.utc(2020, 1, 1, 12),
      finishedAt: DateTime.utc(2020, 1, 1, 12, 3),
      structured: Structured(_title, 'Overview', emoji: '📝'),
      isLocked: locked,
    );
    conversations.conversations = [conversation];
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ],
        child: MaterialApp(
          theme: buildOmiTheme(brightness: brightness),
          navigatorObservers: [if (observer != null) observer],
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: child!,
          ),
          home: Scaffold(
            body: ListView(children: [
              ConversationListItem(conversation: conversation, date: conversation.createdAt, conversationIdx: 0),
            ]),
          ),
        ),
      ),
    );
  }

  for (final brightness in Brightness.values) {
    for (final textScale in [1.0, 2.0]) {
      testWidgets('locked preview is obscured with a legible action at $brightness / $textScale', (tester) async {
        final semantics = tester.ensureSemantics();
        addTearDown(semantics.dispose);
        await pumpRow(tester, brightness: brightness, textScale: textScale);

        // The reported bug left the title sharp beneath the upgrade text. The blur must
        // contain all row content, while the upgrade action stays outside that layer.
        expect(find.descendant(of: find.byType(ImageFiltered), matching: find.text(_title)), findsOneWidget);
        expect(find.descendant(of: find.byType(ImageFiltered), matching: find.text(_upgrade)), findsNothing);
        expect(find.byType(BackdropFilter), findsNothing);
        expect(find.bySemanticsLabel(_title), findsNothing);
        expect(find.bySemanticsLabel(_upgrade), findsOneWidget);

        final button = find.byKey(const Key('locked_preview_action'));
        final previewRect = tester.getRect(find.byType(OmiLockedPreview));
        final buttonRect = tester.getRect(button);
        expect(previewRect.contains(buttonRect.topLeft), isTrue);
        expect(previewRect.contains(buttonRect.bottomRight), isTrue);
        expect(buttonRect.height, greaterThanOrEqualTo(44));
        final text = tester.widget<Text>(find.text(_upgrade));
        final control = tester.widget<TextButton>(find.descendant(of: button, matching: find.byType(TextButton)));
        final foreground = text.style!.color!.computeLuminance();
        final background = control.style!.backgroundColor!.resolve({})!.computeLuminance();
        final contrast = foreground > background
            ? (foreground + 0.05) / (background + 0.05)
            : (background + 0.05) / (foreground + 0.05);
        expect(contrast, greaterThanOrEqualTo(4.5));
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('an unlocked row stays readable and has no upgrade treatment', (tester) async {
    final semantics = tester.ensureSemantics();
    addTearDown(semantics.dispose);
    await pumpRow(tester, locked: false);
    expect(find.byType(ImageFiltered), findsNothing);
    expect(find.byType(OmiLockedPreview), findsNothing);
    expect(find.bySemanticsLabel(_title), findsOneWidget);
    expect(find.text(_upgrade), findsNothing);
  });

  testWidgets('the upgrade action keeps the existing paywall destination', (tester) async {
    final routes = _Routes();
    await pumpRow(tester, observer: routes);
    await tester.tap(find.byKey(const Key('locked_preview_action')));
    expect(routes.pushed, hasLength(2));
    final route = routes.pushed.last as MaterialPageRoute;
    final destination = route.builder(tester.element(find.byType(ConversationListItem)));
    expect(destination, isA<UsagePage>());
    expect((destination as UsagePage).showUpgradeDialog, isTrue);
    // Check navigation without building the network-backed usage screen.
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('the upgrade action respects the row selection mode', (tester) async {
    final routes = _Routes();
    await pumpRow(tester, observer: routes);
    conversations.enterSelectionMode();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('locked_preview_action')));
    await tester.pump();
    expect(routes.pushed, hasLength(1));
    expect(conversations.selectedConversationIds, isEmpty);
    expect(tester.takeException(), isNull);
  });
}
