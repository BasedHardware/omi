import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/payments/stripe_connect_setup.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/pages/settings/ai_app_generator_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

final _l10n = lookupAppLocalizations(const Locale('en'));
const _accountLink = 'https://connect.stripe.com/setup/e/acct_secret_link';

class _Temporary extends PathProviderPlatform {
  _Temporary(this.path);
  final String path;

  @override
  Future<String?> getTemporaryPath() async => path;
}

/// The generator owner with its network steps replaced; every value the page reads is settable.
class _FakeGenerator extends AiAppGeneratorProvider {
  GenerationState fakeState = GenerationState.idle;
  GenerationStep step = GenerationStep.creatingPlan;
  String? name, description, error;
  String category = 'productivity-and-organization';
  List<String>? capabilities;
  Uint8List? icon;
  bool public = false, paid = false;
  double fakePrice = 0;
  int submits = 0, regenerates = 0, clears = 0;
  final prices = <double>[];
  final publics = <bool>[];
  final paids = <bool>[];

  @override
  GenerationState get state => fakeState;
  @override
  GenerationStep get currentStep => step;
  @override
  int get currentStepIndex => step.index;
  @override
  String? get errorMessage => error;
  @override
  String? get generatedName => name;
  @override
  String? get generatedDescription => description;
  @override
  String? get generatedCategory => name == null ? null : category;
  @override
  List<String>? get generatedCapabilities => capabilities;
  @override
  Uint8List? get generatedIconBytes => icon;
  @override
  bool get makePublic => public;
  @override
  bool get isPaid => paid;
  @override
  double get price => fakePrice;
  @override
  List<String> get samplePrompts => const ['A gratitude journal', 'A focus coach'];
  @override
  bool get isLoadingPrompts => false;
  @override
  bool get isLoading => isGenerating || fakeState == GenerationState.submitting;
  @override
  bool get isGenerating => fakeState == GenerationState.generatingApp || fakeState == GenerationState.generatingIcon;
  @override
  bool get hasGeneratedApp => name != null && description != null && icon != null && !isGenerating;

  @override
  Future<void> fetchSamplePrompts() async {}

  void generated(Uint8List bytes) {
    fakeState = GenerationState.idle;
    name = 'Focus Coach';
    description = 'Keeps you on track';
    capabilities = ['chat', 'memories'];
    icon = bytes;
    notifyListeners();
  }

  @override
  Future<bool> regenerateIcon() async {
    regenerates++;
    icon = Uint8List.fromList([...icon!, regenerates]);
    notifyListeners();
    return true;
  }

  @override
  Future<String?> submitGeneratedApp() async {
    submits++;
    return null;
  }

  @override
  void setMakePublic(bool value) {
    publics.add(value);
    public = value;
    notifyListeners();
  }

  @override
  void setIsPaid(bool value) {
    paids.add(value);
    paid = value;
    notifyListeners();
  }

  @override
  void setPrice(double value) {
    prices.add(value);
    fakePrice = value;
    notifyListeners();
  }

  @override
  void clear() {
    clears++;
    fakeState = GenerationState.idle;
    name = description = error = null;
    capabilities = icon = null;
    notifyListeners();
  }
}

/// The payout owner with its backend calls replaced.
class _FakePayments extends PaymentMethodProvider {
  PaymentMethodType? active;
  bool connected = false, polling = false, loading = false;
  PaymentConnectionState connection = PaymentConnectionState.notConnected;
  List<Map<String, dynamic>> countries = [
    {'id': 'US', 'name': 'United States'},
    {'id': 'DE', 'name': 'Germany'},
  ];
  final setActive = <PaymentMethodType>[];
  int statusLoads = 0, pollStarts = 0, pollStops = 0, links = 0;

  @override
  PaymentMethodType? get activeMethod => active;
  @override
  bool get isStripeConnected => connected;
  @override
  bool get isStripePolling => polling;
  @override
  bool get isLoading => loading;
  @override
  PaymentConnectionState get stripeConnectionState => connection;
  @override
  List<Map<String, dynamic>> get supportedCountries => countries;

  @override
  Future getSupportedCountries() async {}
  @override
  Future getPaymentMethodsStatus() async => statusLoads++;
  @override
  void setActiveMethod(PaymentMethodType method) => setActive.add(method);
  @override
  Future<String?> connectStripe() async {
    links++;
    return _accountLink;
  }

  @override
  void startStripePolling() {
    pollStarts++;
    polling = true;
    notifyListeners();
  }

  @override
  void stopStripePolling() {
    pollStops++;
    // The page also stops polling from dispose, while the tree is locked; only a change notifies.
    if (!polling) return;
    polling = false;
    notifyListeners();
  }
}

final class _AnotherOwner implements AuthTokenGateway {
  const _AnotherOwner();

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'another-owner');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

class _Opener extends StatelessWidget {
  const _Opener(this.page);
  final Widget page;

  @override
  Widget build(BuildContext context) => Scaffold(
      body: TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page)),
          child: const Text('open')));
}

void main() {
  late Directory temporary;
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    temporary = Directory.systemTemp.createTempSync('omi-generator-native-test');
    final previous = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Temporary(temporary.path);
    addTearDown(() {
      PathProviderPlatform.instance = previous;
      if (temporary.existsSync()) temporary.deleteSync(recursive: true);
    });
  });

  Future<void> pumpPage(WidgetTester tester, Widget page, {PaymentMethodProvider? payments}) async {
    final apps = AppProvider();
    final owner = payments ?? _FakePayments();
    addTearDown(apps.dispose);
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
          ChangeNotifierProvider<AppProvider>.value(value: apps),
          ChangeNotifierProvider<PaymentMethodProvider>.value(value: owner),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: _Opener(page))));
    await tester.tap(find.text('open'));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(milliseconds: 400));
    await NativeTestHost.settle(tester);
  }

  /// Completes a pop transition and removes the route.
  Future<void> settleRoute(WidgetTester tester) async {
    for (var frame = 0; frame < 10; frame++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  /// Lets real file I/O finish, then rebuilds.
  /// [until] bounds the wait for slow machines; without it, a fixed number of rounds runs.
  Future<void> settleIo(WidgetTester tester, {bool Function()? until}) async {
    for (var i = 0; i < (until == null ? 25 : 250); i++) {
      if (until != null && i >= 25 && until()) return;
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pump();
    }
    if (until != null && !until()) fail('Timed out waiting for the temporary icon file');
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last);

  List<NativeRow> rows(WidgetTester tester) {
    final current = surface(tester);
    return [...current.toolbar, ...current.sections.expand((section) => section.rows)];
  }

  NativeRow row(WidgetTester tester, String id) => rows(tester).singleWhere((row) => row.id == id);

  Iterable<String> ids(WidgetTester tester) => rows(tester).map((row) => row.id);

  /// Everything the mounted native views were sent, plus the current creation snapshot.
  String everySnapshot(WidgetTester tester, NativeTestHost host) => jsonEncode([
        for (final call in host.calls) call.$2.arguments,
        for (final view in tester.widgetList<UiKitView>(find.byType(UiKitView))) view.creationParams,
      ]);

  /// Delivers an action the way the mounted SwiftUI view does, through the view's channel.
  Future<void> fromNative(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
    expect(find.byType(UiKitView), findsOneWidget, reason: 'The screen is native');
    await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
    await tester.pump();
  }

  String? previewFile(WidgetTester tester) {
    final uri = row(tester, 'ai_gen_preview').imageUri;
    return uri == null ? null : Uri.parse(uri).toFilePath();
  }

  group('AI app generator', () {
    // A real 1×1 PNG, so the classic preview can decode it too.
    final iconBytes =
        base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=');

    Future<_FakeGenerator> pumpGenerator(WidgetTester tester) async {
      final generator = _FakeGenerator();
      await pumpPage(tester, AiAppGeneratorPage(createProvider: () => generator));
      expect(find.byType(UiKitView), findsOneWidget, reason: 'The generator starts native');
      return generator;
    }

    testWidgets('every state projects without the icon bytes or base64', (tester) async {
      final host = NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      expect(surface(tester).title, _l10n.aiAppGeneratorBannerTitle);
      expect(ids(tester), containsAll(['ai_gen_back', 'ai_gen_prompt:0', 'ai_gen_prompt:1', 'ai_gen_prompt_text']));
      expect(row(tester, 'ai_gen_send').projection['enabled'], isFalse, reason: 'Send needs a prompt');

      await row(tester, 'ai_gen_prompt:1').action!(null);
      await tester.pump();
      expect(row(tester, 'ai_gen_prompt_text').value, 'A focus coach');
      expect(row(tester, 'ai_gen_send').projection['enabled'], isTrue);

      generator
        ..fakeState = GenerationState.generatingIcon
        ..step = GenerationStep.generatingIcon
        ..name = 'Focus Coach'
        ..capabilities = ['chat']
        ..notifyListeners();
      await tester.pump();
      expect(surface(tester).loading, isTrue);
      final progress = row(tester, 'ai_gen_progress');
      expect([progress.value, progress.maximumValue, progress.subtitle], [4.0, 5.0, '80%']);
      expect(row(tester, 'ai_gen_step:designingApp').symbol, 'checkmark.circle.fill');
      expect(row(tester, 'ai_gen_step:generatingIcon').symbol, 'circle.dotted');
      expect(row(tester, 'ai_gen_step:generatingIcon').subtitle, _l10n.processing);
      expect(row(tester, 'ai_gen_step:finalTouches').symbol, 'circle');
      expect(rows(tester).every((row) => row.valid), isTrue);

      generator.generated(iconBytes);
      await settleIo(tester, until: () => previewFile(tester) != null);
      expect(surface(tester).title, 'Focus Coach');
      expect(ids(tester), containsAll(['ai_gen_beta', 'ai_gen_regenerate_icon', 'ai_gen_public', 'ai_gen_paid']));
      expect(previewFile(tester), isNotNull);
      expect(File(previewFile(tester)!).readAsBytesSync(), iconBytes);

      await row(tester, 'ai_gen_paid').action!(true);
      await tester.pump();
      await row(tester, 'ai_gen_price').action!('4.5');
      await row(tester, 'ai_gen_public').action!(true);
      await tester.pump();
      expect(row(tester, 'ai_gen_price').keyboard, 'decimal');
      expect([
        generator.paids,
        generator.prices,
        generator.publics
      ], [
        [true],
        [4.5],
        [true]
      ]);
      await row(tester, 'ai_gen_price').action!('abc');
      expect(generator.prices.last, 0);
      await row(tester, 'ai_gen_paid').action!(false);
      await tester.pump();
      await row(tester, 'ai_gen_paid').action!(true);
      await tester.pump();
      expect(row(tester, 'ai_gen_price').value, '', reason: 'The price field reappears empty');

      final sent = everySnapshot(tester, host);
      expect(sent, isNot(contains(base64Encode(iconBytes))));
      expect(sent, isNot(contains(base64Encode(iconBytes).substring(0, 24))));
      expect(sent, isNot(contains('data:image')));
      expect(row(tester, 'ai_gen_preview').imageUri, startsWith('file:///'));
    });

    testWidgets('the temporary icon is replaced on regenerate and deleted on clear', (tester) async {
      NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      generator.generated(iconBytes);
      await settleIo(tester, until: () => previewFile(tester) != null);
      final first = previewFile(tester)!;
      expect(File(first).existsSync(), isTrue);

      await row(tester, 'ai_gen_regenerate_icon').action!(null);
      await settleIo(tester, until: () => previewFile(tester) != null && previewFile(tester) != first);
      final second = previewFile(tester)!;
      expect(second, isNot(first), reason: 'Each icon gets a new file name');
      expect(File(first).existsSync(), isFalse);
      expect(File(second).existsSync(), isTrue);

      // Back from the generated app clears it and stays on the page.
      await row(tester, 'ai_gen_back').action!(null);
      await settleIo(tester);
      expect(generator.clears, 1);
      expect(find.byType(AiAppGeneratorPage), findsOneWidget);
      expect(tester.state<NavigatorState>(find.byType(Navigator)).canPop(), isTrue, reason: 'Back did not pop');
      expect(surface(tester).title, _l10n.aiAppGeneratorBannerTitle);
      expect(File(second).existsSync(), isFalse);
    });

    testWidgets('icons an interrupted earlier page left behind are purged, the new icon kept', (tester) async {
      NativeTestHost.install();
      final stale = File('${temporary.path}/omi_ai_generator/icon_stale.png')
        ..createSync(recursive: true)
        ..writeAsBytesSync(iconBytes);
      final generator = await pumpGenerator(tester);
      generator.generated(iconBytes);
      await settleIo(tester, until: () => previewFile(tester) != null);
      expect(stale.existsSync(), isFalse);
      expect(File(previewFile(tester)!).existsSync(), isTrue);
    });

    testWidgets('the temporary icon is deleted when the page is disposed', (tester) async {
      NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      generator.generated(iconBytes);
      await settleIo(tester, until: () => previewFile(tester) != null);
      final file = previewFile(tester)!;
      await tester.pumpWidget(const SizedBox());
      await settleIo(tester);
      expect(File(file).existsSync(), isFalse);
    });

    testWidgets('an icon replaced while its file is still being written leaves nothing behind', (tester) async {
      NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      generator.generated(iconBytes);
      // The first write is still pending when the regenerated icon arrives; it completes stale.
      await generator.regenerateIcon();
      await settleIo(tester, until: () => previewFile(tester) != null);
      await settleIo(tester);
      final files = Directory('${temporary.path}/omi_ai_generator').listSync().whereType<File>().map((f) => f.path);
      expect(files, [previewFile(tester)]);
      expect(File(previewFile(tester)!).readAsBytesSync(), generator.icon);
    });

    testWidgets('the temporary icon is deleted when the account session changes', (tester) async {
      NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      generator.generated(iconBytes);
      await settleIo(tester, until: () => previewFile(tester) != null);
      final file = previewFile(tester)!;
      AuthService.installLocalHarnessTokenGateway(const _AnotherOwner());
      AuthService.instance.captureSessionSnapshot();
      await settleIo(tester);
      expect(File(file).existsSync(), isFalse);
      // A later icon from the previous owner's page is never written.
      await generator.regenerateIcon();
      await settleIo(tester);
      expect(temporary.listSync(recursive: true).whereType<File>(), isEmpty);
    });

    testWidgets('Create submits once through the existing owner', (tester) async {
      NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      generator.generated(iconBytes);
      await settleIo(tester, until: () => previewFile(tester) != null);
      expect(row(tester, 'ai_gen_create').projection['enabled'], isTrue);
      await row(tester, 'ai_gen_create').action!(null);
      await tester.pump();
      expect(generator.submits, 1);
    });

    testWidgets('the prompt back clears and leaves the page', (tester) async {
      NativeTestHost.install();
      final generator = await pumpGenerator(tester);
      await row(tester, 'ai_gen_back').action!(null);
      await settleRoute(tester);
      expect(generator.clears, 1);
      expect(find.byType(AiAppGeneratorPage), findsNothing);
    });

    testWidgets('a prompt over 10000 characters keeps the classic composer', (tester) async {
      NativeTestHost.install();
      await pumpGenerator(tester);
      await row(tester, 'ai_gen_prompt_text').action!('a' * 10000);
      await tester.pump();
      expect(find.byType(UiKitView), findsOneWidget);
      await row(tester, 'ai_gen_prompt_text').action!('a' * 10001);
      await tester.pump();
      expect(find.byType(UiKitView), findsNothing);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('flag off keeps the classic generator and writes no icon file', (tester) async {
      final generator = _FakeGenerator();
      await pumpPage(tester, AiAppGeneratorPage(createProvider: () => generator));
      generator.generated(iconBytes);
      await settleIo(tester);
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(find.text(_l10n.createApp), findsOneWidget);
      expect(temporary.listSync(recursive: true), isEmpty);
    });
  });

  group('Payouts', () {
    testWidgets('no active method (PayPal counts as none) offers Connect', (tester) async {
      NativeTestHost.install();
      final payments = _FakePayments()..active = PaymentMethodType.paypal;
      await pumpPage(tester, const PaymentsPage(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(surface(tester).title, _l10n.payments);
      expect(ids(tester), ['payout_back', 'payout_info', 'payout_connect:stripe', 'payout_coming_soon']);
      expect(row(tester, 'payout_connect:stripe').kind, 'navigation');
      expect(row(tester, 'payout_connect:stripe').subtitle, _l10n.paymentStatusNotConnected);
      expect(payments.statusLoads, 1);
      await surface(tester).onRefresh!(null);
      expect(payments.statusLoads, 2);
    });

    testWidgets('a connected inactive Stripe offers update and set active', (tester) async {
      final host = NativeTestHost.install();
      final payments = _FakePayments()..connected = true;
      await pumpPage(tester, const PaymentsPage(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      final method = row(tester, 'payout_method:stripe');
      expect(method.kind, 'menu');
      expect(method.options.keys, ['update', 'set_active']);
      expect(ids(tester), contains('payout_info'));
      await fromNative(tester, host, 'payout_method:stripe', 'set_active');
      expect(payments.setActive, [PaymentMethodType.stripe]);
    });

    testWidgets('an active Stripe shows its status and Update', (tester) async {
      NativeTestHost.install();
      final payments = _FakePayments()
        ..connected = true
        ..active = PaymentMethodType.stripe;
      await pumpPage(tester, const PaymentsPage(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(ids(tester), ['payout_back', 'payout_active:stripe', 'payout_update:stripe', 'payout_coming_soon']);
      expect(row(tester, 'payout_active:stripe').symbol, 'checkmark.seal.fill');
      await row(tester, 'payout_update:stripe').action!(null);
      await NativeTestHost.settle(tester);
      expect(find.byType(StripeConnectSetup), findsOneWidget);
    });
  });

  group('Stripe Connect setup', () {
    List<String> mockLauncher() {
      const channel = MethodChannel('plugins.flutter.io/url_launcher');
      final launched = <String>[];
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.arguments is Map && (call.arguments as Map)['url'] is String) {
          launched.add((call.arguments as Map)['url'] as String);
        }
        return true;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
      return launched;
    }

    testWidgets('the country choice ignores the unset option and Connect needs a country', (tester) async {
      final host = NativeTestHost.install();
      final payments = _FakePayments();
      await pumpPage(tester, const StripeConnectSetup(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      final country = row(tester, 'stripe_country');
      expect(country.options.keys, ['__unset__', 'US', 'DE']);
      expect(country.options['US'], '🇺🇸 United States');
      expect(country.value, '__unset__');
      expect(row(tester, 'stripe_connect').projection['enabled'], isFalse);

      await fromNative(tester, host, 'stripe_country', '__unset__');
      expect(payments.selectedCountryId, isNull, reason: 'The unset option never sets a country');
      await fromNative(tester, host, 'stripe_country', 'US');
      expect(payments.selectedCountryId, 'US');
      expect(row(tester, 'stripe_country').value, 'US');
      await fromNative(tester, host, 'stripe_country', '__unset__');
      expect(payments.selectedCountryId, 'US', reason: 'The unset option never clears or sets a country');
      expect(row(tester, 'stripe_connect').projection['enabled'], isTrue);
      expect(find.byType(UiKitView), findsOneWidget);
    });

    testWidgets('loading the countries never shows the native spinner', (tester) async {
      NativeTestHost.install();
      final payments = _FakePayments()..loading = true;
      await pumpPage(tester, const StripeConnectSetup(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(surface(tester).loading, isFalse, reason: 'The country fetch does not reliably notify its end');
    });

    testWidgets('the account link never reaches a snapshot', (tester) async {
      final host = NativeTestHost.install();
      final launched = mockLauncher();
      final payments = _FakePayments()..setSelectedCountryId('US');
      await pumpPage(tester, const StripeConnectSetup(), payments: payments);
      await fromNative(tester, host, 'stripe_connect');
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Polling stays native');
      expect([payments.links, payments.pollStarts], [1, 1]);
      expect(ids(tester), containsAll(['stripe_retry', 'stripe_later']));
      expect(surface(tester).loading, isTrue);
      expect(launched, [_accountLink], reason: 'The link goes only to the external browser');
      expect(everySnapshot(tester, host), isNot(contains('acct_secret_link')));
    });

    testWidgets('leaving stops polling', (tester) async {
      NativeTestHost.install();
      final payments = _FakePayments()..polling = true;
      await pumpPage(tester, const StripeConnectSetup(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      // Past the route transition, nothing animates while polling is shown natively.
      await tester.pump(const Duration(seconds: 1));
      expect(tester.binding.transientCallbackCount, 0, reason: 'No classic pulse ticks under the native surface');
      await row(tester, 'stripe_back').action!(null);
      await settleRoute(tester);
      expect(find.byType(StripeConnectSetup), findsNothing);
      expect(payments.pollStops, greaterThanOrEqualTo(1));
      expect(payments.polling, isFalse);
    });

    testWidgets('a connected account offers update and go back', (tester) async {
      NativeTestHost.install();
      final payments = _FakePayments()..connected = true;
      await pumpPage(tester, const StripeConnectSetup(), payments: payments);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(ids(tester), ['stripe_back', 'stripe_connected_status', 'stripe_update', 'stripe_go_back']);
      await row(tester, 'stripe_go_back').action!(null);
      await settleRoute(tester);

      expect(find.byType(StripeConnectSetup), findsNothing);
    });

    testWidgets('an invalid country id keeps the complete classic screen', (tester) async {
      NativeTestHost.install();
      final payments = _FakePayments()
        ..countries = [
          {'id': 'US', 'name': 'United States'},
          {'id': 'usa', 'name': 'Elsewhere'},
        ];
      await pumpPage(tester, const StripeConnectSetup(), payments: payments);
      expect(find.byType(UiKitView), findsNothing);
      expect(find.text(_l10n.connectNow), findsOneWidget);
    });
  });

  group('Start earning', () {
    const config = MethodChannel('com.omi.native_ui/config');

    Future<void> pumpPrompt(WidgetTester tester, Object? Function() reply) async {
      messenger.setMockMethodCallHandler(config, (call) async {
        if (call.method != 'present') return null;
        final answer = reply();
        if (answer is PlatformException) throw answer;
        return answer;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(config, null));
      await pumpPage(
          tester,
          Builder(
              builder: (context) => Scaffold(
                  body: TextButton(onPressed: () => showStartEarningPrompt(context), child: const Text('earn')))));
      await tester.tap(find.text('earn'));
      await NativeTestHost.settle(tester);
      await tester.pump(const Duration(milliseconds: 400));
    }

    testWidgets('Connect now routes to payouts', (tester) async {
      NativeTestHost.install();
      await pumpPrompt(tester, () => {'action': 'connect', 'values': <String, Object?>{}});
      expect(find.byType(PaymentsPage), findsOneWidget);
    });

    testWidgets('Not now stays put', (tester) async {
      NativeTestHost.install();
      await pumpPrompt(tester, () => {'action': 'cancel', 'values': <String, Object?>{}});
      expect(find.byType(PaymentsPage), findsNothing);
      expect(find.text(_l10n.connectNow), findsNothing);
    });

    testWidgets('a refused presentation opens the classic sheet', (tester) async {
      NativeTestHost.install();
      await pumpPrompt(tester, () => PlatformException(code: 'invalid_native_presentation'));
      expect(find.text(_l10n.connectStripeOrPayPal), findsOneWidget);
      await tester.tap(find.text(_l10n.connectNow));
      await NativeTestHost.settle(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(PaymentsPage), findsOneWidget);
    });
  });
}
