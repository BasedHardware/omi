import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/l10n/app_localizations_en.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/onboarding/find_device/pairing_failure_card.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/pairing_failure.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

import '../../integration_test/visual_audit/fakes.dart' show AuditDeviceProvider;

typedef Reason = DeviceConnectFailureShownFailureReason;

Widget host(Widget child, {double scale = 1, TargetPlatform platform = TargetPlatform.iOS}) {
  final theme = buildOmiTheme(brightness: Brightness.light);
  final font = platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto';
  return MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: theme.copyWith(
        platform: platform,
        textTheme: theme.textTheme.apply(fontFamily: font),
        appBarTheme: theme.appBarTheme.copyWith(titleTextStyle: OmiType.headline.copyWith(fontFamily: font))),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: Builder(
        builder: (context) => MediaQuery(
              data: MediaQuery.of(context).copyWith(
                  textScaler: TextScaler.linear(scale),
                  padding: const EdgeInsets.only(top: 59, bottom: 34),
                  viewPadding: const EdgeInsets.only(top: 59, bottom: 34)),
              child: Scaffold(body: child),
            )),
  );
}

Widget survey() => Stack(children: [
      Positioned.fill(child: Image.asset(Assets.images.onboardingBg1.path, fit: BoxFit.cover)),
      OnboardingStepLayout(
          reserveHeader: false,
          onBack: () {},
          progress: const OnboardingProgressDots(current: 2, total: 5),
          child: FoundOmiWidget(goNext: () {}, saveSource: (_) async => true)),
    ]);

class PairingProvider extends BaseProvider with MessageNotifierMixin implements OnboardingProvider {
  @override
  Reason? pairingFailureReason;
  @override
  int pairingFailureVersion = 0;
  @override
  bool isConnected = false;
  @override
  String deviceName = '';
  @override
  DeviceType? deviceType;
  @override
  bool enableInstructions = false;
  @override
  List<BtDevice> deviceList = [];
  @override
  List<BtDevice> get visibleDeviceList => [];
  @override
  int get nearbyDeviceCount => 0;
  @override
  void dismissPairingFailure() {
    pairingFailureReason = null;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}
  @override
  void cancelActiveScan() {}
}

class PairingHomeProvider extends HomeProvider {
  @override
  Future<void> setupHasSpeakerProfile() async {}
}

Widget connect(OnboardingProvider pairing) => MultiProvider(providers: [
      ChangeNotifierProvider<OnboardingProvider>.value(value: pairing),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => AuditDeviceProvider()),
      ChangeNotifierProvider<HomeProvider>(create: (_) => PairingHomeProvider()),
    ], child: const ConnectDevicePage());

Future<void> loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final name in ['.SF UI Text', '.SF UI Display', '.SF Pro Text', 'CupertinoSystemText']) {
    final loader = FontLoader(name)..addFont(rootBundle.load('assets/fonts/SFPRODISPLAYREGULAR.OTF'));
    await loader.load();
  }
  var dir = File(Platform.resolvedExecutable).parent;
  Directory? fonts;
  for (var i = 0; i < 8; i++) {
    final candidate = Directory('${dir.path}/material_fonts');
    if (File('${candidate.path}/Roboto-Regular.ttf').existsSync()) {
      fonts = candidate;
      break;
    }
    dir = dir.parent;
  }
  expect(fonts, isNotNull);
  final loader = FontLoader('Roboto');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    loader.addFont(Future.value(ByteData.sublistView(File('${fonts!.path}/Roboto-$weight.ttf').readAsBytesSync())));
  }
  await loader.load();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  void viewport(WidgetTester tester) {
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  test('classification uses exposed states; null connection is one reachability bucket', () {
    expect(connectFailureReason(StateError('Device initialization did not complete')), Reason.notFoundOrDropped);
    expect(connectFailureReason(TimeoutException('timeout')), Reason.notFoundOrDropped);
    expect(
        connectFailureReason(StateError('Device initialization did not complete'), staleBond: true), Reason.staleBond);
    expect(connectFailureReason(const BluetoothAdapterUnavailableException(BluetoothAdapterState.off)),
        Reason.bluetoothOff);
    expect(connectFailureReason(const BluetoothAdapterUnavailableException(BluetoothAdapterState.unauthorized)),
        Reason.bluetoothPermissionDenied);
    for (final state in [BluetoothAdapterState.off, BluetoothAdapterState.unauthorized]) {
      expect(connectFailureReason(BluetoothAdapterUnavailableException(state), staleBond: true),
          state == BluetoothAdapterState.off ? Reason.bluetoothOff : Reason.bluetoothPermissionDenied);
    }
    expect(connectFailureReason(Exception('unknown')), Reason.unknown);
    expect(connectFailureReason(StateError('unrelated')), Reason.unknown);
    expect(blockedFailureReason(DevicePairingBlockedReason.nearbyDevicesDenied), Reason.nearbyDevicesDenied);
    expect(
        blockedFailureReason(DevicePairingBlockedReason.locationPermissionMissing), Reason.locationPermissionMissing);
    expect(blockedFailureReason(DevicePairingBlockedReason.bluetoothOff, adapterState: BluetoothAdapterState.off),
        Reason.bluetoothOff);
    for (final state in [
      BluetoothAdapterState.unknown,
      BluetoothAdapterState.unsupported,
      BluetoothAdapterState.resetting
    ]) {
      expect(blockedFailureReason(DevicePairingBlockedReason.bluetoothOff, adapterState: state), Reason.unknown);
    }
    expect(blockedFailureReason(DevicePairingBlockedReason.noAdapter), Reason.unknown);
    expect(blockedFailureReason(DevicePairingBlockedReason.scannerUnavailable), Reason.unknown);
  });

  testWidgets('every failure reason displays its actionable copy and emits once per presentation', (tester) async {
    viewport(tester);
    final l10n = AppLocalizationsEn();
    final copies = {
      Reason.bluetoothOff: 'Turn on Bluetooth on your phone, then try again.',
      Reason.bluetoothPermissionDenied: 'Allow Bluetooth access for Omi in Settings, then try again.',
      Reason.nearbyDevicesDenied: 'Allow Nearby devices access for Omi in Settings, then try again.',
      Reason.locationPermissionMissing:
          'Allow location access for Omi in Settings so this phone can find your device, then try again.',
      Reason.notFoundOrDropped:
          "Couldn't reach your Omi. Make sure it's charged, close to your phone, and its light is blinking, then try again.",
      Reason.staleBond: 'Forget Omi in your phone’s Bluetooth settings, then try pairing again.',
      Reason.unknown: 'An error occurred. Please try again.',
    };
    for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
      final events = <RegisteredEvent>[];
      for (final reason in Reason.values) {
        var dismissed = 0, guides = 0;
        Widget page() => Center(
            child: PairingFailureCard(
                key: ValueKey(reason),
                reason: reason,
                onDismiss: () => dismissed++,
                onGuide: () => guides++,
                emit: events.add));
        await tester.pumpWidget(host(page(), platform: platform));
        expect(pairingFailureCopy(l10n, reason), copies[reason]);
        expect(find.text(copies[reason]!), findsOneWidget);
        final count = events.length;
        await tester.pumpWidget(host(page(), platform: platform));
        await tester.pump();
        expect(events.length, count);
        expect(events.last.wireName, 'Device Connect Failure Shown');
        expect(events.last.properties,
            {'failure_reason': reason.wireName, 'platform': platform == TargetPlatform.iOS ? 'ios' : 'android'});
        await tester.tap(find.byKey(const Key('pairing_failure_guide')));
        await tester.pump();
        expect(guides, 1);
        await tester.tap(find.byKey(const Key('pairing_failure_dismiss')));
        expect(dismissed, 1);
        expect(tester.takeException(), isNull);
      }
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('device-first step: Connect is the primary at the bottom inset, store and skip sit under it',
      (tester) async {
    viewport(tester);
    final l10n = AppLocalizationsEn();
    await tester.pumpWidget(host(OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (_, __) {})));
    expect(find.text(l10n.firstCaptureConnectTitle), findsOneWidget);
    expect(find.text(l10n.firstCaptureConnect), findsOneWidget);
    expect(find.text(l10n.firstCaptureNoDevice), findsOneWidget);
    expect(find.text(l10n.firstCaptureSkip), findsOneWidget);
    final connect = tester.getRect(find.byKey(const Key('first_capture_omi')));
    final shop = tester.getRect(find.byKey(const Key('first_capture_shop')));
    final skip = tester.getRect(find.byKey(const Key('onboarding_complete_start')));
    expect(connect.bottom, lessThan(shop.top));
    expect(shop.bottom, lessThan(skip.top));
    expect(skip.bottom, closeTo(802, 1));
    expect(tester.takeException(), isNull);
    await tester
        .pumpWidget(host(OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (_, __) {}), scale: 2));
    expect(find.byKey(const Key('onboarding_complete_start')).hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('all twelve survey choices fit above Continue at 393x852; large text scrolls', (tester) async {
    viewport(tester);
    await tester.runAsync(() => loadFonts());
    final l10n = AppLocalizationsEn();
    final labels = [
      l10n.tiktok,
      l10n.youtube,
      l10n.instagram,
      l10n.xTwitter,
      l10n.reddit,
      l10n.linkedIn,
      l10n.friendWordOfMouth,
      l10n.coworker,
      l10n.event,
      l10n.appStore,
      l10n.googleSearch,
      l10n.otherSource
    ];
    await tester.pumpWidget(host(survey()));
    final footerTop = tester.getRect(find.byKey(const Key('found_omi_continue'))).top;
    for (final label in labels) {
      expect(find.text(label).hitTestable(), findsOneWidget, reason: label);
      expect(tester.getRect(find.text(label)).bottom, lessThan(footerTop), reason: label);
    }
    final scroll = tester.state<ScrollableState>(find.byType(Scrollable));
    expect(scroll.position.maxScrollExtent, 0);
    await tester.pumpWidget(host(survey(), scale: 2));
    expect(tester.state<ScrollableState>(find.byType(Scrollable)).position.maxScrollExtent, greaterThan(0));
    expect(find.byKey(const Key('found_omi_continue')).hitTestable(), findsOneWidget);
    await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -1600));
    await tester.pumpAndSettle();
    expect(find.text(l10n.otherSource).hitTestable(), findsOneWidget);
    expect(find.text(l10n.googleSearch).hitTestable(), findsOneWidget);
    await tester.tap(find.text(l10n.otherSource));
    await tester.pump();
    await tester.ensureVisible(find.byType(TextField));
    expect(find.byType(TextField).hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('connection card is in the connect flow and dismisses without leaving it', (tester) async {
    viewport(tester);
    final pairing = PairingProvider()..pairingFailureReason = Reason.staleBond;
    await tester.pumpWidget(host(connect(pairing)));
    await tester.pump();
    expect(find.byType(PairingFailureCard), findsOneWidget);
    await tester.tap(find.byKey(const Key('pairing_failure_dismiss')));
    await tester.pump();
    expect(find.byType(PairingFailureCard), findsNothing);
    expect(find.byType(ConnectDevicePage), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    pairing.dispose();
  });

  testWidgets('render onboarding polish with real fonts on both platforms', (tester) async {
    if (Platform.environment['ONB_POLISH_RENDER'] != '1') return;
    viewport(tester);
    await tester.runAsync(() => loadFonts());
    const boundary = Key('polish-render');
    for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
      debugDefaultTargetPlatformOverride = platform;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final tag = platform == TargetPlatform.iOS ? 'ios' : 'android';
      Future<void> render(String name, Widget child, {double scale = 1, bool scrollToEnd = false}) async {
        await tester.pumpWidget(const SizedBox());
        await tester.pumpWidget(RepaintBoundary(key: boundary, child: host(child, platform: platform, scale: scale)));
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump(const Duration(milliseconds: 400));
        if (scrollToEnd) {
          await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -1600));
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull, reason: '$tag-$name');
        await tester.runAsync(() async {
          final image = tester.element(find.byKey(boundary)).renderObject! as RenderRepaintBoundary;
          final png = await (await image.toImage(pixelRatio: 3)).toByteData(format: ui.ImageByteFormat.png);
          final ordinal = name == 'device-first'
              ? 1
              : name.startsWith('connect-')
                  ? Reason.values.indexWhere((reason) => name == 'connect-${reason.wireName}') +
                      (platform == TargetPlatform.iOS ? 2 : 12)
                  : ['find-us', 'find-us-large', 'find-us-large-end'].indexOf(name) +
                      (platform == TargetPlatform.iOS ? 9 : 19);
          final filename = '${ordinal.toString().padLeft(3, '0')}-mobile-$tag-${name.replaceAll('_', '-')}.png';
          final file = File('../.agent-artifacts/ui-evidence/onb-polish/$filename');
          file.parent.createSync(recursive: true);
          file.writeAsBytesSync(png!.buffer.asUint8List());
        });
      }

      if (platform == TargetPlatform.iOS) {
        await render(
            'device-first', OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (_, __) {}));
      }
      for (final reason in Reason.values) {
        final pairing = PairingProvider()..pairingFailureReason = reason;
        await render('connect-${reason.wireName}', connect(pairing));
        await tester.pumpWidget(const SizedBox());
        pairing.dispose();
      }
      await render('find-us', survey());
      await render('find-us-large', survey(), scale: 2);
      await render('find-us-large-end', survey(), scale: 2, scrollToEnd: true);
    }
    debugDefaultTargetPlatformOverride = null;
  });
}
