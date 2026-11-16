import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/on_device/free_cap_sheet.dart';
import 'package:omi/pages/on_device/on_phone_banner.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/phone_transcription_choice.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Renders the free plan's on-device flow (David, 2026-11-16) for review. Hermetic: no network.
///
/// `flutter test test/widgets/free_ondevice_flow_render_test.dart \
///   --dart-define=OMI_FREE_ONDEVICE_EVIDENCE_DIR=<dir>`
const evidenceDir = String.fromEnvironment('OMI_FREE_ONDEVICE_EVIDENCE_DIR');
const boundaryKey = Key('free_ondevice_evidence');

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get havingRecordingDevice => false;
  @override
  Future<void> onTranscriptionSettingsChanged() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _loadFonts(WidgetTester tester) async {
  await tester.runAsync(() async {
    final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
    for (final entry in fonts) {
      final loader = FontLoader(entry['family'] as String);
      for (final font in entry['fonts'] as List<dynamic>) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
    for (final family in [
      'Roboto',
      'CupertinoSystemText',
      'CupertinoSystemDisplay',
      '.SF UI Text',
      '.SF UI Display',
      'SF Pro Display',
      '.SF Pro Text',
      '.SF Pro Display',
      'FlutterTest',
      'Ahem'
    ]) {
      final loader = FontLoader(family)
        ..addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'))
        ..addFont(sfProFont('SFPRODISPLAYMEDIUM.OTF'));
      await loader.load();
    }
  });
}

UsageProvider _freeUsage({required TranscriptionAllowanceSnapshot allowance, int usedSeconds = 18000}) {
  return UsageProvider()
    ..debugSetSubscription(UserSubscriptionResponse(
        subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
        transcriptionSecondsUsed: usedSeconds,
        transcriptionSecondsLimit: 18000,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        transcriptionAllowance: allowance));
}

Widget _background({List<Widget> top = const []}) {
  Widget row(String title, String meta) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              child: Icon(Icons.graphic_eq, color: OmiColors.textTertiary, size: 20),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.body, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Text(meta, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                ],
              ),
            ),
          ],
        ),
      );
  return Scaffold(
    body: SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
            child: Text('Conversations', textAlign: TextAlign.center, style: OmiType.title3),
          ),
          ...top,
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xs),
            child: Text('Today', style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          ),
          row('Standup with the design team', '9:00 AM · 24m'),
          row('Walk with Sam', '8:10 AM · 12m'),
        ],
      ),
    ),
  );
}

Future<void> _pump(WidgetTester tester, Widget Function() home,
    {bool dark = true,
    TargetPlatform platform = TargetPlatform.iOS,
    List<ChangeNotifierProvider> providers = const []}) async {
  tester.view.physicalSize = const Size(1179, 2556);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final previousPalette = OmiColors.active;
  addTearDown(() => OmiColors.active = previousPalette);
  OmiColors.active = dark ? OmiPalette.dark : OmiPalette.light;
  await _loadFonts(tester);
  final base = buildOmiTheme(brightness: dark ? Brightness.dark : Brightness.light);
  Widget app = MaterialApp(
    debugShowCheckedModeBanner: false,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: base.copyWith(
      platform: platform,
      textTheme: base.textTheme.apply(fontFamily: 'SF Pro Display'),
      // The Android default family is not in the test engine; render it in the bundled SF Pro.
      appBarTheme: base.appBarTheme
          .copyWith(titleTextStyle: base.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display')),
    ),
    home: home(),
  );
  if (providers.isNotEmpty) app = MultiProvider(providers: providers, child: app);
  await tester.pumpWidget(RepaintBoundary(key: boundaryKey, child: app));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

Future<void> _capture(WidgetTester tester, String name) async {
  expect(tester.takeException(), isNull);
  if (evidenceDir.isEmpty) return;
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(evidenceDir).create(recursive: true);
    await File('$evidenceDir/$name').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

Widget _sheetHost() => Builder(builder: (context) {
      WidgetsBinding.instance.addPostFrameCallback((_) => showFreeCapSheet(context, capMinutes: 300));
      return _background();
    });

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-user'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('cap sheet, dark', (tester) async {
    await _pump(tester, _sheetHost);
    expect(find.byKey(const Key('free_cap_upgrade')), findsOneWidget);
    await _capture(tester, '001-mobile-ios-free-cap-sheet-dark.png');
  });

  testWidgets('cap sheet, light', (tester) async {
    await _pump(tester, _sheetHost, dark: false);
    await _capture(tester, '002-mobile-ios-free-cap-sheet-light.png');
  });

  testWidgets('recording banner and a held recording, dark', (tester) async {
    await _pump(
      tester,
      () => _background(top: [
        const OnPhoneTranscriptionBanner(),
        const SizedBox(height: OmiSpacing.sm),
        const HeldRecordingLockedRow(
            recording: HeldAudioRecording(id: 'fixture', startedAt: 1794826800, seconds: 1440)),
      ]),
    );
    expect(find.text('Transcribing on this phone'), findsOneWidget);
    await _capture(tester, '003-mobile-ios-on-phone-banner-held-row-dark.png');
  });

  for (final (name, pinned, allowance) in [
    (
      '004-mobile-android-settings-phone-setup-dark.png',
      false,
      const TranscriptionAllowanceSnapshot(mode: 'on_device', reason: 'plan_allowance_exhausted', remainingSeconds: 0),
    ),
    (
      '005-mobile-android-settings-switch-back-dark.png',
      true,
      const TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'plan_within_allowance', remainingSeconds: 18000),
    ),
  ]) {
    testWidgets('settings: $name', (tester) async {
      const config = CustomSttConfig(
          provider: SttProvider.onDeviceWhisper, language: 'en', identity: SttModeResolver.freemiumOnDeviceId);
      if (pinned) {
        final persisted = await PhoneTranscriptionChoice.adopt(config, SharedPreferencesUtil());
        await SharedPreferencesUtil().saveConfigForProvider(persisted.provider, persisted);
      }
      final capture = _Capture();
      final usage = _freeUsage(allowance: allowance, usedSeconds: pinned ? 0 : 18000);
      addTearDown(capture.dispose);
      await _pump(
        tester,
        () => TranscriptionSettingsPage(choosePhone: !pinned),
        platform: TargetPlatform.android,
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: capture),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ],
      );
      // The debug-only model performance snackbar otherwise covers the page.
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpAndSettle();
      expect(find.byKey(Key(pinned ? 'transcription_switch_back' : 'transcription_phone_model')), findsOneWidget);
      await _capture(tester, name);
    });
  }
}
