import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/activity/needs_attention_section.dart';
import 'package:omi/pages/home/widgets/home_tab_switcher.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';

/// The largest iOS accessibility text size (AX5) on an iPhone 17 Pro.
const _maxText = TextScaler.linear(3.1);
const _phone = Size(402, 874);

void _usePhone(WidgetTester tester) {
  tester.view.physicalSize = _phone;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Widget _app(Widget home, {List<ChangeNotifierProvider> providers = const []}) {
  final app = MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: const [Locale('en')],
    builder: (context, child) => MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: _maxText), child: child!),
    home: home,
  );
  return providers.isEmpty ? app : MultiProvider(providers: providers, child: app);
}

void _expectOnScreen(WidgetTester tester, Finder finder) {
  final rect = tester.getRect(finder);
  expect(rect.top, greaterThanOrEqualTo(0), reason: '$finder starts above the screen');
  expect(rect.bottom, lessThanOrEqualTo(_phone.height), reason: '$finder ends below the screen');
}

class _StoreAuth extends AuthenticationProvider {
  _StoreAuth() : super(initializeListeners: false);

  @override
  bool get isLocalDevProfile => false;
}

AttentionItem _item(String id) => AttentionItem(
      id: id,
      kind: 'conversation_summary_failed',
      conversationId: 'c-$id',
      retryable: true,
      seen: false,
      retryState: AttentionRetryState.none,
    );

void main() {
  testWidgets('sign-in: the sign-in button is on screen without scrolling', (tester) async {
    _usePhone(tester);
    final auth = _StoreAuth();
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(
      Scaffold(body: AuthComponent(onSignIn: () {})),
      providers: [ChangeNotifierProvider<AuthenticationProvider>.value(value: auth)],
    ));
    await tester.pump();
    expect(tester.takeException(), isNull);
    _expectOnScreen(tester, find.widgetWithText(ElevatedButton, 'Sign in with Google'));
  });

  testWidgets('consent: both button labels wrap instead of cutting off, on screen', (tester) async {
    _usePhone(tester);
    final auth = AuthenticationProvider(initializeListeners: false);
    addTearDown(auth.dispose);
    await tester.pumpWidget(_app(
      Scaffold(body: AiConsentWidget(onAgree: () {}, onUseDifferentAccount: () {})),
      providers: [ChangeNotifierProvider<AuthenticationProvider>.value(value: auth)],
    ));
    await tester.pump();
    expect(tester.takeException(), isNull);
    for (final label in ['Agree & Continue', 'Use a Different Account']) {
      final paragraph = tester.renderObject<RenderParagraph>(find.text(label));
      expect(paragraph.didExceedMaxLines, isFalse, reason: '"$label" is cut off');
    }
    _expectOnScreen(tester, find.byKey(const Key('ai_consent_agree')));
    _expectOnScreen(tester, find.byKey(const Key('ai_consent_use_different_account')));
  });

  testWidgets('home: Home and Tasks fit the header and Tasks stays tappable', (tester) async {
    _usePhone(tester);
    final home = HomeProvider();
    addTearDown(home.dispose);
    final taps = <int>[];
    await tester.pumpWidget(_app(
      Scaffold(body: SafeArea(child: HomeTabSwitcher(onTabTap: (index, _) => taps.add(index)))),
      providers: [ChangeNotifierProvider<HomeProvider>.value(value: home)],
    ));
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'the tab row overflows');
    final tasks = tester.getRect(find.text('Tasks'));
    expect(tasks.right, lessThanOrEqualTo(_phone.width));
    await tester.tap(find.text('Tasks'));
    expect(taps, [HomeProvider.tasksTab]);
  });

  testWidgets('activity: the Needs attention header keeps the full width above Retry all', (tester) async {
    _usePhone(tester);
    final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0)),
      loadAttention: () async =>
          ApiSuccess(AttentionItemsPage(enabled: true, items: [_item('x'), _item('y')], unseenCount: 0)),
      retry: (id, {required idempotencyKey}) async =>
          ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress)),
      retryAll: ({required idempotencyKey}) async => const ApiSuccess([]),
      markSeen: (_) async => const ApiSuccess(null),
      dismiss: (_) async => const ApiSuccess(null),
    );
    addTearDown(store.dispose);
    await store.refresh();
    await tester.pumpWidget(_app(Scaffold(
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: NeedsAttentionSection(store: store, captureMonitor: null),
        ),
      ),
    )));
    await tester.pump();
    expect(tester.takeException(), isNull);
    final header = tester.getRect(find.text('NEEDS ATTENTION'));
    final retryAll = tester.getRect(find.byKey(const Key('activity_retry_all')));
    expect(header.width, closeTo(_phone.width - 32 - 4, 1), reason: 'the header is squeezed beside Retry all');
    expect(retryAll.top, greaterThanOrEqualTo(header.bottom));
  });

  testWidgets('plan & usage: the plan badge keeps its name on one line', (tester) async {
    _usePhone(tester);
    final provider = UsageProvider();
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.unlimitedV2, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ));
    provider.debugSetUsage(
      'today',
      UsageStats(
          transcriptionSeconds: 600, speechSeconds: 0, wordsTranscribed: 900, insightsGained: 3, memoriesCreated: 1),
      [
        UsageHistoryPoint(
            date: DateTime.now().toUtc().toIso8601String(),
            transcriptionSeconds: 600,
            speechSeconds: 0,
            wordsTranscribed: 900,
            insightsGained: 3,
            memoriesCreated: 1),
      ],
    );
    // The stat tiles have their own large-text overflow (not this change); only the badge row is checked.
    final errors = <FlutterErrorDetails>[];
    final previous = FlutterError.onError;
    FlutterError.onError = errors.add;
    addTearDown(() => FlutterError.onError = previous);
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: provider,
      child: _app(const UsagePage(debugSkipFetch: true)),
    ));
    await tester.pump(const Duration(milliseconds: 100));
    FlutterError.onError = previous;
    expect(errors.map((e) => e.toString()).where((e) => !e.contains('usage_stat_tile.dart')), isEmpty);
    final badge = tester.renderObject<RenderParagraph>(find.text('Omi Pro'));
    final lines = badge
        .getBoxesForSelection(const TextSelection(baseOffset: 0, extentOffset: 'Omi Pro'.length))
        .map((box) => box.top)
        .toSet();
    expect(lines, hasLength(1), reason: 'the plan name breaks across lines');
    expect(find.text('Manage Plan'), findsOneWidget);
  });
}
