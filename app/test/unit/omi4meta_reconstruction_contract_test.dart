import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/dev_env.dart';
import 'package:omi/firebase_options_dev.dart' as dev_firebase;

String _read(String path) => File(path).readAsStringSync();

String _lockedVersion(String packageName) {
  final lock = _read('pubspec.lock');
  final match = RegExp(
    '^  $packageName:\\n(?:    .+\\n)*?    version: "?([^"\\n]+)"?',
    multiLine: true,
  ).firstMatch(lock);
  if (match == null) {
    fail('Missing $packageName in pubspec.lock');
  }
  return match.group(1)!;
}

String _firebaseCoreConstraint(String packageName) {
  final packageConfig = jsonDecode(_read('.dart_tool/package_config.json')) as Map<String, dynamic>;
  final packages = packageConfig['packages'] as List<dynamic>;
  final package = packages.cast<Map<String, dynamic>>().firstWhere(
        (entry) => entry['name'] == packageName,
        orElse: () => fail('Missing $packageName in package_config.json'),
      );
  final rootUri = package['rootUri'] as String;
  final pubspec = File('${Uri.parse(rootUri).toFilePath()}/pubspec.yaml').readAsStringSync();
  final match = RegExp(r'^\s*firebase_core:\s*\^?([^\s]+)', multiLine: true).firstMatch(pubspec);
  if (match == null) {
    fail('Missing firebase_core dependency in $packageName');
  }
  return match.group(1)!;
}

void main() {
  group('Omi4Meta reconstruction contract', () {
    test('declares Meta wearables integration surfaces', () {
      expect(_read('pubspec.yaml'), contains('meta_wearables_dat_flutter'));
      expect(_read('lib/backend/schema/bt_device/bt_device.dart'), contains('metaWearables'));

      final service = File('lib/services/devices/meta_wearables_service.dart');
      expect(service.existsSync(), isTrue);
      final serviceSource = service.readAsStringSync();
      expect(serviceSource, contains('class MetaWearablesService'));
      expect(serviceSource, contains('Future<MetaWearablesSnapshot> snapshot()'));
      expect(serviceSource, contains('Future<BtDevice> startPairing()'));
      expect(serviceSource, contains('DeviceType.metaWearables'));
    });

    test('keeps recreated iOS STT fast path guarded', () {
      expect(_read('lib/services/sockets/transcription_service.dart'), contains('Duration(milliseconds: 500)'));

      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('SpeechAnalyzer'));
      expect(appDelegate, contains('SpeechTranscriber'));
      expect(appDelegate, contains('AssetInventory'));
      expect(appDelegate, contains('#available(iOS 26.0, *)'));
    });

    test('declares iOS DAT runtime requirements', () {
      expect(_read('ios/Podfile'), contains("platform :ios, '17.0'"));

      final project = _read('ios/Runner.xcodeproj/project.pbxproj');
      expect(project, contains('IPHONEOS_DEPLOYMENT_TARGET = 17.0;'));
      expect(project, isNot(contains('IPHONEOS_DEPLOYMENT_TARGET = 13.0;')));
      expect(project, isNot(contains('IPHONEOS_DEPLOYMENT_TARGET = 15.0;')));
      expect(project, isNot(contains('IPHONEOS_DEPLOYMENT_TARGET = 16.0;')));

      expect(_read('ios/Flutter/AppFrameworkInfo.plist'), contains('<string>17.0</string>'));
      expect(_read('ios/Flutter/Flutter.podspec'), contains("s.ios.deployment_target = '17.0'"));
      expect(_read('ios/Flutter/Flutter.podspec'), isNot(contains("s.ios.deployment_target = '13.0'")));
      expect(_read('scripts/repair_flutter_spm_ios_target.sh'), contains('ios/Flutter/Flutter.podspec'));

      final plist = _read('ios/Runner/Info.plist');
      expect(plist, contains('<key>MWDAT</key>'));
      expect(plist, contains('<string>omimeta://</string>'));
      expect(plist, contains('<string>fb-viewapp</string>'));
      expect(plist, contains('<string>com.meta.ar.wearable</string>'));
    });

    test('Info.plist carries MWDAT app id and build-time token placeholder', () {
      final plist = _read('ios/Runner/Info.plist');
      expect(plist, contains('<string>2020435062214461</string>'),
          reason: 'MetaAppID must match Wearables Developer Center project 2020435062214461.');
      expect(plist, contains(r'<string>$(META_WEARABLES_CLIENT_TOKEN)</string>'),
          reason: 'ClientToken must be injected at build time, not committed to source.');
      expect(plist, isNot(matches(RegExp(r'AR\|\d+\|[A-Fa-f0-9]{32}'))),
          reason: 'ClientToken must not be committed to source.');
      expect(plist, isNot(contains('<string>developer-mode-placeholder</string>')),
          reason: 'Developer Mode sentinel values must be replaced by production credentials.');
      expect(plist, contains(r'$(DEVELOPMENT_TEAM)'));
    });

    test('iOS DAT registration callback is forwarded to the DAT plugin', () {
      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      final plugin = _read(
        'third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaWearablesDatPlugin.swift',
      );

      expect(plugin, contains('MetaWearablesDatHandleURL'),
          reason: 'The native DAT plugin listens for URL notifications from the host app.');
      expect(appDelegate, contains('NotificationCenter.default.post'));
      expect(appDelegate, contains('MetaWearablesDatHandleURL'),
          reason: 'Meta AI registration callbacks must reach Wearables.shared.handleUrl through the plugin.');
      expect(appDelegate, contains('deepLinkChannel?.invokeMethod("onDeepLink"'),
          reason: 'Existing OAuth/deep-link forwarding must remain intact.');
    });

    test('Android DAT stage A registration wiring is present', () {
      final mainActivity = _read('android/app/src/main/kotlin/com/example/my_project/MainActivity.kt');
      expect(mainActivity, contains('FlutterFragmentActivity'));
      expect(mainActivity, isNot(contains('class MainActivity: FlutterActivity()')));

      final buildGradle = _read('android/app/build.gradle');
      expect(buildGradle, contains('minSdkVersion 31'));
      expect(buildGradle, contains('ndkVersion System.getenv()["NDK_VERSION"] ?: "28.2.13676358"'));

      final settingsGradle = _read('android/settings.gradle');
      expect(settingsGradle, contains('maven.pkg.github.com/facebook/meta-wearables-dat-android'));
      expect(settingsGradle, contains('github_token'));
      expect(settingsGradle, contains('GITHUB_TOKEN'));

      final manifest = _read('android/app/src/main/AndroidManifest.xml');
      expect(manifest, contains('android.permission.INTERNET'));
      expect(manifest, contains('android.permission.BLUETOOTH_CONNECT'));
      expect(manifest, contains('android:launchMode="singleTop"'));
      expect(manifest, contains('com.meta.wearable.mwdat.APPLICATION_ID'));
      expect(manifest, contains('android:value="2020435062214461"'));
      expect(manifest, contains('com.meta.wearable.mwdat.CLIENT_TOKEN'));
      expect(manifest, contains(r'android:value="${metaWearablesClientToken}"'));
      expect(manifest, isNot(matches(RegExp(r'AR\|\d+\|[A-Fa-f0-9]{32}'))));
      expect(buildGradle, contains('META_WEARABLES_CLIENT_TOKEN'));
      expect(manifest, contains('com.meta.wearable.mwdat.DAM_ENABLED'));
      expect(manifest, contains('com.meta.wearable.mwdat.ANALYTICS_OPT_OUT'));
      expect(manifest, contains('android:scheme="omimeta"'));

      final agents = _read('AGENTS.md');
      expect(agents, contains('github_token'));
      expect(agents, contains('GITHUB_TOKEN'));
      expect(agents, contains('read:packages'));
    });

    test('Info.plist enables DAT Display sessions used by the app', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('startDisplaySession'), reason: 'Display is in product scope.');
      expect(provider, contains('sendDisplayView'), reason: 'Display is in product scope.');

      final plist = _read('ios/Runner/Info.plist');
      expect(plist, contains('<key>DAMEnabled</key>'));
      expect(plist, contains('<true/>'));
      expect(plist, contains('<key>NSLocalNetworkUsageDescription</key>'),
          reason: 'Display/high-bandwidth fallback uses local network link leases.');
      expect(plist, contains('<key>NSBonjourServices</key>'));
    });

    test('connection guide offers Meta Glasses with Omi Glass artwork', () {
      final guide = _read('lib/widgets/connection_guide_sheet.dart');
      expect(guide, contains("id: 'meta_glasses'"));
      expect(guide, contains('pairingTitleMetaGlasses'));
      expect(guide, contains('pairingDescMetaGlasses'));

      final metaCardIndex = guide.indexOf("id: 'meta_glasses'");
      final imageIndex = guide.indexOf('Assets.images.omiGlass.path', metaCardIndex);
      expect(imageIndex, greaterThan(metaCardIndex),
          reason: 'Meta Glasses guide entry must reuse the Omi Glass product image.');

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, contains('"pairingTitleMetaGlasses"'));
      expect(arb, contains('"pairingDescMetaGlasses"'));
      expect(arb, contains('"metaGlasses"'));
    });

    test('meta wearables provider manages multiple devices', () {
      final provider = File('lib/providers/meta_wearables_provider.dart');
      expect(provider.existsSync(), isTrue);
      final source = provider.readAsStringSync();
      expect(source, contains('class MetaWearablesProvider'));
      expect(source, contains('List<DeviceInfo>'), reason: 'Provider must track every paired Meta device.');
      expect(source, contains('devicesStream'), reason: 'Provider must observe multi-device updates from DAT.');
      expect(source, contains('selectDevice'), reason: 'User must be able to pick the active glasses.');
      expect(source, contains('startRegistration'));
      expect(source, contains('unregister'));

      expect(_read('lib/main.dart'), contains('MetaWearablesProvider'),
          reason: 'Provider must be registered in the app-level MultiProvider.');

      final connectPage = _read('lib/pages/capture/connect.dart');
      expect(connectPage, contains('MetaGlasses'), reason: 'Connect page must expose a Meta Glasses entry point.');
    });

    test('meta glasses camera permission has explicit app-visible states', () {
      final service = _read('lib/services/devices/meta_wearables_service.dart');
      expect(service, contains('enum MetaGlassesCameraPermissionState'));
      expect(service, contains('notRegistered'));
      expect(service, contains('unavailable'));
      expect(service, contains('needsRequest'));
      expect(service, contains('requesting'));
      expect(service, contains('granted'));
      expect(service, contains('MetaGlassesCameraPermissionState cameraPermissionState'));
      expect(service, contains('Future<bool> requestCameraPermission()'));
      expect(service, contains('MetaWearablesDat.requestCameraPermission()'),
          reason: 'The service must preserve the plugin permission request result.');

      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('MetaGlassesCameraPermissionState cameraPermissionState'));
      expect(provider, contains('bool get cameraPermissionGranted'));
      expect(provider, contains('bool get isRequestingCameraPermission'));
      expect(provider, contains('MetaGlassesCameraPermissionState.requesting'));

      final page = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(page, contains('isRequestingCameraPermission'),
          reason: 'The permission CTA must visibly reflect an in-flight Meta AI permission request.');
    });

    test('connect panel shows one connected state, not stacked search + connected', () {
      final connectPage = _read('lib/pages/capture/connect.dart');
      expect(connectPage, contains('Consumer2<OnboardingProvider, MetaWearablesProvider>'),
          reason: 'Connected state must consider both BLE and Meta glasses.');
      expect(connectPage, contains('_connectAnotherDevice'),
          reason: 'Multi-device: scanner collapses behind connect-another-device once glasses connect.');
      expect(connectPage, contains('_buildMetaGlassesConnectedCard'));
      expect(connectPage, contains('connectAnotherDevice'));

      // The connection guide follows scanner visibility — it must be reachable
      // while adding another device even when glasses are already connected.
      final bottomBar = connectPage.substring(connectPage.indexOf('bottomNavigationBar:'));
      expect(bottomBar, contains('_connectAnotherDevice'),
          reason: 'Guide link must reappear when the scanner is shown via connect-another-device.');
    });

    test('meta glasses support Camera+Mic and Mic-only capture modes with media-remote tap gestures', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('enum MetaGlassesCaptureMode'));
      expect(provider, contains('cameraAndMic'));
      expect(provider, contains('micOnly'));
      expect(provider, contains('startCapture'));
      expect(provider, contains('stopCapture'));
      expect(provider, contains("invokeMethod('configureForBluetooth')"),
          reason: 'Mic capture must route audio from the glasses Bluetooth (HFP) microphone.');
      expect(provider, contains('ingestCapturedImage'),
          reason: 'Camera mode must feed DAT photos into the conversation image pipeline.');
      expect(provider, contains('enableBackgroundStreaming'));
      // DAT has no gesture API; taps arrive as Bluetooth media-remote commands
      // that iOS delivers only while capture holds the audio session.
      expect(provider, contains('gestures=media-remote'));
      expect(provider, contains("MethodChannel('com.omi/meta_gestures')"));
      expect(provider, contains('_handleGesture'));

      final controller = _read('lib/services/capture/capture_controller.dart');
      expect(controller, contains('Future<bool> ingestCapturedImage(Uint8List imageBytes'));

      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('MPRemoteCommandCenter'));
      expect(appDelegate, contains('com.omi/meta_gestures'));
      expect(appDelegate, contains('import MediaPlayer'));

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, contains('"metaGlassesModeCameraMic"'));
      expect(arb, contains('"metaGlassesModeMicOnly"'));
      expect(arb, contains('"metaGlassesGestureHint"'));
      expect(arb, contains('"connectAnotherDevice"'));
    });

    test('multi-device hub page exists and is wired from home', () {
      final hub = File('lib/pages/devices/devices_page.dart');
      expect(hub.existsSync(), isTrue);
      final source = hub.readAsStringSync();
      expect(source, contains('class DevicesPage'));
      expect(source, contains('Consumer2<DeviceProvider, MetaWearablesProvider>'),
          reason: 'Hub must list the BLE wearable and every pair of Meta glasses together.');
      expect(source, contains('metaProvider.devices.map'),
          reason: 'Every paired pair of glasses gets its own row (multi-device).');
      expect(source, contains('ConnectedDevice'), reason: 'BLE row must navigate to the device page.');
      expect(source, contains('MetaGlassesPage'), reason: 'Glasses rows must navigate to the glasses page.');
      expect(source, contains('ConnectDevicePage'), reason: 'Hub must offer connecting another device.');

      final pill = _read('lib/pages/home/widgets/battery_info_widget.dart');
      expect(pill, contains('DevicesPage'), reason: 'Home battery pill routes to the hub when glasses are linked.');
      expect(pill, contains('MetaWearablesProvider'));

      final main = _read('lib/main.dart');
      expect(main, contains('ChangeNotifierProxyProvider<CaptureProvider, MetaWearablesProvider>'),
          reason: 'Home device state needs glasses registration known at startup and capture controller attached.');
      expect(main, contains('lazy: false'));
      expect(main, contains('create: (context) => MetaWearablesProvider()..init()'));

      expect(_read('lib/l10n/app_en.arb'), contains('"myDevices"'));
    });

    test('glasses behave like a built-in app: auto-capture, buffered photos, light stream', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('autoCaptureEnabled'),
          reason: 'Capture must start hands-free when registered glasses appear.');
      expect(provider, contains('_maybeAutoStartCapture'));
      expect(provider, contains('attachCaptureController'),
          reason: 'Pipeline is wired app-wide so no page visit is needed.');
      expect(provider, contains('flushPhotoQueue'),
          reason: 'Photos are stored locally and retried until the backend confirms them.');
      expect(provider, contains('meta_glasses_photo_queue'));
      expect(provider, contains('_photoSessionFps'),
          reason: 'The camera session runs at a low frame rate to keep the per-frame copy cheap.');
      expect(provider, contains('StreamQuality.medium'),
          reason: 'Medium quality so stored frames are viewable (low/360p looked bad).');

      expect(_read('lib/main.dart'), contains('ChangeNotifierProxyProvider<CaptureProvider, MetaWearablesProvider>'),
          reason: 'Capture controller must be attached at app level for autonomous operation.');

      final controller = _read('lib/services/capture/capture_controller.dart');
      expect(controller, contains('Future<bool> ingestCapturedImage'),
          reason: 'Photo ingestion must report delivery so the queue only drops confirmed photos.');

      final page = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(page, contains('_showPreview'), reason: 'Live preview is opt-in; rendering it caused UI lag.');

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, contains('"metaGlassesAutoCapture"'));
      expect(arb, contains('"metaGlassesPendingPhotos"'));
    });

    test('StreamSession configuration uses DAT-valid defaults for photo capture', () {
      final plugin = _read('third_party/meta_wearables_dat_flutter/lib/meta_wearables_dat_flutter.dart');
      expect(plugin, contains('VideoCodec videoCodec = VideoCodec.raw'),
          reason: 'OMI uses raw frames unless a caller explicitly opts into HEVC.');

      final streamQuality = _read('third_party/meta_wearables_dat_flutter/lib/src/models/stream_quality.dart');
      expect(streamQuality, contains('fpsValues = [2, 7, 15, 24, 30]'), reason: 'DAT only accepts these frame rates.');

      final service = _read('lib/services/devices/meta_wearables_service.dart');
      expect(service, contains('int fps = 30'));
      expect(service, contains('StreamQuality quality = StreamQuality.medium'));

      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('static const int _photoSessionFps = 2;'),
          reason: 'Background stream uses the lowest DAT-valid frame rate (2 fps) to keep copies cheap.');
      expect(provider, contains('static const StreamQuality _photoSessionQuality = StreamQuality.medium;'),
          reason: 'Medium quality so stored frames are viewable.');
    });

    test('Meta DAT session lifecycle states are surfaced and handled', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('StreamSessionState streamSessionState = StreamSessionState.stopped;'));
      expect(provider, contains('DeviceSessionState deviceSessionState = DeviceSessionState.idle;'));
      expect(provider, contains('MetaWearablesDat.streamSessionStateStream().listen'));
      expect(provider, contains('MetaWearablesDat.deviceSessionStateStream().listen'));
      expect(provider, contains('_handleStreamSessionState'));
      expect(provider, contains('case StreamSessionState.paused:'),
          reason: 'Paused sessions must not be restarted by the app.');
      expect(provider, contains('case StreamSessionState.stopped:'),
          reason: 'Stopped sessions must release stream resources so a new session can be created.');
      expect(provider, contains('_releaseStreamResources();'));
      expect(provider, contains('MetaWearablesDat.streamSessionErrorStream().listen'));
      expect(provider, contains('MetaWearablesDat.deviceSessionErrorStream().listen'));
      expect(provider, contains('MetaWearablesDat.videoStreamSizeStream().listen'));
    });

    test('device update-required compatibility states have recovery CTAs', () {
      final plugin = _read('third_party/meta_wearables_dat_flutter/lib/meta_wearables_dat_flutter.dart');
      expect(plugin, contains('static Future<void> openFirmwareUpdate()'));
      expect(plugin, contains('static Future<void> openDATGlassesAppUpdate()'));

      final platform =
          _read('third_party/meta_wearables_dat_flutter/lib/src/meta_wearables_dat_platform_interface.dart');
      expect(platform, contains('Future<void> openFirmwareUpdate()'));
      expect(platform, contains('Future<void> openDATGlassesAppUpdate()'));

      final methodChannel =
          _read('third_party/meta_wearables_dat_flutter/lib/src/meta_wearables_dat_method_channel.dart');
      expect(methodChannel, contains("invokeMethod<void>('openFirmwareUpdate')"));
      expect(methodChannel, contains("invokeMethod<void>('openDATGlassesAppUpdate')"));

      final iosPlugin = _read(
        'third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaWearablesDatPlugin.swift',
      );
      expect(iosPlugin, contains('case "openFirmwareUpdate":'));
      expect(iosPlugin, contains('Wearables.shared.openFirmwareUpdate()'));
      expect(iosPlugin, contains('case "openDATGlassesAppUpdate":'));
      expect(iosPlugin, contains('Wearables.shared.openDATGlassesAppUpdate()'));

      final service = _read('lib/services/devices/meta_wearables_service.dart');
      expect(service, contains('enum MetaGlassesCameraPermissionState'));
      for (final state in ['notRegistered', 'unavailable', 'needsRequest', 'requesting', 'granted']) {
        expect(service, contains(state));
      }
      expect(service, contains('Future<void> openFirmwareUpdate()'));
      expect(service, contains('Future<void> openDATGlassesAppUpdate()'));

      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('Future<void> openCompatibilityUpdate(DeviceInfo device)'));
      expect(provider, contains('DeviceCompatibility.deviceUpdateRequired'));
      expect(provider, contains('DeviceCompatibility.sdkUpdateRequired'));

      final glassesPage = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(glassesPage, contains('provider.openCompatibilityUpdate(device)'));
      expect(glassesPage, contains('context.l10n.update'));

      final devicesPage = _read('lib/pages/devices/devices_page.dart');
      expect(devicesPage, contains('metaProvider.openCompatibilityUpdate(device)'));
      expect(devicesPage, contains('context.l10n.update'));
    });

    test('Meta glasses rows show doc-level device kind metadata', () {
      final labels = File('lib/utils/meta_wearables_device_label.dart');
      expect(labels.existsSync(), isTrue);
      final labelSource = labels.readAsStringSync();
      expect(labelSource, contains('DeviceKind.rayBanMeta'));
      expect(labelSource, contains('l10n.metaGlassesTypeRayBanMeta'));
      expect(labelSource, contains('DeviceKind.rayBanDisplay'));
      expect(labelSource, contains('l10n.metaGlassesTypeRayBanDisplay'));
      expect(labelSource, contains('DeviceKind.oakleyMeta'));
      expect(labelSource, contains('l10n.metaGlassesTypeOakleyMeta'));

      final glassesPage = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(glassesPage, contains('metaWearablesDeviceKindLabel(context.l10n, device.kind)'));

      final devicesPage = _read('lib/pages/devices/devices_page.dart');
      expect(devicesPage, contains('metaWearablesDeviceKindLabel(context.l10n, device.kind)'));

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, contains('"metaGlassesTypeRayBanMeta"'));
      expect(arb, contains('"metaGlassesTypeRayBanDisplay"'));
      expect(arb, contains('"metaGlassesTypeOakleyMeta"'));

      final generated = _read('lib/l10n/app_localizations.dart');
      expect(generated, contains('String get metaGlassesTypeRayBanMeta;'));
      expect(generated, contains('String get metaGlassesTypeRayBanDisplay;'));
      expect(generated, contains('String get metaGlassesTypeOakleyMeta;'));

      final englishArb = jsonDecode(_read('lib/l10n/app_en.arb')) as Map<String, dynamic>;
      expect(englishArb, containsPair('metaGlassesTypeRayBanMeta', isA<String>()));
      expect(englishArb, containsPair('metaGlassesTypeRayBanDisplay', isA<String>()));
      expect(englishArb, containsPair('metaGlassesTypeOakleyMeta', isA<String>()));
    });

    test('Display support is explicitly scoped to a Ray-Ban Display status card', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('static const bool _advancedDisplayUiEnabled = false;'));
      expect(provider, contains('bool get canShowDisplayStatus => selectedDevice?.kind == DeviceKind.rayBanDisplay;'));
      expect(provider, contains('if (!canShowDisplayStatus) return;'));
      expect(provider, contains('MetaWearablesDat.startDisplaySession'));
      expect(provider, contains('MetaWearablesDat.sendDisplayView'));
      expect(provider, contains('MetaWearablesDat.displayStateStream()'));
      expect(provider, contains('FlexBox('));
      expect(provider, contains('buildDisplayCaptureView'));
      expect(provider, contains('DisplayText(captureStateLine'));
      expect(provider, contains('DisplayText(snippet'));
      expect(provider, contains('_displaySessionActive = true;'));
      expect(provider, contains('static const Duration _displayUpdateThrottle = Duration(seconds: 2);'));
      expect(provider, contains('_captureController?.addListener(_handleCaptureDisplayChanged);'));
      expect(provider, contains('_displayCaptureController?.removeListener(_handleCaptureDisplayChanged);'));

      final page = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(page, isNot(contains('startDisplaySession(')),
          reason:
              'No standalone Display UI is exposed until the product scope expands beyond the capture status card.');
    });

    test('thermal and hinge health signals pause camera capture without stopping mic capture', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('enum MetaGlassesHealth'));
      expect(provider, contains('MetaGlassesHealth.ok'));
      expect(provider, contains('MetaGlassesHealth.overheating'));
      expect(provider, contains('MetaGlassesHealth.foldedClosed'));
      expect(provider, contains('isThermalCritical'));
      expect(provider, contains('isHingesClosed'));
      expect(provider, contains('_thermalPaused'));
      expect(provider, contains('Future<void> _handleSessionError'));
      expect(provider, contains('await _stopPhotoLoop();'));
      expect(provider, contains('_scheduleThermalRetry();'));
      expect(
        provider,
        isNot(contains('if (health == MetaGlassesHealth.overheating) _manualStopRequested = true;')),
        reason: 'Thermal safety pauses camera photos only; mic capture should keep running and auto-recover.',
      );

      final glassesPage = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(glassesPage, contains('_healthWarningRow(context, provider)'));
      expect(glassesPage, contains('Icons.thermostat'));
      expect(glassesPage, contains('Icons.visibility_off'));
      expect(glassesPage, contains('Colors.orangeAccent'));
      expect(glassesPage, contains('context.l10n.metaGlassesOverheating'));
      expect(glassesPage, contains('context.l10n.metaGlassesFolded'));

      final devicesPage = _read('lib/pages/devices/devices_page.dart');
      expect(devicesPage, contains('metaProvider.health'));
      expect(devicesPage, contains('context.l10n.metaGlassesOverheating'));
      expect(devicesPage, contains('context.l10n.metaGlassesFolded'));

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, contains('"metaGlassesOverheating"'));
      expect(arb, contains('"metaGlassesFolded"'));
      expect(glassesPage, isNot(contains('battery')));
      final glassesCardStart = devicesPage.indexOf('Widget _glassesCard');
      final connectCardStart = devicesPage.indexOf('Widget _connectDeviceCard');
      expect(glassesCardStart, greaterThanOrEqualTo(0));
      expect(connectCardStart, greaterThan(glassesCardStart));
      final glassesCard = devicesPage.substring(glassesCardStart, connectCardStart);
      expect(glassesCard, isNot(contains('battery')));
    });

    test('Meta glasses background capture is native-pushed frames (no shutter, works backgrounded)', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      // Native-pushed videoFramesStream trigger keeps firing while backgrounded
      // (a Dart timer would suspend); each throttled event encodes a viewable
      // JPEG natively via captureLatestFrame. No pause/resume shutter, no
      // hardware still capture, no GPU-texture rasterizer (suspends in bg).
      expect(provider, contains('_service.videoFrames().listen'));
      expect(provider, contains('MetaWearablesDat.captureLatestFrame'),
          reason: 'native CPU JPEG encode renders in history and works backgrounded (texture rasterizer did neither)');
      expect(provider, isNot(contains('MetaWearablesDat.captureStreamFrame')),
          reason: 'the Flutter-texture rasterizer is suspended when backgrounded; capture must use the native encode');
      expect(provider, isNot(contains('Timer.periodic(_photoInterval')),
          reason: 'Dart timers suspend in the background; the native frame stream does not');
      expect(provider, isNot(contains('_pausePreviewBetweenFrames')),
          reason: 'per-frame pause/resume caused the shuttered cadence and is removed');
      expect(provider, isNot(contains('MetaWearablesDat.capturePhoto(')),
          reason: 'background capture never calls the still-photo shutter API');

      final service = _read('lib/services/devices/meta_wearables_service.dart');
      expect(service, contains('Stream<VideoFrame> videoFrames()'));
    });

    test('Meta glasses capture is exactly two modes: Camera+Mic or Mic only (no separate vision toggle)', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      expect(provider, contains('enum MetaGlassesCaptureMode'));
      expect(provider, isNot(contains('continuousVisionEnabled')),
          reason: 'Vision is implied by Camera+Mic mode; a separate continuous-vision toggle is redundant.');
      expect(provider, isNot(contains('ContinuousVisionFrameGate')));
      expect(provider, isNot(contains('setContinuousVisionEnabled')));

      final page = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(page, isNot(contains('meta_glasses_continuous_vision_switch')));
      expect(page, contains('metaGlassesModeCameraMic'));
      expect(page, contains('metaGlassesModeMicOnly'));

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, isNot(contains('"metaGlassesContinuousVision"')));
    });

    test('capture frequency is editable and hardware gestures are honest, while stream errors retry quietly', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      // Editable capture frequency.
      expect(provider, contains('enum MetaGlassesCaptureInterval'));
      expect(provider, contains('Future<void> setCaptureInterval(MetaGlassesCaptureInterval interval)'));
      expect(provider, contains('Duration get _photoInterval => captureInterval.duration;'));
      // Hardware truth: DAT exposes no gesture API, so there is exactly ONE
      // honest gesture — a stalk tap arriving as a Bluetooth media-remote
      // command, debounced, toggling capture. No fake tap/swipe action
      // remapping UI.
      expect(provider, isNot(contains('setTapAction')));
      expect(provider, isNot(contains('setSwipeAction')));
      expect(provider, isNot(contains('swipeAction')));
      expect(provider, isNot(contains('MetaGlassesGestureAction')));
      expect(provider, isNot(contains('_runTapGestureToggleCapture')));
      expect(provider, contains('gestures=media-remote'));
      expect(provider, contains('_gestureDebounce'));
      // Generic video-streaming errors must recover quietly, not surface a raw error.
      expect(provider, contains('recoverFromVideoStreamingError'));

      final page = _read('lib/pages/meta_wearables/meta_glasses_page.dart');
      expect(page, contains('provider.setCaptureInterval'));
      expect(page, isNot(contains('provider.setGesturesEnabled')));
      expect(page, isNot(contains('provider.setTapAction')));
      expect(page, isNot(contains('provider.setSwipeAction')));
      expect(page, isNot(contains('DropdownButton<MetaGlassesGestureAction>')));

      final arb = _read('lib/l10n/app_en.arb');
      expect(arb, contains('"metaGlassesCaptureFrequency"'));
      expect(arb, contains('"metaGlassesGestures"'));
      expect(arb, contains('not supported'));
      expect(arb, isNot(contains('"metaGlassesActionToggleCapture"')));
      expect(arb, isNot(contains('"metaGlassesActionTakePhoto"')));
    });

    test('Meta glasses are first-class in onboarding device selection', () {
      final wrapper = _read('lib/pages/onboarding/wrapper.dart');
      expect(wrapper, contains('OnboardingMetaGlassesStep'));
      expect(wrapper, contains('MetaWearablesProvider'));
      expect(wrapper, contains('MetaGlassesPage'));
      expect(wrapper, contains("onboardingStepCompleted('Device meta_glasses')"));
      expect(wrapper, contains('metaGlassesOnboardingComplete'));
      expect(wrapper, isNot(contains('Container(), // FindDevicesPage placeholder')));

      final step = _read('lib/pages/onboarding/meta_glasses_onboarding_step.dart');
      expect(step, contains("Key('onboarding_meta_glasses_option')"));
      expect(step, contains('Assets.images.omiGlass.path'));
      expect(step, contains('context.l10n.metaGlasses'));
      expect(step, contains('context.l10n.getOmiDevice'));
      expect(step, contains('metaGlassesOnboardingComplete'));
      expect(step, contains('provider.isRegistered && provider.hasLinkedDevices'));
    });

    test('MockDeviceKit smoke harness exercises device permission stream photo path', () {
      final smoke = File('test/unit/meta_wearables_mockdevice_smoke_test.dart');
      expect(smoke.existsSync(), isTrue);
      final source = smoke.readAsStringSync();
      expect(source, contains('MetaWearablesDat.enableMockDevice'));
      expect(source, contains('MetaWearablesDat.pairMockRayBanMeta'));
      expect(source, contains('MetaWearablesDat.mockPowerOn'));
      expect(source, contains('MetaWearablesDat.mockUnfold'));
      expect(source, contains('MetaWearablesDat.mockDon'));
      expect(source, contains('MetaWearablesDat.setMockPermission'));
      expect(source, contains('MetaWearablesDat.setMockCapturedImage'));
      expect(source, contains('MetaWearablesProvider'));
      expect(source, contains('provider.startPreview()'));
      expect(source, contains('provider.captureGlassesPhotoNow()'));
      expect(source, contains('provider.pendingPhotoCount'));
    });

    test('agent-flutter UI proof harness is gated by compile-time define', () {
      final harness = File('lib/debug/meta_wearables_ui_proof.dart');
      expect(harness.existsSync(), isTrue);
      final source = harness.readAsStringSync();
      expect(source, contains("bool.fromEnvironment('OMI_META_UI_PROOF')"));
      expect(source, contains('!kReleaseMode'));
      expect(source, contains('MetaWearablesUiProof'));
      expect(source, contains('MetaWearablesProvider(service: const MetaWearablesProofService())'));
      expect(source, contains('DevicesPage'));
      expect(source, contains('MetaGlassesPage'));
      expect(source, contains('Proof Ray-Ban Meta'));
      expect(source, contains('Proof Ray-Ban Display'));
      expect(source, contains('DeviceCompatibility.deviceUpdateRequired'));
      expect(source, contains('DeviceCompatibility.sdkUpdateRequired'));

      final mobileApp = _read('lib/mobile/mobile_app.dart');
      expect(mobileApp, contains('if (MetaWearablesUiProof.enabled)'));
      expect(mobileApp, contains('return const MetaWearablesUiProof();'));
    });

    test('photos never displace the live transcription in capture views', () {
      final widgets = _read('lib/pages/capture/widgets/widgets.dart');

      // Lite capture card: transcript first, photos as a compact strip below.
      final liteStart = widgets.indexOf('getLiteTranscriptWidget(List<TranscriptSegment>');
      expect(liteStart, greaterThanOrEqualTo(0));
      final liteBody = widgets.substring(liteStart);
      final transcriptIndex = liteBody.indexOf('LiteTranscriptWidget(segments:');
      final photosIndex = liteBody.indexOf('PhotosPreviewWidget(photos:');
      expect(transcriptIndex, greaterThanOrEqualTo(0));
      expect(photosIndex, greaterThanOrEqualTo(0));
      expect(transcriptIndex, lessThan(photosIndex),
          reason: 'An incoming photo must not take the transcript line\'s spot on the capture card.');

      // Full view: no fixed 250px photo grid stacked above the transcript.
      expect(widgets, isNot(contains('SizedBox(height: 250, child: buildPhotos())')),
          reason: 'Periodic glasses photos collapse into a strip; transcript keeps the space.');
    });

    test('phone install build does not require watchOS runtime', () {
      final project = _read('ios/Runner.xcodeproj/project.pbxproj');
      expect(project, isNot(contains('Embed Watch Content')));
      expect(project, isNot(contains('omiWatchApp.app in Embed Watch Content')));
      expect(project, isNot(contains('target = 42A7BA332E788BD300138969 /* omiWatchApp */;')));
    });

    test('Flutter SPM integration has local engine package shim', () {
      final shim = File('ios/Flutter/ephemeral/Packages/.packages/FlutterFramework/Package.swift');
      expect(shim.existsSync(), isTrue, reason: 'Flutter SPM resolver requires FlutterFramework local package.');

      final package = shim.readAsStringSync();
      expect(package, contains('name: "FlutterFramework"'));
      expect(package, contains('.library(name: "FlutterFramework"'));
      expect(package, contains('.target('));

      final source = File(
          'ios/Flutter/ephemeral/Packages/.packages/FlutterFramework/Sources/FlutterFramework/FlutterFramework.swift');
      expect(source.existsSync(), isTrue);

      final devScheme = _read('ios/Runner.xcodeproj/xcshareddata/xcschemes/dev.xcscheme');
      expect(devScheme, contains('Run Prepare Flutter Framework Script'));
    });

    test('Firebase SwiftPM plugins agree on FlutterFire shared core tag', () {
      final coreVersion = _lockedVersion('firebase_core');

      for (final packageName in ['firebase_auth', 'firebase_crashlytics', 'firebase_messaging']) {
        expect(
          _firebaseCoreConstraint(packageName),
          coreVersion,
          reason: '$packageName must derive the same flutterfire exact tag as firebase_core.',
        );
      }
    });

    test('Meta DAT install build excludes mock SDK compile path', () {
      final pubspec = _read('pubspec.yaml');
      expect(pubspec.contains('path: third_party/meta_wearables_dat_flutter'), isTrue);

      final packageFile = File('third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Package.swift');
      expect(packageFile.existsSync(), isTrue);
      expect(packageFile.readAsStringSync().contains('MWDATMockDevice'), isFalse);

      final mockManager = _read(
        'third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaMockDeviceManager.swift',
      );
      expect(mockManager, contains('Mock Device Kit unavailable in Omi4Meta install build'));
      expect(mockManager.contains('pairRaybanMeta()'), isFalse);
      expect(mockManager.contains('MockDisplaylessGlasses'), isFalse);
    });

    test('Meta Mock Device Kit integration is debug define gated and documented', () {
      final integration = File('integration_test/meta_glasses_mock_test.dart');
      expect(integration.existsSync(), isTrue);
      final source = integration.readAsStringSync();
      expect(source, contains("bool.fromEnvironment('OMI_META_MOCK')"));
      expect(source, contains('kDebugMode &&'));
      expect(source, contains('MetaWearablesMockHarness'));
      expect(source, contains('RecordingCaptureController'));
      expect(source, contains('setMockCapturedImage'));
      expect(source, contains('provider.startCapture(capture)'));
      expect(source, contains('provider.pendingPhotoCount, 0'));

      final support = File('test/support/meta_wearables_mock_harness.dart');
      expect(support.existsSync(), isTrue);
      expect(support.readAsStringSync(), contains('class MetaWearablesMockHarness'));

      final agents = _read('AGENTS.md');
      expect(agents, contains('flutter test integration_test/meta_glasses_mock_test.dart'));
      expect(agents, contains('--dart-define=OMI_META_MOCK=true'));
    });

    test('SwiftProtobuf stays statically linked (dynamic-framework hack crashes device launch)', () {
      // A Podfile hack that forced SwiftProtobuf to a dynamic framework and
      // stripped it from the Runner embed step left the binary loading an
      // @rpath/SwiftProtobuf.framework that was never embedded -> dyld
      // "Library not loaded" crash at launch on device (stuck on splash).
      // The MWDATCore static-link duplicate-class objc warning is harmless.
      final podfile = _read('ios/Podfile');
      expect(podfile, contains('use_frameworks! :linkage => :static'));
      expect(podfile, isNot(contains('swift_protobuf_dynamic_frameworks')),
          reason: 'Forcing SwiftProtobuf dynamic without embedding it crashes device launch.');
      expect(podfile, isNot(contains('Pod::BuildType.dynamic_framework')));
      expect(podfile, isNot(contains('remove_swift_protobuf_runner_linkage')));

      final podfileLock = _read('ios/Podfile.lock');
      expect(podfileLock, contains('- SwiftProtobuf'));
      expect(podfileLock, isNot(contains('MWDATCore')), reason: 'Do not patch or repackage Meta DAT xcframeworks.');
    });

    test('install build has generated Firebase and Env config', () {
      for (final path in [
        'lib/firebase_options_dev.dart',
        'lib/firebase_options_prod.dart',
        'lib/env/dev_env.g.dart',
        'lib/env/prod_env.g.dart',
        'ios/Config/Dev/GoogleService-Info.plist',
        'ios/Config/Prod/GoogleService-Info.plist',
        'ios/Runner/GoogleService-Info.plist',
      ]) {
        expect(File(path).existsSync(), isTrue, reason: '$path is required by kernel build.');
      }

      expect(_read('lib/env/dev_env.g.dart'), contains('part of \'dev_env.dart\''));
      expect(_read('lib/env/prod_env.g.dart'), contains('part of \'prod_env.dart\''));

      final devEnv = DevEnv();
      expect(devEnv.apiBaseUrl, 'https://api.omi.me/');
      expect(devEnv.useWebAuth, isTrue);
      expect(devEnv.appleSignInEnabled, isTrue);
      expect(devEnv.useAppleWebAuth, isTrue);
      expect(devEnv.useAuthCustomToken, isTrue);
      expect(devEnv.authRedirectScheme, 'omi');
      expect(dev_firebase.DefaultFirebaseOptions.ios.projectId, 'based-hardware');
      expect(dev_firebase.DefaultFirebaseOptions.ios.messagingSenderId, '208440318997');
      expect(dev_firebase.DefaultFirebaseOptions.ios.appId, startsWith('1:208440318997:ios:'));
      expect(dev_firebase.DefaultFirebaseOptions.ios.iosBundleId, 'dev.moni11811.omi');

      for (final path in ['ios/Config/Dev/GoogleService-Info.plist', 'ios/Runner/GoogleService-Info.plist']) {
        final plist = _read(path);
        expect(plist, contains('<string>based-hardware</string>'), reason: '$path must match Omi prod custom tokens.');
        expect(plist, contains('<string>208440318997</string>'), reason: '$path must use Omi prod sender id.');
        expect(plist, contains('<string>1:208440318997:ios:a1906bb92fe244810e421c</string>'));
        expect(plist, isNot(contains('based-hardware-dev')));
        expect(plist, isNot(contains('1031333818730')));
      }

      final generatedDevEnv = _read('lib/env/dev_env.g.dart');
      expect(generatedDevEnv, contains('// generated_from: .dev.env'));
      expect(generatedDevEnv, contains('static const List<int> _enviedkeyapiBaseUrl'));

      expect(
        _read('lib/env/dev_env.dart'),
        contains("defaultValue: true"),
        reason: 'Dev bundle dev.moni11811.omi does not have a matching native Google iOS OAuth client.',
      );
      expect(
        _read('lib/env/dev_env.g.dart'),
        contains('static const bool? useWebAuth = true;'),
        reason: 'Dev auth must use backend web OAuth for both Google and Apple.',
      );
    });

    test('dev iOS install uses Firebase matching bundle id', () {
      const devBundleId = 'dev.moni11811.omi';

      for (final path in [
        'ios/Flutter/devDebug.xcconfig',
        'ios/Flutter/devProfile.xcconfig',
        'ios/Flutter/devRelease.xcconfig'
      ]) {
        expect(
          _read(path),
          contains('APP_BUNDLE_IDENTIFIER=$devBundleId'),
          reason: '$path must match the checked-in dev Firebase iOS app.',
        );
      }

      expect(_read('ios/Config/Dev/GoogleService-Info.plist'), contains('<string>$devBundleId</string>'));
      expect(_read('ios/Runner/GoogleService-Info.plist'), contains('<string>$devBundleId</string>'));
      expect(_read('lib/firebase_options_dev.dart'), contains("iosBundleId: '$devBundleId'"));

      expect(
        _read('ios/Runner.xcodeproj/project.pbxproj'),
        isNot(contains(r'$(APP_BUNDLE_IDENTIFIER).development.widget')),
        reason: 'Dev widget id is derived from the dev app id; adding .development again breaks signing truth.',
      );
    });

    test('AppSetup dev environment exists for backend web auth', () {
      final envFile = File('.dev.env');
      expect(envFile.existsSync(), isTrue, reason: 'docs.omi.me AppSetup creates .dev.env during setup.sh ios.');

      final env = _read('.dev.env');
      expect(env, contains('API_BASE_URL=https://api.omi.me/'));
      expect(env, contains('USE_WEB_AUTH=true'));
      expect(env, contains('USE_AUTH_CUSTOM_TOKEN=true'));
      expect(env, contains('USE_APPLE_WEB_AUTH=true'));
      expect(env, contains('APPLE_SIGN_IN_ENABLED=true'));
    });

    test('startup init cannot hold the native splash forever', () {
      final main = _read('lib/main.dart');

      expect(main, contains('Future<T?> _runStartupPhase<T>('));
      expect(main, contains('.timeout(_startupPhaseTimeout'));
      expect(main, contains("await _runStartupPhase('ServiceManager.start'"));
      expect(main, contains("await _runStartupPhase('AuthService.getIdToken'"));
    });

    test('Apple sign-in stays visible and uses web auth when native entitlement is unavailable', () {
      expect(_read('lib/env/env.dart'), contains('appleSignInEnabled'));
      expect(_read('lib/env/env.dart'), contains('useAppleWebAuth'));
      expect(_read('lib/env/dev_env.dart'), contains('APPLE_SIGN_IN_ENABLED'));
      expect(_read('lib/env/dev_env.dart'), contains('USE_APPLE_WEB_AUTH'));
      expect(_read('lib/env/prod_env.dart'), contains('APPLE_SIGN_IN_ENABLED'));
      expect(_read('lib/env/prod_env.dart'), contains('USE_APPLE_WEB_AUTH'));

      final authPage = _read('lib/pages/onboarding/auth.dart');
      expect(authPage, contains('Env.appleSignInEnabled'));

      final provider = _read('lib/providers/auth_provider.dart');
      expect(provider, contains('Env.useAppleWebAuth'));
      expect(provider, contains("authenticateWithProvider('apple')"));
    });

    test('auth breadcrumbs reach native iOS logs', () {
      final authLog = File('lib/utils/omi_auth_log.dart');
      expect(authLog.existsSync(), isTrue);
      expect(authLog.readAsStringSync(), contains("MethodChannel('com.omi/auth_log')"));

      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('authLogChannel'));
      expect(appDelegate, contains('NSLog("[OmiAuth]'));

      expect(_read('lib/services/auth_service.dart'), contains('OmiAuthLog.info'));
      expect(_read('lib/providers/auth_provider.dart'), contains('OmiAuthLog.info'));
    });

    test('auth callbacks are not swallowed by generic app link handling', () {
      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(
        appDelegate,
        isNot(contains('AppLinks.shared.getLink(launchOptions: launchOptions)')),
        reason: 'Cold-start OAuth URLs must reach GoogleSignIn/Firebase delegates via super.application.',
      );

      final authService = _read('lib/services/auth_service.dart');
      expect(
        authService,
        contains('LaunchMode.externalApplication'),
        reason: 'Backend web OAuth callbacks use omi:// and need Safari/system handoff, not SFSafariViewController.',
      );
      expect(authService, contains("MethodChannel('com.omi/web_auth')"));
      expect(authService, contains('_authenticateWithNativeWebAuth'));
      expect(appDelegate, contains('ASWebAuthenticationSession'));
      expect(appDelegate, contains('callbackURLScheme'));
      expect(appDelegate, contains('session.presentationContextProvider = self'));
      expect(appDelegate, contains('presentationAnchor(for session: ASWebAuthenticationSession)'));
      expect(
        appDelegate.indexOf('presentationAnchor(for session: ASWebAuthenticationSession)'),
        lessThan(appDelegate.indexOf('func registerPlugins')),
        reason:
            'ASWebAuthenticationPresentationContextProviding must be implemented by AppDelegate, not a later helper.',
      );
      expect(
        authService,
        contains(r'${Env.authRedirectScheme}://auth/callback'),
        reason: 'Dev and TestFlight must not share one OAuth callback URL scheme.',
      );

      expect(_read('lib/env/env.dart'), contains('authRedirectScheme'));
      expect(_read('lib/env/dev_env.dart'), contains('AUTH_REDIRECT_SCHEME'));
      expect(_read('lib/env/dev_env.g.dart'), contains("static const String? authRedirectScheme = 'omi';"));
      expect(_read('lib/env/prod_env.g.dart'), contains("static const String? authRedirectScheme = 'omi';"));

      final plist = _read('ios/Runner/Info.plist');
      expect(plist, contains(r'$(AUTH_REDIRECT_SCHEME)'));
      expect(plist, isNot(contains('<string>omi</string>')));

      for (final path in [
        'ios/Flutter/devDebug.xcconfig',
        'ios/Flutter/devProfile.xcconfig',
        'ios/Flutter/devRelease.xcconfig'
      ]) {
        expect(_read(path), contains('AUTH_REDIRECT_SCHEME=omi'));
      }
      for (final path in [
        'ios/Flutter/prodDebug.xcconfig',
        'ios/Flutter/prodProfile.xcconfig',
        'ios/Flutter/prodRelease.xcconfig'
      ]) {
        expect(_read(path), contains('AUTH_REDIRECT_SCHEME=omi'));
      }
    });

    test('custom token auth falls back to provider OAuth credentials', () {
      final authService = _read('lib/services/auth_service.dart');
      expect(authService, contains('custom token sign-in failed'));
      expect(authService, contains('_signInWithProviderOAuthCredentials'));
      expect(authService, contains('FirebaseAuthException'));
      expect(
        authService.indexOf('_signInWithProviderOAuthCredentials(oauthCredentials)'),
        greaterThan(authService.indexOf('signInWithCustomToken(customToken)')),
        reason:
            'Omi prod custom token can mismatch local Firebase; provider OAuth fallback must run after token failure.',
      );
    });

    test('Google native sign-in has required iOS client id plist keys', () {
      final plist = _read('ios/Runner/Info.plist');
      expect(plist, contains('<key>GIDClientID</key>'));
      expect(plist, contains(r'<string>$(GOOGLE_CLIENT_ID)</string>'));

      for (final path in [
        'ios/Flutter/devDebug.xcconfig',
        'ios/Flutter/devProfile.xcconfig',
        'ios/Flutter/devRelease.xcconfig'
      ]) {
        expect(
          _read(path),
          contains('GOOGLE_CLIENT_ID=1031333818730-dusn243nct6i5rgfpfkj5mchuj1qnmde.apps.googleusercontent.com'),
          reason: '$path must configure GoogleSignIn before it starts OAuth.',
        );
      }
    });

    test('auth failures emit native-visible diagnostics on device console', () {
      final authService = _read('lib/services/auth_service.dart');
      expect(authService, contains("OmiAuthLog.info('Google mobile sign-in start"));
      expect(authService, contains("OmiAuthLog.info('Google mobile sign-in error"));
      expect(authService, contains("OmiAuthLog.info('Web auth start"));

      final provider = _read('lib/providers/auth_provider.dart');
      expect(provider, contains('OmiAuthLog.info'));
      expect(provider, contains('Google branch='));
      expect(provider, contains('Apple branch='));

      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('[OmiAuth] AppDelegate openURL'));
    });

    test('iOS OAuth callbacks are forwarded to Dart deep link fallback', () {
      final authService = _read('lib/services/auth_service.dart');
      expect(authService, contains("MethodChannel('com.omi/deep_links')"));
      expect(authService, contains("call.method == 'onDeepLink'"));

      final appDelegate = _read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('FlutterMethodChannel(name: "com.omi/deep_links"'));
      expect(appDelegate, contains('invokeMethod("onDeepLink"'));
    });

    test('memory item resolves delete notification page state', () {
      final source = _read('lib/pages/memories/widgets/memory_item.dart');
      expect(source.contains("package:omi/pages/memories/page.dart"), isTrue);
      expect(source, contains('findAncestorStateOfType<MemoriesPageState>'));
    });

    test('Flutter SPM package avoids CocoaPods duplicate-link plugins', () {
      final package = _read('ios/Flutter/ephemeral/Packages/FlutterGeneratedPluginSwiftPackage/Package.swift');
      expect(package.contains('meta_wearables_dat_flutter'), isTrue);

      final spmRepair = File('scripts/repair_flutter_spm_ios_target.sh');
      expect(spmRepair.existsSync(), isTrue);
      expect(spmRepair.readAsStringSync(), contains('FlutterGeneratedPluginSwiftPackage/Package.swift'));
      expect(spmRepair.readAsStringSync(), contains('.iOS("17.0")'));

      for (final podBackedPlugin in [
        'firebase_core',
        'firebase_auth',
        'firebase_messaging',
        'firebase_crashlytics',
        'posthog_flutter',
      ]) {
        expect(
          package.contains(podBackedPlugin),
          isFalse,
          reason: '$podBackedPlugin must stay CocoaPods-only to avoid duplicate iOS symbols.',
        );
      }
    });
  });
}
