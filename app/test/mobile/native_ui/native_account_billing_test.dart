import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
const _pathProvider = MethodChannel('plugins.flutter.io/path_provider');
final _l10n = lookupAppLocalizations(const Locale('en'));
TestDefaultBinaryMessenger get _messenger => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

/// Answers each native 'present' with the next reply (a [PlatformException] is thrown, as Swift's
/// refusal would be) and records the presented snapshots. Activities answer at once.
List<Map> _answerPresentations(List<Object? Function(Map snapshot)> replies) {
  final presented = <Map>[];
  _messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    final reply = replies[presented.length - 1](snapshot);
    if (reply is PlatformException) throw reply;
    return reply;
  });
  addTearDown(() => _messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

Object? _choose(String action) => {'action': action, 'values': <String, Object?>{}, 'reason': 'action'};
Object? _cancel(Map _) => {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'};
final _refused = PlatformException(code: 'invalid_native_presentation');

/// Cancellation is recorded; a pending [reply] holds the request open.
class _FakeUsage extends UsageProvider {
  final calls = <(String?, String?)>[];
  Completer<bool>? reply;

  @override
  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) {
    calls.add((reason, reasonDetails));
    return reply?.future ?? Future.value(true);
  }
}

/// The rows the topmost native surface dispatches.
NativeRow _row(WidgetTester tester, String id) =>
    IosNativeSurface.debugDispatchRows(tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface)).last)
        .singleWhere((row) => row.id == id);

/// Sends [id] from the newest native view exactly as Swift would; a refused command throws.
Future<void> _send(NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  const StandardMethodCodec().decodeEnvelope(reply!);
}

Future<void> _settle(WidgetTester tester) async {
  await NativeTestHost.settle(tester);
  await tester.pump(const Duration(seconds: 1));
  await NativeTestHost.settle(tester);
}

Future<void> _pumpHome(WidgetTester tester, UsageProvider usage) => tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ],
        child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: [Locale('en')],
            home: Scaffold(body: Text('home')))));

BuildContext _home(WidgetTester tester) => tester.element(find.text('home', skipOffstage: false));

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('cancel subscription', () {
    Future<(NativeTestHost, _FakeUsage, Future<bool?>)> openConfirmStep(WidgetTester tester) async {
      final host = NativeTestHost.install();
      _answerPresentations([]);
      final usage = _FakeUsage();
      addTearDown(usage.dispose);
      await _pumpHome(tester, usage);
      final result = CancelSubscriptionFlow.show(_home(tester));
      await _settle(tester);

      expect(_row(tester, 'leave_step').title, _l10n.leaveFlowStepOf(1, 3));
      expect(_row(tester, 'leave_continue').projection['enabled'], false);
      await expectLater(_send(host, 'leave_continue'), throwsA(isA<PlatformException>()),
          reason: 'Continue is refused until a reason is chosen');
      await _send(host, 'cancel_reason:too_expensive');
      await _settle(tester);
      expect(_row(tester, 'cancel_reason:too_expensive').symbol, 'checkmark.circle.fill');
      expect(_row(tester, 'cancel_reason:other').symbol, 'circle');
      expect(_row(tester, 'leave_continue').projection['enabled'], true);
      await _send(host, 'leave_continue');
      await _settle(tester);

      final details = _row(tester, 'cancel_details');
      expect(details.maximumLength, 300);
      await expectLater(_send(host, 'cancel_details', 'x' * 301), throwsA(isA<PlatformException>()),
          reason: 'Details beyond the limit never reach the owner');
      await _send(host, 'cancel_details', 'Too pricey');
      await _settle(tester);
      expect(_row(tester, 'cancel_details').value, 'Too pricey');
      await _send(host, 'leave_continue');
      await _settle(tester);
      expect(_row(tester, 'cancel_period').symbol, 'info.circle');
      return (host, usage, result);
    }

    testWidgets('confirm cancels once with the reason and details; back is blocked meanwhile', (tester) async {
      final (host, usage, result) = await openConfirmStep(tester);
      expect(_row(tester, 'cancel_confirm').subtitle, isEmpty);
      usage.reply = Completer<bool>();
      unawaited(_send(host, 'cancel_confirm'));
      await _settle(tester);

      expect(usage.calls, [('too_expensive', 'Too pricey')]);
      expect(_row(tester, 'cancel_confirm').projection['enabled'], false);
      expect(_row(tester, 'cancel_confirm').subtitle, _l10n.cancelling,
          reason: 'The native row shows progress even when the activity HUD is gone');
      expect(_row(tester, 'cancel_keep').projection['enabled'], false);
      expect(_row(tester, 'leave_back').projection['enabled'], false);
      await tester.binding.handlePopRoute();
      await _settle(tester);
      expect(_row(tester, 'cancel_period'), isNotNull, reason: 'System back cannot leave while cancelling');
      await expectLater(_send(host, 'cancel_confirm'), throwsA(isA<PlatformException>()));

      usage.reply!.complete(true);
      await _settle(tester);
      expect(await result, true);
      expect(usage.calls, hasLength(1));
      expect(find.text('home'), findsOneWidget);
    });

    testWidgets('keep closes the whole flow with false and cancels nothing', (tester) async {
      final (host, usage, result) = await openConfirmStep(tester);
      await _send(host, 'cancel_keep');
      await _settle(tester);
      expect(await result, false);
      expect(usage.calls, isEmpty);
      expect(find.text('home'), findsOneWidget);
    });
  });

  group('delete account', () {
    testWidgets('delete waits for the exact word, requests once and blocks export meanwhile', (tester) async {
      final host = NativeTestHost.install();
      _answerPresentations([]);
      final usage = _FakeUsage();
      addTearDown(usage.dispose);
      final requests = <(String?, String?)>[];
      final reply = Completer<bool>();
      await _pumpHome(tester, usage);
      unawaited(Navigator.of(_home(tester)).push(MaterialPageRoute<void>(
          builder: (_) => DeleteAccount(deleteAccountRequest: ({reason, reasonDetails}) {
                requests.add((reason, reasonDetails));
                return reply.future;
              }))));
      await _settle(tester);
      await expectLater(_send(host, 'leave_continue'), throwsA(isA<PlatformException>()));
      await _send(host, 'delete_reason:taking_break');
      await _settle(tester);
      await _send(host, 'leave_continue');
      await _settle(tester);
      expect(_row(tester, 'delete_details').maximumLength, 500);
      await _send(host, 'delete_details', 'Back later');
      await _settle(tester);
      await _send(host, 'leave_skip');
      await _settle(tester);

      expect(_row(tester, 'delete_account').projection['enabled'], false);
      for (final typed in ['DELET', 'DEL ETE', 'DELETE!']) {
        await _send(host, 'delete_confirm_word', typed);
        await _settle(tester);
        expect(_row(tester, 'delete_confirm_word').value, typed, reason: 'The field keeps what was typed');
        expect(_row(tester, 'delete_account').projection['enabled'], false, reason: '"$typed" is not the word');
        await expectLater(_send(host, 'delete_account'), throwsA(isA<PlatformException>()));
      }
      expect(_row(tester, 'delete_export').projection['enabled'], true);
      DataExport.exportInProgress.value = true;
      await _settle(tester);
      expect(_row(tester, 'delete_export').projection['enabled'], false);
      expect(_row(tester, 'delete_export').subtitle, _l10n.exportingAllData);
      DataExport.exportInProgress.value = false;
      await _settle(tester);

      await _send(host, 'delete_confirm_word', 'delete');
      await _settle(tester);
      expect(_row(tester, 'delete_account').projection['enabled'], true);
      expect(_row(tester, 'delete_account').subtitle, isEmpty);
      unawaited(_send(host, 'delete_account'));
      await _settle(tester);
      expect(requests, [('taking_break', 'Back later')]);
      expect(_row(tester, 'delete_export').projection['enabled'], false);
      expect(_row(tester, 'delete_keep').projection['enabled'], false);
      expect(_row(tester, 'leave_back').projection['enabled'], false);
      expect(_row(tester, 'delete_account').projection['enabled'], false);
      expect(_row(tester, 'delete_account').subtitle, _l10n.deleting,
          reason: 'The native row shows progress even when the activity HUD is gone');
      await expectLater(_send(host, 'delete_account'), throwsA(isA<PlatformException>()),
          reason: 'A second tap while deleting never reaches the request');

      reply.complete(false);
      await _settle(tester);
      expect(requests, hasLength(1));
      expect(_row(tester, 'delete_account').projection['enabled'], true);
      expect(_row(tester, 'delete_account').subtitle, isEmpty);
      await tester.pump(const Duration(seconds: 10));
    });
  });

  group('plan confirmations', () {
    Future<_FakeUsage> pumpSheet(WidgetTester tester, Subscription subscription, List<Map<String, dynamic>> plans,
        {List<SubscriptionPlan> availablePlans = const [], bool animateHeroOnMount = false}) async {
      await tester.binding.setSurfaceSize(const Size(430, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final usage = _FakeUsage()
        ..debugSetSubscription(UserSubscriptionResponse(
            subscription: subscription,
            transcriptionSecondsUsed: 0,
            transcriptionSecondsLimit: 0,
            wordsTranscribedUsed: 0,
            wordsTranscribedLimit: 0,
            insightsGainedUsed: 0,
            insightsGainedLimit: 0,
            availablePlans: availablePlans))
        ..debugSetAvailablePlans({
          'plans': <dynamic>[...plans]
        });
      addTearDown(usage.dispose);
      await _pumpHome(tester, usage);
      unawaited(Navigator.of(_home(tester))
          .push(MaterialPageRoute<void>(builder: (_) => _Sheet(animateHeroOnMount: animateHeroOnMount))));
      await _settle(tester);
      return usage;
    }

    Map<String, dynamic> price(String planId, String title, String interval, int amount, {bool active = false}) => {
          'id': 'price_${planId}_$interval',
          'plan_id': planId,
          'title': title,
          'interval': interval,
          'unit_amount': amount,
          'price_string': '\$${amount ~/ 100}',
          'is_active': active,
        };

    Future<void> tapVisible(WidgetTester tester, Finder finder) async {
      await tester.ensureVisible(finder);
      await tester.pump();
      await tester.tap(finder);
      await _settle(tester);
    }

    /// Records whether the free-plan switch began: its readiness check is the first thing it awaits.
    List<String> watchFreePlanSwitch() {
      final calls = <String>[];
      _messenger.setMockMethodCallHandler(_pathProvider, (call) {
        calls.add(call.method);
        return Completer<Object?>().future;
      });
      addTearDown(() => _messenger.setMockMethodCallHandler(_pathProvider, null));
      return calls;
    }

    Future<void> openDowngrade(WidgetTester tester) async {
      await pumpSheet(tester, Subscription(plan: PlanType.basic, status: SubscriptionStatus.active), [
        price('unlimited_v2', 'Unlimited', 'month', 1900),
        price('unlimited_v2', 'Unlimited', 'year', 19000),
      ]);
      await tapVisible(tester, find.text(_l10n.downgradeToFreemiumAction));
    }

    testWidgets('a cancelled native downgrade never switches to the free plan', (tester) async {
      NativeTestHost.install();
      final presented = _answerPresentations([_cancel]);
      final switched = watchFreePlanSwitch();
      await openDowngrade(tester);
      expect(presented.single['title'], _l10n.downgradeToFreemiumTitle);
      final confirm = (presented.single['toolbar'] as List).cast<Map>().singleWhere((row) => row['id'] == 'confirm');
      expect(confirm['title'], _l10n.downgradeAnyway);
      expect(confirm['destructive'], true);
      final message = ((presented.single['sections'] as List).single as Map)['rows'] as List;
      expect(message.single['title'],
          allOf(contains(_l10n.downgradeLimitationsHeading), contains(_l10n.downgradeLimitSpeakers)));
      expect(switched, isEmpty);
    });

    testWidgets('a confirmed native downgrade switches to the free plan', (tester) async {
      NativeTestHost.install();
      _answerPresentations([(_) => _choose('confirm')]);
      final switched = watchFreePlanSwitch();
      await openDowngrade(tester);
      expect(switched, ['getApplicationSupportDirectory']);
    });

    testWidgets('without a native alert the existing downgrade dialog asks first', (tester) async {
      NativeTestHost.install();
      _answerPresentations([(_) => _refused]);
      final switched = watchFreePlanSwitch();
      await openDowngrade(tester);
      expect(find.byType(PlanDialogLine), findsNWidgets(4));
      expect(switched, isEmpty);
      await tester.tap(find.text(_l10n.downgradeAnyway));
      await _settle(tester);
      expect(switched, ['getApplicationSupportDirectory']);
    });

    Future<void> openAnnualSwitch(WidgetTester tester) async {
      await pumpSheet(
          tester,
          Subscription(
              plan: PlanType.unlimitedV2,
              status: SubscriptionStatus.active,
              stripeSubscriptionId: 'sub_1',
              currentPriceId: 'price_unlimited_v2_month'),
          [
            price('plus', 'Plus', 'month', 900),
            price('plus', 'Plus', 'year', 9000),
            price('unlimited_v2', 'Unlimited', 'month', 1900, active: true),
            price('unlimited_v2', 'Unlimited', 'year', 19000),
          ],
          availablePlans: [
            SubscriptionPlan(id: 'unlimited_v2', title: 'Unlimited', prices: [
              PricingOption(id: 'price_unlimited_v2_year', title: 'Unlimited yearly', priceString: '\$190'),
            ]),
          ]);
      await tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Unlimited'));
      await tapVisible(tester, find.text(_l10n.billingYearly));
      await tapVisible(tester, find.byKey(const ValueKey('plans_sheet_upgrade_button')));
    }

    testWidgets('a cancelled annual switch never reaches the upgrade owner', (tester) async {
      NativeTestHost.install();
      final presented = _answerPresentations([_cancel]);
      await openAnnualSwitch(tester);
      expect(presented.map((snapshot) => snapshot['title']), [_l10n.upgradeToAnnualPlan]);
      final message = ((presented.single['sections'] as List).single as Map)['rows'] as List;
      expect(
          message.single['title'], allOf(contains(_l10n.importantBillingInfo), contains(_l10n.thirteenMonthsCoverage)));
    });

    testWidgets('a confirmed annual switch continues to the upgrade owner', (tester) async {
      NativeTestHost.install();
      final presented = _answerPresentations([(_) => _choose('confirm'), _cancel]);
      await openAnnualSwitch(tester);
      // The upgrade handler's own plan-change confirmation is the first thing it asks.
      expect(presented.map((snapshot) => snapshot['title']), [_l10n.upgradeToAnnualPlan, _l10n.confirmPlanChange]);
    });
    group('hero animations', () {
      final plans = [
        price('unlimited_v2', 'Unlimited', 'month', 1900),
        price('unlimited_v2', 'Unlimited', 'year', 19000),
      ];

      testWidgets('run only while the classic tree is mounted, then stop', (tester) async {
        await pumpSheet(tester, Subscription(plan: PlanType.basic, status: SubscriptionStatus.active), plans,
            animateHeroOnMount: true);
        final sheet = tester.state<_SheetState>(find.byType(_Sheet));
        expect(sheet._wave.isAnimating, true);
        expect(sheet._arrow.isAnimating, true);

        sheet.hideSheet();
        await _settle(tester);
        expect(sheet._wave.isAnimating, false, reason: 'Nothing ticks once the classic tree is gone');
        expect(sheet._arrow.isAnimating, false);
      });

      testWidgets('leave caller-owned controllers alone by default', (tester) async {
        await pumpSheet(tester, Subscription(plan: PlanType.basic, status: SubscriptionStatus.active), plans);
        final sheet = tester.state<_SheetState>(find.byType(_Sheet));
        expect(sheet._wave.isAnimating, false);
        expect(sheet._arrow.isAnimating, false);
      });
    });
  });

  group('account name', () {
    Future<NativeTestHost> pumpProfile(WidgetTester tester) async {
      SharedPreferencesUtil().givenName = 'Ada';
      final host = NativeTestHost.install();
      await _pumpHome(tester, _FakeUsage());
      unawaited(Navigator.of(_home(tester)).push(MaterialPageRoute<void>(builder: (_) => const ProfilePage())));
      await _settle(tester);
      return host;
    }

    Object? save(String name) => {
          'action': 'save',
          'values': {'name': name},
          'reason': 'action'
        };

    testWidgets('a blank name re-presents with the validation message and never saves', (tester) async {
      final host = await pumpProfile(tester);
      final presented = _answerPresentations([(_) => save('   '), _cancel]);
      await _send(host, 'account_name');
      await _settle(tester);
      expect(presented, hasLength(2));
      final first = ((presented.first['sections'] as List).single as Map)['rows'] as List;
      expect(first.map((row) => row['id']), ['name_prompt', 'name']);
      expect(first.last['value'], 'Ada');
      expect(first.last['maximumLength'], 100);
      final second = ((presented.last['sections'] as List).single as Map)['rows'] as List;
      expect(second.last['title'], _l10n.nameCannotBeEmpty);
      expect(SharedPreferencesUtil().givenName, 'Ada');
      expect(find.byType(ChangeNameWidget), findsNothing);
    });

    testWidgets('a valid name saves through the shared owner', (tester) async {
      final host = await pumpProfile(tester);
      _answerPresentations([(_) => save('  Grace  ')]);
      await _send(host, 'account_name');
      await _settle(tester);
      expect(SharedPreferencesUtil().givenName, 'Grace');
      expect(_row(tester, 'account_name').subtitle, 'Grace');
      await tester.pump(const Duration(seconds: 10));
    });

    testWidgets('without a native editor the existing dialog opens', (tester) async {
      final host = await pumpProfile(tester);
      _answerPresentations([(_) => _refused]);
      // The command completes when the dialog closes.
      unawaited(_send(host, 'account_name'));
      await _settle(tester);
      expect(find.byType(ChangeNameWidget), findsOneWidget);
    });

    testWidgets('saveGivenName refuses a blank name', (tester) async {
      await _pumpHome(tester, _FakeUsage());
      SharedPreferencesUtil().givenName = 'Ada';
      expect(saveGivenName(_home(tester), '  '), false);
      expect(SharedPreferencesUtil().givenName, 'Ada');
    });
  });
}

/// The plans sheet with its animation owners, pushed as a page.
class _Sheet extends StatefulWidget {
  const _Sheet({this.animateHeroOnMount = false});

  final bool animateHeroOnMount;

  @override
  State<_Sheet> createState() => _SheetState();
}

class _SheetState extends State<_Sheet> with TickerProviderStateMixin {
  late final _wave = AnimationController(duration: const Duration(seconds: 18), vsync: this);
  late final _arrow = AnimationController(duration: const Duration(milliseconds: 800), vsync: this);
  var _showSheet = true;

  void hideSheet() => setState(() => _showSheet = false);

  @override
  void dispose() {
    _wave.dispose();
    _arrow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      body: _showSheet
          ? PlansSheet(
              waveController: _wave,
              notesController: _wave,
              arrowController: _arrow,
              arrowAnimation: _arrow,
              animateHeroOnMount: widget.animateHeroOnMount)
          : const SizedBox.shrink());
}
