import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/paywall/paywall_pacing.dart';
import 'package:omi/pages/paywall/value_moment_paywall.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// A free Omi owner gets the paywall at the first summary they read and at the first conversation
// the free allowance locks: once per moment, never within 72h of another paywall, never for a paying
// reader or one whose subscription UI is hidden, and the first-summary offer only with a trial left.

UserSubscriptionResponse _response({
  PlanType plan = PlanType.basic,
  bool trialEligible = true,
  bool showSubscriptionUi = true,
}) =>
    UserSubscriptionResponse(
      trialEligible: trialEligible,
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: showSubscriptionUi,
    );

ServerConversation _conversation({
  ConversationSource? source = ConversationSource.omi,
  ConversationStatus status = ConversationStatus.completed,
  bool locked = false,
}) =>
    ServerConversation(
      id: 'c1',
      createdAt: DateTime.utc(2026, 10, 26, 9),
      structured: Structured('Launch checklist sync', 'Walked through the launch checklist.', emoji: '🚀'),
      source: source,
      status: status,
      isLocked: locked,
    );

void main() {
  late UsageProvider usage;
  late BuildContext? presentOn;
  late PromptQueue queue;
  late List<String> opened;

  Future<void> open(BuildContext context, String source) async => opened.add(source);

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'reader-1'});
    await SharedPreferencesUtil.init();
    usage = UsageProvider()..debugSetSubscription(_response());
    presentOn = null;
    queue = PromptQueue(contextProvider: () => presentOn);
    opened = [];
  });

  tearDown(() {
    usage.dispose();
    PromptQueue.instance.reset();
  });

  Future<void> host(WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Builder(builder: (context) {
            presentOn = context;
            return const SizedBox.shrink();
          }),
        ),
      ),
    );
  }

  /// Lets the queued offer run past its beat and open.
  Future<void> settle(WidgetTester tester) async {
    queue.pump();
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
  }

  group('eligible', () {
    test('a free reader with a trial left gets both moments', () {
      expect(ValueMomentPaywall.eligible(usage, PaywallMoment.ahaFirstSummary), isTrue);
      expect(ValueMomentPaywall.eligible(usage, PaywallMoment.freeCap), isTrue);
    });

    test('a free reader with no trial left gets the cap moment only (the plans sheet)', () {
      usage.debugSetSubscription(_response(trialEligible: false));
      expect(ValueMomentPaywall.eligible(usage, PaywallMoment.ahaFirstSummary), isFalse);
      expect(ValueMomentPaywall.eligible(usage, PaywallMoment.freeCap), isTrue);
    });

    test('paying, hidden-subscription-UI and not-yet-loaded readers get neither', () {
      for (final response in [
        _response(plan: PlanType.unlimitedV2),
        _response(plan: PlanType.unlimited),
        _response(plan: PlanType.plus),
        _response(plan: PlanType.unknown('future_tier')),
        _response(showSubscriptionUi: false),
      ]) {
        usage.debugSetSubscription(response);
        for (final moment in PaywallMoment.values) {
          expect(ValueMomentPaywall.eligible(usage, moment), isFalse, reason: '$response $moment');
        }
      }
      final unloaded = UsageProvider();
      addTearDown(unloaded.dispose);
      expect(ValueMomentPaywall.eligible(unloaded, PaywallMoment.freeCap), isFalse);
    });
  });

  testWidgets('each moment opens once, with its own source', (tester) async {
    await host(tester);
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), queue: queue, open: open),
        isTrue);
    await settle(tester);
    expect(opened, ['aha_first_summary']);

    // Spent for this account, even once the 72h have passed.
    PaywallPacing.markShown(now: DateTime.now().subtract(const Duration(hours: 73)));
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), queue: queue, open: open),
        isFalse);

    expect(
        ValueMomentPaywall.offer(PaywallMoment.freeCap,
            conversation: _conversation(locked: true), queue: queue, open: open),
        isTrue);
    await settle(tester);
    expect(opened, ['aha_first_summary', 'free_cap']);
    expect(
        ValueMomentPaywall.offer(PaywallMoment.freeCap,
            conversation: _conversation(locked: true), queue: queue, open: open),
        isFalse);
  });

  testWidgets('no offer within 72h of any paywall; the moment waits for the next one', (tester) async {
    await host(tester);
    PaywallPacing.markShown(now: DateTime.now().subtract(const Duration(hours: 71)));
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), queue: queue, open: open),
        isFalse);

    PaywallPacing.markShown(now: DateTime.now().subtract(const Duration(hours: 73)));
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), queue: queue, open: open),
        isTrue);
    await settle(tester);
    expect(opened, ['aha_first_summary']);
  });

  testWidgets('a paywall that opens while the offer waits in the queue cancels it', (tester) async {
    await host(tester);
    ValueMomentPaywall.offer(PaywallMoment.freeCap,
        conversation: _conversation(locked: true), queue: queue, open: open);
    PaywallPacing.markShown();
    await settle(tester);
    expect(opened, isEmpty);
  });

  testWidgets('never stacked with a store-review sheet; the moment waits for another session', (tester) async {
    await host(tester);
    var reviewAsked = true;
    ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
        conversation: _conversation(), queue: queue, open: open, reviewRequested: () => reviewAsked);
    await settle(tester);
    expect(opened, isEmpty);

    reviewAsked = false;
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), queue: queue, open: open, reviewRequested: () => reviewAsked),
        isTrue,
        reason: 'not spent: nothing opened');
    await settle(tester);
    expect(opened, ['aha_first_summary']);
  });

  testWidgets('a plans sheet opened while the cap offer loads the subscription cancels it', (tester) async {
    usage.dispose();
    // The reader taps Upgrade on "Processing paused" while the subscription is still loading.
    usage = UsageProvider(subscriptionRequest: () async {
      PaywallPacing.markShown();
      return _response();
    });
    await host(tester);
    expect(
        ValueMomentPaywall.offer(PaywallMoment.freeCap,
            conversation: _conversation(locked: true), usage: usage, queue: queue, open: open),
        isTrue);
    await settle(tester);
    expect(opened, isEmpty);
  });

  test('only Omi owners: paired here, or the conversation came from an Omi', () async {
    expect(ValueMomentPaywall.ownsOmi(_conversation(source: ConversationSource.phone)), isFalse);
    expect(ValueMomentPaywall.ownsOmi(_conversation(source: null)), isFalse);
    expect(ValueMomentPaywall.ownsOmi(_conversation(source: ConversationSource.limitless)), isFalse);
    for (final source in [
      ConversationSource.omi,
      ConversationSource.friend,
      ConversationSource.openglass,
      ConversationSource.sdcard,
    ]) {
      expect(ValueMomentPaywall.ownsOmi(_conversation(source: source)), isTrue, reason: '$source');
    }
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(source: ConversationSource.phone), queue: queue, open: open),
        isFalse);

    await SharedPreferencesUtil().btDeviceSet(BtDevice(id: 'AA:BB', name: 'Omi', type: DeviceType.omi, rssi: 0));
    expect(ValueMomentPaywall.ownsOmi(_conversation(source: ConversationSource.phone)), isTrue);
    await SharedPreferencesUtil().btDeviceSet(BtDevice(id: 'CC:DD', name: 'Bee', type: DeviceType.bee, rssi: 0));
    expect(ValueMomentPaywall.ownsOmi(_conversation(source: ConversationSource.phone)), isFalse);
  });

  test('a reader known not to qualify queues nothing; an unloaded subscription waits for the check', () {
    usage.debugSetSubscription(_response(plan: PlanType.unlimited));
    expect(
        ValueMomentPaywall.offer(PaywallMoment.freeCap,
            conversation: _conversation(locked: true), usage: usage, queue: queue, open: open),
        isFalse);
    expect(queue.pendingIds, isEmpty);
    usage.debugSetSubscription(_response(trialEligible: false));
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), usage: usage, queue: queue, open: open),
        isFalse);
    final unloaded = UsageProvider();
    addTearDown(unloaded.dispose);
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), usage: unloaded, queue: queue, open: open),
        isTrue);
  });

  test('the first-summary moment needs a finished, readable conversation', () {
    for (final conversation in [
      _conversation(status: ConversationStatus.processing),
      _conversation(status: ConversationStatus.in_progress),
      _conversation(locked: true),
      _conversation()..discarded = true,
    ]) {
      expect(
          ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary, conversation: conversation, queue: queue, open: open),
          isFalse);
    }
  });

  testWidgets('a reader who no longer qualifies when it opens keeps the moment for later', (tester) async {
    await host(tester);
    ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary, conversation: _conversation(), queue: queue, open: open);
    usage.debugSetSubscription(_response(plan: PlanType.unlimited));
    await settle(tester);
    expect(opened, isEmpty, reason: 'never for a paying reader');

    usage.debugSetSubscription(_response());
    expect(
        ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
            conversation: _conversation(), queue: queue, open: open),
        isTrue,
        reason: 'not spent: nothing opened');
    await settle(tester);
    expect(opened, ['aha_first_summary']);
  });

  testWidgets('no trial left: nothing at the first summary, the plans sheet at the cap', (tester) async {
    usage.debugSetSubscription(_response(trialEligible: false));
    await host(tester);
    ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary, conversation: _conversation(), queue: queue, open: open);
    await settle(tester);
    expect(opened, isEmpty);
    ValueMomentPaywall.offer(PaywallMoment.freeCap,
        conversation: _conversation(locked: true), queue: queue, open: open);
    await settle(tester);
    expect(opened, ['free_cap']);
  });

  testWidgets('after the "Processing paused" Upgrade opens the plans sheet, the cap offer stays away', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    PlatformManager.initializeForLocalHarness();
    usage.debugSetAvailablePlans({
      'plans': <dynamic>[
        for (final (interval, amount) in [('month', 2999), ('year', 26991)])
          {
            'id': 'price_unlimited_v2_$interval',
            'plan_id': 'unlimited_v2',
            'title': 'Omi Pro',
            'interval': interval,
            'unit_amount': amount,
            'is_active': false,
          },
      ]
    });
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body: Builder(builder: (context) {
              presentOn = context;
              return TextButton(onPressed: () => openHeldAudioPlans(context), child: const Text('Upgrade'));
            }),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Upgrade'));
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.byType(PlansSheet), findsOneWidget);
    Navigator.of(tester.element(find.byType(PlansSheet))).pop();
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(
        ValueMomentPaywall.offer(PaywallMoment.freeCap,
            conversation: _conversation(locked: true), usage: usage, queue: queue, open: open),
        isFalse);
    await settle(tester);
    expect(opened, isEmpty);
  });

  group('locked row', () {
    late ConversationProvider conversations;

    setUp(() {
      conversations = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      );
    });

    tearDown(() => conversations.dispose());

    Future<void> pumpRow(WidgetTester tester, ServerConversation conversation) async {
      conversations.conversations = [conversation];
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ],
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(
              body: ListView(children: [
                ConversationListItem(conversation: conversation, date: conversation.createdAt, conversationIdx: 0),
              ]),
            ),
          ),
        ),
      );
      await tester.pump();
    }

    testWidgets('an Omi conversation the free allowance locked queues the cap offer', (tester) async {
      await pumpRow(tester, _conversation(locked: true));
      expect(PromptQueue.instance.pendingIds, ['value-moment-free_cap']);
    });

    testWidgets('an unlocked row queues nothing', (tester) async {
      await pumpRow(tester, _conversation());
      expect(PromptQueue.instance.pendingIds, isEmpty);
    });
  });
}
