import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/firmware_update_battery.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/firmware_update_dialog.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';

bool _offerZip = false;
void Function()? _onDownload;

class _EnvFields implements EnvFields {
  const _EnvFields();
  @override
  String get apiBaseUrl => 'http://firmware.test/';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _DeviceProvider extends DeviceProvider {
  _DeviceProvider({int batteryLevel = -1, bool isCharging = false}) {
    this.batteryLevel = batteryLevel;
    this.isCharging = isCharging;
  }
  int updateStarts = 0;
  int updateResets = 0;

  void sample(int battery, {bool charging = false}) {
    final chargingChanged = isCharging != charging;
    isCharging = charging;
    if (!updateBatteryLevelForTesting(battery) && chargingChanged) notifyListeners();
  }

  @override
  void setFirmwareUpdateInProgress(bool value) {
    if (value) updateStarts++;
  }

  @override
  void setOnFirmwareUpdatePage(bool value) {}
  @override
  void resetFirmwareUpdateState() => updateResets++;
}

class _NoConnectivity extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];
  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const output = String.fromEnvironment('FIRMWARE_BATTERY_RENDER_OUTPUT');
  final en = lookupAppLocalizations(const Locale('en'));
  final boundary = GlobalKey();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _NoConnectivity();
    await ServiceManager.init();
    Env.init(const _EnvFields());
    // All requests are answered in memory below, without credentials or sockets.
    Env.overrideApiBaseUrl('http://firmware.test/');
    PlatformManager.initializeForLocalHarness();
    PackageInfo.setMockInitialValues(
      appName: 'Omi',
      packageName: 'com.friend.ios.dev',
      version: '9.0.0',
      buildNumber: '9999',
      buildSignature: '',
    );
    HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _FirmwareHttpOverrides());
    if (output.isNotEmpty) await _loadFonts();
  });
  tearDownAll(() {
    HttpPoolManager.instance.dispose();
    Env.clearApiBaseUrlOverrideForTesting();
  });
  setUp(() {
    _offerZip = false;
    _onDownload = null;
  });

  Future<void> pumpPage(WidgetTester tester, _DeviceProvider provider,
      {bool rollback = false,
      Locale locale = const Locale('en'),
      String firmwareVersion = '2.0.10',
      bool expectOffer = true}) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final previousPalette = OmiColors.active;
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    addTearDown(() => OmiColors.active = previousPalette);
    addTearDown(provider.dispose);
    final theme = buildOmiTheme(brightness: Brightness.dark);
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: ChangeNotifierProvider<DeviceProvider>.value(
        value: provider,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          locale: locale,
          theme: theme.copyWith(
              appBarTheme: theme.appBarTheme.copyWith(
            titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
          )),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: FirmwareUpdate(
            isRollback: rollback,
            device: BtDevice(
                id: 'fixture-pendant',
                name: 'Omi',
                type: DeviceType.omi,
                rssi: -50,
                modelNumber: 'Omi',
                firmwareRevision: firmwareVersion),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('firmware_update_start')), expectOffer ? findsOneWidget : findsNothing);
  }

  OmiButton startButton(WidgetTester tester) => tester.widget(find.byKey(const Key('firmware_update_start')));

  Future<void> capture(WidgetTester tester, String filename) async {
    if (output.isEmpty) return;
    final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    _paintProductFont(render);
    await tester.pump();
    await tester.runAsync(() async {
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$filename').writeAsBytes(bytes!.buffer.asUint8List());
      image.dispose();
    });
  }

  for (final status in ['verifying', 'not-installed', 'no-reconnect', 'installed']) {
    testWidgets('OTA outcome renders $status', (tester) async {
      await pumpPage(tester, _DeviceProvider(batteryLevel: 80));
      final dynamic state = tester.state(find.byType(FirmwareUpdate));
      state.setState(() {
        state.isInstalling = status == 'verifying';
        state.isVerifying = status == 'verifying';
        state.installProgress = 100;
        state.isInstalled = status == 'installed';
        state.observedFirmwareVersion = status == 'no-reconnect'
            ? null
            : status == 'installed'
                ? '3.0.1'
                : '2.0.10';
        state.updateFailure = switch (status) {
          'not-installed' => FirmwareUpdateFailure.notInstalled,
          'no-reconnect' => FirmwareUpdateFailure.noReconnect,
          _ => null,
        };
      });
      await tester.pump();
      expect(tester.takeException(), isNull);
      if (status == 'not-installed') expect(find.text(en.firmwareUpdateNotInstalledMessage('2.0.10')), findsOneWidget);
      if (status == 'no-reconnect') expect(find.text(en.firmwareUpdateUnconfirmedMessage), findsOneWidget);
      if (status == 'verifying') expect(find.text(en.firmwareVerifyingInstallation), findsOneWidget);
      if (status == 'installed') expect(find.text('${en.currentVersion}: 3.0.1'), findsOneWidget);
      await capture(tester, 'ota-$status.png');
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('rollback already on stable suppresses the installation offer', (tester) async {
    await pumpPage(tester, _DeviceProvider(batteryLevel: 80),
        rollback: true, firmwareVersion: '3.0.1', expectOffer: false);
    expect(find.text(en.alreadyOnStableFirmware), findsOneWidget);
    await capture(tester, 'ota-already-stable.png');
    debugDefaultTargetPlatformOverride = null;
  });

  for (final rollback in [false, true]) {
    testWidgets('unknown battery renders waiting message and refreshes (rollback=$rollback)', (tester) async {
      final provider = _DeviceProvider();
      await pumpPage(tester, provider, rollback: rollback);
      expect(find.text(en.firmwareBatteryUnavailable), findsOneWidget);
      expect(find.text(en.firmwareBatteryTooLow(-1)), findsNothing);
      expect(startButton(tester).onPressed, isNull);
      if (!rollback) await capture(tester, '001-mobile-ios-firmware-battery-unavailable.png');
      provider.sample(kFirmwareUpdateMinBattery);
      await tester.pumpAndSettle();
      expect(find.text(en.firmwareBatteryUnavailable), findsNothing);
      expect(startButton(tester).onPressed, isNotNull);
      debugDefaultTargetPlatformOverride = null;
    });
  }

  for (final (locale, ordinal) in [('ro', '002'), ('hu', '003'), ('et', '004')]) {
    testWidgets('unknown battery guidance renders in $locale', (tester) async {
      await pumpPage(tester, _DeviceProvider(), locale: Locale(locale));
      expect(find.text(lookupAppLocalizations(Locale(locale)).firmwareBatteryUnavailable), findsOneWidget);
      expect(startButton(tester).onPressed, isNull);
      expect(tester.takeException(), isNull);
      await capture(tester, '$ordinal-mobile-ios-firmware-battery-unavailable-$locale.png');
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('charging enables unknown battery; unplugging blocks it again', (tester) async {
    final provider = _DeviceProvider(isCharging: true);
    await pumpPage(tester, provider);
    expect(startButton(tester).onPressed, isNotNull);
    expect(find.text(en.firmwareBatteryUnavailable), findsNothing);
    provider.sample(-1);
    await tester.pumpAndSettle();
    expect(startButton(tester).onPressed, isNull);
    expect(find.text(en.firmwareBatteryUnavailable), findsOneWidget);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('stale enabled callback cannot open sheet after battery becomes unknown', (tester) async {
    final provider = _DeviceProvider(batteryLevel: kFirmwareUpdateMinBattery);
    await pumpPage(tester, provider);
    final start = startButton(tester).onPressed!;
    provider.sample(-1);
    start();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('firmware_update_sheet_start')), findsNothing);
    expect(provider.updateStarts, 0);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('disconnect clears cached battery and charging; reconnect waits for a fresh sample', (tester) async {
    final provider = _DeviceProvider(batteryLevel: 80, isCharging: true);
    await pumpPage(tester, provider);
    final staleStart = startButton(tester).onPressed!;
    provider.setIsConnected(false);
    expect(provider.batteryLevel, -1);
    expect(provider.isCharging, isFalse);
    await staleStart();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('firmware_update_sheet_start')), findsNothing);
    expect(startButton(tester).onPressed, isNull);
    expect(find.text(en.firmwareBatteryUnavailable), findsOneWidget);
    provider.setIsConnected(true);
    await tester.pumpAndSettle();
    expect(startButton(tester).onPressed, isNull);
    provider.sample(80);
    await tester.pumpAndSettle();
    expect(startButton(tester).onPressed, isNotNull);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('one-point threshold crossings refresh the update and failure screens', (tester) async {
    final provider = _DeviceProvider();
    await pumpPage(tester, provider);
    provider.sample(kFirmwareUpdateMinBattery - 1);
    await tester.pumpAndSettle();
    expect(startButton(tester).onPressed, isNull);
    expect(find.text(en.firmwareBatteryTooLow(29)), findsOneWidget);
    expect(en.firmwareBatteryTooLow(29), contains('at least 30%'));
    provider.sample(kFirmwareUpdateMinBattery);
    await tester.pumpAndSettle();
    expect(startButton(tester).onPressed, isNotNull);
    await tester.tap(find.byKey(const Key('firmware_update_start')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('firmware_update_sheet_start')));
    await tester.pumpAndSettle();
    final retry = find.byKey(const Key('firmware_update_try_again'));
    expect(find.text(en.firmwareDownloadFailedMessage), findsOneWidget);
    provider.sample(kFirmwareUpdateMinBattery - 1);
    await tester.pumpAndSettle();
    expect(tester.widget<OmiButton>(retry).onPressed, isNull);
    provider.sample(kFirmwareUpdateMinBattery);
    await tester.pumpAndSettle();
    expect(tester.widget<OmiButton>(retry).onPressed, isNotNull);
    expect(find.text(en.firmwareBatteryTooLow(kFirmwareUpdateMinBattery - 1)), findsNothing);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('disconnect while the confirmation sheet is open blocks a cached charging battery', (tester) async {
    final provider = _DeviceProvider(batteryLevel: 80, isCharging: true);
    await pumpPage(tester, provider);
    await tester.tap(find.byKey(const Key('firmware_update_start')));
    await tester.pumpAndSettle();
    provider.setIsConnected(false);
    await tester.tap(find.byKey(const Key('firmware_update_sheet_start')));
    await tester.pumpAndSettle();
    expect(provider.updateStarts, 0);
    expect(startButton(tester).onPressed, isNull);
    expect(find.text(en.firmwareBatteryUnavailable), findsOneWidget);
    debugDefaultTargetPlatformOverride = null;
  });

  for (final battery in [-1, 0, 15, kFirmwareUpdateMinBattery - 1]) {
    testWidgets('sheet confirmation rechecks battery $battery before starting', (tester) async {
      final provider = _DeviceProvider(batteryLevel: kFirmwareUpdateMinBattery);
      await pumpPage(tester, provider);
      await tester.tap(find.byKey(const Key('firmware_update_start')));
      await tester.pumpAndSettle();
      provider.sample(battery);
      await tester.tap(find.byKey(const Key('firmware_update_sheet_start')));
      await tester.pumpAndSettle();
      expect(provider.updateStarts, 0, reason: 'Must block before download or native DFU');
      expect(startButton(tester).onPressed, isNull);
      expect(
          find.text(battery < 0 ? en.firmwareBatteryUnavailable : en.firmwareBatteryTooLow(battery)), findsOneWidget);
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('charging allows unknown battery confirmation; retry honors the gate', (tester) async {
    final provider = _DeviceProvider(isCharging: true);
    await pumpPage(tester, provider);
    await tester.tap(find.byKey(const Key('firmware_update_start')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('firmware_update_sheet_start')));
    await tester.pumpAndSettle();
    expect(provider.updateStarts, 1);
    // Missing ZIP URL intentionally stops this permitted start before a download or native DFU.
    expect(find.text(en.firmwareDownloadFailedMessage), findsOneWidget);
    final retry = find.byKey(const Key('firmware_update_try_again'));
    expect(tester.widget<OmiButton>(retry).onPressed, isNotNull);
    provider.sample(-1);
    await tester.pumpAndSettle();
    expect(tester.widget<OmiButton>(retry).onPressed, isNull);
    expect(find.text(en.firmwareBatteryUnavailable), findsOneWidget);
    provider.sample(kFirmwareUpdateMinBattery);
    await tester.pumpAndSettle();
    expect(tester.widget<OmiButton>(retry).onPressed, isNotNull);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('battery becoming unknown during download prevents bootloader handoff', (tester) async {
    final directory = (await tester.runAsync(() => Directory.systemTemp.createTemp('omi-firmware-gate-')))!;
    addTearDown(() => tester.runAsync(() => directory.delete(recursive: true)));
    const paths = MethodChannel('plugins.flutter.io/path_provider');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(paths, (_) async => directory.path);
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(paths, null));

    _offerZip = true;
    final provider = _DeviceProvider(batteryLevel: kFirmwareUpdateMinBattery);
    _onDownload = () => provider.sample(-1);
    await pumpPage(tester, provider);
    await tester.tap(find.byKey(const Key('firmware_update_start')));
    await tester.pumpAndSettle();
    final sheet = tester.widget<FirmwareUpdateSheet>(find.byType(FirmwareUpdateSheet));
    // Await the real download callback in real time, including its temporary file write.
    await tester.runAsync(sheet.onUpdateStart);
    await tester.pump();
    expect(provider.updateStarts, 1);
    expect(provider.updateResets, 1, reason: 'A rejected handoff must release the update-in-progress flag');
    final dynamic state = tester.state(find.byType(FirmwareUpdate));
    expect(state.isDownloaded, isTrue);
    expect(state.isInstalling, isFalse);
    expect(state.updateFailure, isNull, reason: 'No native DFU should have been attempted');
    expect(tester.takeException(), isNull);
    debugDefaultTargetPlatformOverride = null;
  });
}

// Evidence only: the widget-test engine's system face is not the phone's font.
// Repaint paragraphs explicitly in the loaded product fixture for every locale.
void _paintProductFont(RenderObject object) {
  if (object is RenderParagraph) object.text = _productFont(object.text);
  object.visitChildren(_paintProductFont);
  object.markNeedsPaint();
}

InlineSpan _productFont(InlineSpan span) {
  if (span is! TextSpan) return span;
  final style = span.style ?? const TextStyle();
  final family = style.fontFamily;
  if (family != null && (family.startsWith('packages/') || family.contains('Icons'))) return span;
  return TextSpan(
    text: span.text,
    style: style.copyWith(fontFamily: 'SF Pro Display'),
    children: span.children?.map(_productFont).toList(),
    recognizer: span.recognizer,
    semanticsLabel: span.semanticsLabel,
    locale: span.locale,
  );
}

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
  // Flutter's built-in Material font is outside FontManifest.json in widget tests.
  // Register it explicitly so every locale's platform back glyph is captured.
  var directory = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10; i++, directory = directory.parent) {
    for (final path in ['artifacts/material_fonts', 'material_fonts']) {
      final icons = File('${directory.path}/$path/MaterialIcons-Regular.otf');
      if (!icons.existsSync()) continue;
      await (FontLoader('MaterialIcons')..addFont(Future.value(ByteData.sublistView(await icons.readAsBytes()))))
          .load();
      return;
    }
  }
  throw StateError('MaterialIcons-Regular.otf not found above ${Platform.resolvedExecutable}');
}

class _FirmwareHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FirmwareHttpClient();
}

class _FirmwareHttpClient implements HttpClient {
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    expect(method, 'GET');
    expect(url.path, anyOf('/v2/firmware/latest', '/v2/firmware/stable', '/firmware.zip'));
    return _FirmwareRequest(url);
  }

  @override
  int? maxConnectionsPerHost;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  Duration? connectionTimeout;
  @override
  void close({bool force = false}) {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FirmwareRequest implements HttpClientRequest {
  _FirmwareRequest(this.url);
  final Uri url;
  @override
  HttpHeaders get headers => _FirmwareHeaders();
  @override
  bool followRedirects = false;
  @override
  int maxRedirects = 5;
  @override
  bool persistentConnection = true;
  @override
  int contentLength = -1;
  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();
  @override
  Future<HttpClientResponse> close() async {
    if (url.path == '/firmware.zip') {
      _onDownload?.call();
      return _FirmwareResponse([1, 2, 3]);
    }
    return _FirmwareResponse(utf8.encode(jsonEncode({
      'version': '3.0.1',
      'min_version': '2.0.0',
      'draft': false,
      if (_offerZip) 'zip_url': 'http://firmware.test/firmware.zip',
    })));
  }

  @override
  Future<HttpClientResponse> get done => close();
  @override
  void abort([Object? error, StackTrace? stackTrace]) {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FirmwareResponse extends Stream<List<int>> implements HttpClientResponse {
  _FirmwareResponse(this._body);
  final List<int> _body;
  @override
  int get statusCode => 200;
  @override
  int get contentLength => _body.length;
  @override
  HttpHeaders get headers => _FirmwareHeaders();
  @override
  String get reasonPhrase => 'OK';
  @override
  bool get isRedirect => false;
  @override
  List<RedirectInfo> get redirects => const [];
  @override
  bool get persistentConnection => true;
  @override
  StreamSubscription<List<int>> listen(void Function(List<int>)? onData,
          {Function? onError, void Function()? onDone, bool? cancelOnError}) =>
      Stream.value(_body).listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FirmwareHeaders implements HttpHeaders {
  @override
  void forEach(void Function(String, List<String>) action) {}
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
