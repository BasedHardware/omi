// Exercises the real sheet/provider code path with synthetic subscription fixtures.
// Redemption may refresh server truth only after applied; it never checks out or upgrades.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _apply = ValueKey('plans_sheet_apply_code');
const _field = ValueKey('plans_sheet_promo_code');
const _boundary = ValueKey('redeem_render');
const _originalAllowance = TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'paid_plan');
const _refreshedAllowance = TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'paid_plan', remainingSeconds: 900);

UserSubscriptionResponse _snapshot(
        {bool cancel = false,
        bool hasSub = true,
        bool active = true,
        TranscriptionAllowanceSnapshot allowance = _originalAllowance}) =>
    UserSubscriptionResponse(
      subscription: Subscription(
          plan: hasSub ? PlanType.unlimitedV2 : PlanType.basic,
          status: active ? SubscriptionStatus.active : SubscriptionStatus.inactive,
          stripeSubscriptionId: hasSub ? 'sub_synthetic' : null,
          currentPriceId: hasSub ? 'price_year_synthetic' : null,
          cancelAtPeriodEnd: cancel),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      transcriptionAllowance: allowance,
    );

class _Usage extends UsageProvider {
  _Usage({required super.redeemCodeRequest, required super.subscriptionRequest});
  int checkouts = 0;
  final checkoutCodes = <String?>[];
  int upgrades = 0;
  @override
  Future<void> loadAvailablePlans() async {}
  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession(
      {required String priceId, String? promotionCode, int? trialDays}) async {
    checkouts++;
    checkoutCodes.add(promotionCode);
    return null;
  }

  @override
  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId, String? promotionCode}) async {
    upgrades++;
    return null;
  }
}

class _Harness extends StatefulWidget {
  const _Harness();
  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> with SingleTickerProviderStateMixin {
  late final _animation = AnimationController(vsync: this);
  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
      waveController: _animation,
      notesController: _animation,
      arrowController: _animation,
      arrowAnimation: _animation,
      readStorefrontGate: () async => false);
}

Future<void> _pump(WidgetTester tester, _Usage usage, {Locale locale = const Locale('en')}) async {
  tester.view.physicalSize = const Size(393, 852);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  usage.debugSetAvailablePlans({
    'plans': <dynamic>[
      {
        'id': 'price_year_synthetic',
        'plan_id': 'unlimited_v2',
        'title': 'Omi Pro',
        'interval': 'year',
        'unit_amount': 29900,
        'price_string': '\$299/yr',
        'is_active': usage.subscription?.subscription.plan.isPaid == true
      },
      {
        'id': 'price_month_synthetic',
        'plan_id': 'unlimited_v2',
        'title': 'Omi Pro',
        'interval': 'month',
        'unit_amount': 3000,
        'price_string': '\$30/mo',
        'is_active': false
      },
    ]
  });
  addTearDown(usage.dispose);
  await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: MultiProvider(
          providers: [
            ChangeNotifierProvider<UsageProvider>.value(value: usage),
            ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
          ],
          child: MaterialApp(
              debugShowCheckedModeBanner: false,
              locale: locale,
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              theme: buildOmiTheme(brightness: Brightness.dark).copyWith(
                  platform: TargetPlatform.iOS,
                  textTheme: buildOmiTheme(brightness: Brightness.dark).textTheme.apply(fontFamily: 'Evidence')),
              home: const Scaffold(body: _Harness())))));
  await tester.pump();
  final context = tester.element(find.byType(PlansSheet));
  await tester.scrollUntilVisible(find.text(AppLocalizations.of(context).promoCode), 220,
      scrollable: find.byType(Scrollable).first);
  await Scrollable.ensureVisible(tester.element(find.text(AppLocalizations.of(context).promoCode)), alignment: 0.2);
  await tester.pump();
  await tester.tap(find.text(AppLocalizations.of(context).promoCode));
  await tester.pump();
  await tester.ensureVisible(find.byKey(_field));
  await tester.pump();
}

Future<void> _capture(WidgetTester tester, String name) async {
  const evidence = String.fromEnvironment('OMI_REDEEM_EVIDENCE_DIR');
  if (evidence.isEmpty) return;
  tester.testTextInput.hide();
  await tester.pump(const Duration(milliseconds: 300));
  final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_boundary));
  await tester.runAsync(() async {
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(evidence).create(recursive: true);
    await File('$evidence/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    TranscriptionAllowanceCache.replace(_originalAllowance);
    OmiColors.active = OmiPalette.dark;
  });
  setUpAll(() async {
    final font = File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf');
    if (font.existsSync()) await _loadFont('Evidence', font);
    await _loadFont('MaterialIcons', _materialIconsFont());
    for (final variant in ['Solid', 'Regular']) {
      final file = _packageAsset('font_awesome_flutter',
          'lib/fonts/Font-Awesome-7-Free-${variant == 'Solid' ? 'Solid-900' : 'Regular-400'}.otf');
      if (file != null) {
        await _loadFont('FontAwesome$variant', file);
        await _loadFont('packages/font_awesome_flutter/FontAwesome$variant', file);
      }
    }
  });
  tearDown(TranscriptionAllowanceCache.clear);

  test('provider waits for an older read then refreshes post-application truth', () async {
    final oldRead = Completer<UserSubscriptionResponse?>();
    final applied = Completer<ApiResult<bool>>();
    var reads = 0;
    var calls = 0;
    final usage = _Usage(redeemCodeRequest: (_, {canSend}) async {
      calls++;
      return applied.future;
    }, subscriptionRequest: () async {
      reads++;
      if (reads == 1) return await oldRead.future;
      return _snapshot(allowance: _refreshedAllowance);
    })
      ..debugSetSubscription(_snapshot());
    addTearDown(usage.dispose);
    final pending = usage.fetchSubscription();
    final redemption = usage.redeemUserSubscriptionCode('SYNTHETIC');
    expect(await usage.redeemUserSubscriptionCode('SYNTHETIC'), isA<ApiFailure<bool>>());
    applied.complete(const ApiSuccess(true));
    await Future<void>.delayed(Duration.zero);
    expect(reads, 1);
    oldRead.complete(_snapshot());
    await pending;
    expect(await redemption, isA<ApiSuccess<bool>>());
    expect(reads, 2);
    expect(calls, 1);
    expect(TranscriptionAllowanceCache.current, same(_refreshedAllowance));
  });

  test('an account switch invalidates the send guard and suppresses refresh/success', () async {
    final applied = Completer<ApiResult<bool>>();
    bool Function()? guard;
    var reads = 0;
    final usage = _Usage(redeemCodeRequest: (_, {canSend}) async {
      guard = canSend;
      return applied.future;
    }, subscriptionRequest: () async {
      reads++;
      return _snapshot();
    })
      ..debugSetSubscription(_snapshot());
    addTearDown(usage.dispose);
    final redemption = usage.redeemUserSubscriptionCode('SYNTHETIC');
    expect(guard!(), isTrue);
    usage.clearUserData();
    expect(guard!(), isFalse);
    applied.complete(const ApiSuccess(true));
    expect(await redemption, isA<ApiFailure<bool>>());
    expect(reads, 0);
    expect(usage.subscription, isNull);
    expect(TranscriptionAllowanceCache.current, isNull);
  });

  for (final fixture in ['annual active', 'trial (server active projection)']) {
    testWidgets('$fixture submits same-plan code with no checkout/upgrade and refreshes only on applied',
        (tester) async {
      var redemptions = 0;
      var reads = 0;
      final completer = Completer<ApiResult<bool>>();
      final usage = _Usage(redeemCodeRequest: (code, {canSend}) async {
        redemptions++;
        expect(code, 'SYNTHETIC');
        expect(canSend!(), isTrue);
        return completer.future;
      }, subscriptionRequest: () async {
        reads++;
        return _snapshot(allowance: _refreshedAllowance);
      })
        ..debugSetSubscription(_snapshot());
      await _pump(tester, usage);
      expect(find.byKey(const ValueKey('plans_sheet_upgrade_button')), findsNothing);
      expect(tester.widget<OmiButton>(find.byKey(_apply)).onPressed, isNull);
      await tester.enterText(find.byKey(_field), 'SYNTHETIC');
      await tester.pump();
      await tester.ensureVisible(find.byKey(_apply));
      await tester.pump();
      await _capture(tester, fixture.startsWith('annual') ? 'redeem-field' : 'redeem-trial-field');
      if (fixture.startsWith('trial')) {
        await tester.testTextInput.receiveAction(TextInputAction.done);
      } else {
        await tester.tap(find.byKey(_apply));
      }
      await tester.pump();
      await tester.tap(find.byKey(_apply));
      await tester.testTextInput.receiveAction(TextInputAction.done);
      expect(redemptions, 1);
      expect(reads, 0);
      expect(TranscriptionAllowanceCache.current, same(_originalAllowance));
      completer.complete(const ApiSuccess(true));
      await tester.pump();
      await tester.pump();
      expect(reads, 1);
      expect(usage.checkouts, 0);
      expect(usage.upgrades, 0);
      expect(usage.subscription!.subscription.currentPriceId, 'price_year_synthetic');
      expect(TranscriptionAllowanceCache.current, same(_refreshedAllowance));
      expect(find.byKey(const ValueKey('plans_sheet_code_applied')), findsOneWidget);
      expect(tester.widget<TextField>(find.byKey(_field)).controller!.text, isEmpty);
      await _capture(tester, fixture.startsWith('annual') ? 'redeem-success' : 'redeem-trial-success');
      expect(tester.takeException(), isNull);
    });
  }

  for (final status in [400, 409, 422, 429, 502, null]) {
    testWidgets('refusal/network $status preserves subscription/allowance and input; no checkout', (tester) async {
      var reads = 0;
      final usage = _Usage(
          redeemCodeRequest: (_, {canSend}) async => ApiFailure(
              ApiProblem(status == null ? ApiProblemKind.transport : ApiProblemKind.rejected, statusCode: status)),
          subscriptionRequest: () async {
            reads++;
            return _snapshot();
          })
        ..debugSetSubscription(_snapshot());
      final original = usage.subscription;
      await _pump(tester, usage);
      await tester.enterText(find.byKey(_field), 'SYNTHETIC');
      await tester.pump();
      await tester.ensureVisible(find.byKey(_apply));
      await tester.pump();
      await tester.tap(find.byKey(_apply));
      await tester.pump();
      await tester.pump();
      final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
      final message = l10n.subscriptionCodeResult(status == 400 || status == 422
          ? 'refused'
          : status == 409
              ? 'conflict'
              : status == 429
                  ? 'rateLimited'
                  : 'error');
      expect(find.text(message), findsOneWidget);
      expect(reads, 0);
      expect(usage.subscription, same(original));
      expect(TranscriptionAllowanceCache.current, same(_originalAllowance));
      expect(usage.checkouts, 0);
      expect(usage.upgrades, 0);
      expect(find.byKey(const ValueKey('plans_sheet_code_applied')), findsNothing);
      if (status == 409) await _capture(tester, 'redeem-error');
      if (status == 429) {
        expect(tester.widget<OmiButton>(find.byKey(_apply)).onPressed, isNull);
        await tester.pumpWidget(const SizedBox()); // disposes the owned cooldown timer
      }
      expect(tester.takeException(), isNull);
    });
  }

  for (final state in ['cancel', 'no-sub', 'inactive']) {
    testWidgets('$state retains checkout promo field but cannot submit a redemption', (tester) async {
      var calls = 0;
      final usage = _Usage(
          redeemCodeRequest: (_, {canSend}) async {
            calls++;
            return const ApiSuccess(true);
          },
          subscriptionRequest: () async => _snapshot())
        ..debugSetSubscription(
            _snapshot(cancel: state == 'cancel', hasSub: state != 'no-sub', active: state != 'inactive'));
      await _pump(tester, usage);
      expect(find.byKey(_field), findsOneWidget);
      expect(find.byKey(_apply), findsNothing);
      expect(tester.widget<TextField>(find.byKey(_field)).onSubmitted, isNull);
      expect(await usage.redeemUserSubscriptionCode('SYNTHETIC'), isA<ApiFailure<bool>>());
      expect(calls, 0);
      if (state != 'inactive') {
        await tester.enterText(find.byKey(_field), 'SYNTHETIC');
        await tester.pump();
        final action =
            find.byKey(ValueKey(state == 'cancel' ? 'plans_sheet_resubscribe_button' : 'plans_sheet_upgrade_button'));
        await tester.ensureVisible(action);
        await tester.pump();
        await tester.tap(action);
        await tester.pump();
        await tester.pump();
        expect(usage.checkouts, 1);
        expect(usage.checkoutCodes, ['SYNTHETIC']);
        expect(calls, 0);
      }
    });
  }
}

Future<void> _loadFont(String family, File file) async {
  await (FontLoader(family)..addFont(Future.value(ByteData.sublistView(file.readAsBytesSync())))).load();
}

File? _packageAsset(String package, String asset) {
  final config = File('.dart_tool/package_config.json');
  final packages = (jsonDecode(config.readAsStringSync()) as Map)['packages'] as List;
  for (final entry in packages) {
    if (entry['name'] != package) continue;
    final root = config.parent.uri.resolveUri(Uri.parse(entry['rootUri'] as String));
    final file = File.fromUri(root.resolve(asset));
    if (file.existsSync()) return file;
  }
  return null;
}

File _materialIconsFont() {
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10; i++) {
    for (final relative in [
      'artifacts/material_fonts/MaterialIcons-Regular.otf',
      'material_fonts/MaterialIcons-Regular.otf'
    ]) {
      final file = File('${dir.path}/$relative');
      if (file.existsSync()) return file;
    }
    if (dir.path == dir.parent.path) break;
    dir = dir.parent;
  }
  throw StateError('Material icon font unavailable');
}
