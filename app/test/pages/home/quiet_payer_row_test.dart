import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/home/widgets/quiet_payer_row.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter;

DateTime get _now => DateTime.now();
final _omi = BtDevice(name: 'Omi', id: 'AA:BB', type: DeviceType.omi, rssi: 0);
final _none = BtDevice(name: '', id: '', type: DeviceType.omi, rssi: 0);

UserSubscriptionResponse _response({
  PlanType plan = PlanType.unlimitedV2,
  SubscriptionStatus status = SubscriptionStatus.active,
  String? stripeId = 'sub_monthly',
  PaymentIssue? issue,
  bool cancelAtPeriodEnd = false,
}) =>
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: plan,
        status: status,
        stripeSubscriptionId: stripeId,
        cancelAtPeriodEnd: cancelAtPeriodEnd,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: true,
      paymentIssue: issue,
    );

ServerConversation _conversation(String id, Duration age) => ServerConversation(
      id: id,
      createdAt: _now.subtract(age),
      startedAt: _now.subtract(age),
      status: ConversationStatus.completed,
      structured: Structured('Standup', 'Notes.'),
    );

/// Only what the row reads; the real provider needs the BLE service stack.
class _FakeDevice extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? connectedDevice;
  @override
  BtDevice? pairedDevice;
  @override
  bool isConnecting = false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _World {
  _World(UserSubscriptionResponse response) : usage = UsageProvider(subscriptionRequest: () async => response);

  final UsageProvider usage;
  final conversations = ConversationProvider(isSignedIn: () => false);
  final device = _FakeDevice();
  int monthlyReads = 0;
}

Future<_World> _pump(
  WidgetTester tester, {
  UserSubscriptionResponse? response,
  bool? monthly = true,
  List<ServerConversation>? conversations,
  BtDevice? paired,
  BtDevice? remembered,
  BtDevice? connected,
  double textScale = 1,
}) async {
  final world = _World(response ?? _response());
  addTearDown(world.usage.dispose);
  await world.usage.fetchSubscription();
  world.conversations.conversations = conversations ?? [_conversation('old', const Duration(days: 6))];
  world.device.pairedDevice = paired ?? _omi;
  world.device.connectedDevice = connected;
  final row = QuietPayerRow(
    loadMonthlyPayer: () async {
      world.monthlyReads++;
      return monthly;
    },
    rememberedDevice: () => remembered ?? _none,
    devicePage: () => const Scaffold(body: Text('device page')),
  );
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: world.usage),
        ChangeNotifierProvider<ConversationProvider>.value(value: world.conversations),
        ChangeNotifierProvider<DeviceProvider>.value(value: world.device),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: Scaffold(body: CustomScrollView(slivers: [SliverToBoxAdapter(child: row)])),
      ),
    ),
  );
  await tester.pump();
  return world;
}

Future<void> _rebuild(WidgetTester tester, void Function() change) async {
  change();
  await tester.pump();
}

final _row = find.byKey(const ValueKey('quiet_payer_row'));

void main() {
  late RecordingAdapter analytics;
  setUp(() async {
    QuietPayerRow.resetSession();
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    analytics = RecordingAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  Future<List<String>> events(WidgetTester tester) async {
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    return analytics.events.map((event) => event.$1).toList();
  }

  testWidgets('a silent monthly payer with a disconnected Omi sees one quiet row with Check', (tester) async {
    await _pump(tester);

    expect(_row, findsOneWidget);
    expect(find.text('No recordings in 5 days'), findsOneWidget);
    expect(find.text('Check your Omi.'), findsOneWidget);
    expect(find.text('Check'), findsOneWidget);
  });

  testWidgets('Shown is sent once per app session, not per rebuild or remount', (tester) async {
    final world = await _pump(tester);
    await _rebuild(tester, world.conversations.notifyListeners);
    await _rebuild(tester, world.usage.notifyListeners);
    await tester.pumpWidget(const SizedBox());
    await _pump(tester);

    expect(_row, findsOneWidget);
    expect((await events(tester)).where((e) => e == 'Subscription Quiet Row Shown'), hasLength(1));
    expect(world.monthlyReads, 1);
  });

  testWidgets('Check opens the device page and sends Tapped', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('quiet_payer_check')));
    await tester.pumpAndSettle();

    expect(find.text('device page'), findsOneWidget);
    expect(await events(tester), contains('Subscription Quiet Row Tapped'));
  });

  testWidgets('the row leaves by itself when a new conversation arrives', (tester) async {
    final world = await _pump(tester);
    expect(_row, findsOneWidget);

    await _rebuild(tester, () {
      world.conversations.conversations = [
        _conversation('new', const Duration(minutes: 2)),
        ...world.conversations.conversations,
      ];
      world.conversations.notifyListeners();
    });
    expect(_row, findsNothing);
  });

  testWidgets('the row leaves by itself when the Omi connects', (tester) async {
    final world = await _pump(tester);
    expect(_row, findsOneWidget);

    await _rebuild(tester, () {
      world.device.connectedDevice = _omi;
      world.device.notifyListeners();
    });
    expect(_row, findsNothing);
  });

  testWidgets('a pairing remembered before the device is read still counts as a paired Omi', (tester) async {
    await _pump(tester, paired: _none, remembered: _omi);
    expect(_row, findsOneWidget);
  });

  testWidgets('largest text stacks Check under the copy, on screen', (tester) async {
    tester.view.physicalSize = const Size(402, 874);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await _pump(tester, textScale: 3.2);

    expect(tester.takeException(), isNull);
    final message = tester.getRect(find.text('Check your Omi.'));
    final check = tester.getRect(find.byKey(const ValueKey('quiet_payer_check')));
    expect(check.top, greaterThanOrEqualTo(message.bottom));
    expect(check.right, lessThanOrEqualTo(402));
  });

  group('shows nothing', () {
    final cases = <String, Future<void> Function(WidgetTester)>{
      'for a yearly payer': (t) => _pump(t, monthly: false),
      'while the plan interval is unknown': (t) => _pump(t, monthly: null),
      'for a free user': (t) => _pump(t, response: _response(plan: PlanType.basic, stripeId: null)),
      'for a cancelled-at-period-end plan': (t) => _pump(t, response: _response(cancelAtPeriodEnd: true)),
      'for an inactive plan': (t) => _pump(t, response: _response(status: SubscriptionStatus.inactive)),
      'when a payment issue row is showing': (t) => _pump(
            t,
            response: _response(issue: const PaymentIssue(status: 'past_due', plan: PlanType.unlimitedV2)),
          ),
      'with a conversation in the last 5 days': (t) =>
          _pump(t, conversations: [_conversation('recent', const Duration(days: 4, hours: 23))]),
      'before the conversation list has anything': (t) => _pump(t, conversations: []),
      'for a phone-mic-only user with no Omi paired': (t) => _pump(t, paired: _none, remembered: _none),
      'for another brand of device': (t) =>
          _pump(t, paired: BtDevice(name: 'Plaud', id: 'CC:DD', type: DeviceType.plaud, rssi: 0)),
      'while the Omi is connected': (t) => _pump(t, connected: _omi),
    };
    for (final entry in cases.entries) {
      testWidgets(entry.key, (tester) async {
        await entry.value(tester);
        expect(_row, findsNothing);
        expect(await events(tester), isNot(contains('Subscription Quiet Row Shown')));
      });
    }

    testWidgets('while the conversation list is loading or failed', (tester) async {
      final world = await _pump(tester);
      await _rebuild(tester, () => world.conversations.setLoadingConversations(true));
      expect(_row, findsNothing);
      await _rebuild(tester, () {
        world.conversations.setLoadingConversations(false);
        world.conversations.conversationsLoadFailed = true;
        world.conversations.notifyListeners();
      });
      expect(_row, findsNothing);
    });
  });

  test('only yearly-switch answers past the interval check count as a paid monthly price', () {
    wire.GeneratedYearlySwitchResponse answer(String reason, {bool eligible = false}) =>
        wire.GeneratedYearlySwitchResponse(eligible: eligible, reason: reason);

    expect(paidMonthlyFromYearlySwitch(null), isNull);
    expect(paidMonthlyFromYearlySwitch(answer('eligible', eligible: true)), isTrue);
    for (final monthly in ['currency', 'not_offered', 'no_yearly_price', 'no_savings']) {
      expect(paidMonthlyFromYearlySwitch(answer(monthly)), isTrue, reason: monthly);
    }
    for (final other in ['not_monthly', 'trial', 'discounted', 'free_price', 'status', 'unavailable']) {
      expect(paidMonthlyFromYearlySwitch(answer(other)), isFalse, reason: other);
    }
  });
}
