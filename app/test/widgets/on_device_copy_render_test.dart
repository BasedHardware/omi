import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/on_device/on_device_at_cap_sheet.dart';
import 'package:omi/pages/on_device/on_device_provenance_section.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/on_device/on_device_schedule_page.dart';
import 'package:omi/pages/on_device/on_device_settings_page.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_tuning.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/phone_power_source.dart';
import 'package:omi/ui/ui.dart';

import '../support/on_device_fakes.dart';

/// On-device copy renders. `--dart-define=OMI_ON_DEVICE_UX_EVIDENCE_DIR=<dir>` writes 1179×2556 PNGs.
void main() {
  const evidence = String.fromEnvironment('OMI_ON_DEVICE_UX_EVIDENCE_DIR');

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> shoot(
    WidgetTester tester,
    String name, {
    required Widget home,
    TargetPlatform platform = TargetPlatform.iOS,
    bool light = false,
    Locale locale = const Locale('en'),
    Future<void> Function(WidgetTester tester)? afterPump,
    List<String> fontFallback = const ['SF Pro Display'],
  }) async {
    debugDefaultTargetPlatformOverride = platform;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final previousPalette = OmiColors.active;
    OmiColors.active = light ? OmiPalette.light : OmiPalette.dark;
    addTearDown(() => OmiColors.active = previousPalette);
    if (evidence.isNotEmpty) await tester.runAsync(_loadEvidenceFonts);

    final brightness = light ? Brightness.light : Brightness.dark;
    final theme = buildOmiTheme(brightness: brightness).copyWith(platform: platform);
    final titled = theme.copyWith(
      appBarTheme: theme.appBarTheme.copyWith(
        titleTextStyle: (theme.appBarTheme.titleTextStyle ?? const TextStyle()).copyWith(
          fontFamily: 'SF Pro Display',
          fontFamilyFallback: fontFallback,
        ),
      ),
    );

    const boundaryKey = ValueKey('on_device_evidence');
    await tester.pumpWidget(RepaintBoundary(
      key: boundaryKey,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        locale: locale,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: titled,
        builder: (context, child) => DefaultTextStyle.merge(
          style: TextStyle(fontFamily: 'SF Pro Display', fontFamilyFallback: fontFallback),
          child: child!,
        ),
        home: home,
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    if (afterPump != null) await afterPump(tester);
    _rejectForbiddenCopy(tester);

    debugDefaultTargetPlatformOverride = null;
    if (evidence.isEmpty) return;
    _paintProductFont(tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey)));
    await tester.pump();
    await tester.runAsync(() async {
      final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
      final image = await boundary.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      final dir = await Directory(evidence).create(recursive: true);
      await File('${dir.path}/$name').writeAsBytes(bytes!.buffer.asUint8List());
      image.dispose();
    });
  }

  OnDeviceTranscriptionController controller({
    OnDeviceModelStatus status =
        const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed, sizeBytes: 120 * 1024 * 1024),
    String? engine,
    OnDeviceSettings settings = const OnDeviceSettings(enabled: true),
    bool transcribing = false,
  }) {
    final model = FakeOnDeviceModel(status, engine);
    final value = OnDeviceTranscriptionController(model: model, power: const UnknownPhonePowerSource())
      ..debugActivate(settings: settings, transcribing: transcribing);
    if (transcribing) value.progress = 0.42;
    return value;
  }

  const usage = StorefrontUsage(
    kind: 'usage_budget',
    percent: 80,
    resetLabel: 'resets Nov 1',
    meterLine: '80% used · about 3 hours of recording left · resets Nov 1',
    hoursLeft: 3,
    moreLabel: 'Get more usage',
  );

  Widget conversationsBackdrop() {
    return Scaffold(
      appBar: AppBar(title: const Text('Conversations')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: const [
          Text('Today'),
          SizedBox(height: 12),
          ListTile(title: Text('Standup with the design team'), subtitle: Text('9:00 AM · 24m')),
        ],
      ),
    );
  }

  testWidgets('at-cap sheet', (tester) async {
    await shoot(tester, '01-at-cap-sheet-ios.png', home: conversationsBackdrop(), afterPump: (tester) async {
      showOnDeviceAtCapSheet(tester.element(find.text('Conversations')), liveHoursReturnOn: DateTime(2026, 11, 1));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
    });
    expect(find.text("You've reached this month's limit"), findsOneWidget);
    expect(find.text('Runs while your phone charges.'), findsOneWidget);
  });

  testWidgets('parakeet setup not downloaded', (tester) async {
    final value = controller(
        status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded, sizeBytes: 538 * 1024 * 1024));
    await shoot(tester, '02-setup-step1-not-downloaded-ios.png', home: OnDeviceSetupPage(controller: value));
    expect(find.text(lookupAppLocalizations(const Locale('en')).onDeviceSetupBody), findsOneWidget);
  });

  testWidgets('parakeet setup downloading', (tester) async {
    final value = controller(
      status: const OnDeviceModelStatus(
          phase: OnDeviceModelPhase.downloading,
          progress: 0.62,
          timeLeft: Duration(minutes: 4),
          sizeBytes: 538 * 1024 * 1024),
    );
    await shoot(tester, '03-setup-step1-downloading-ios.png', home: OnDeviceSetupPage(controller: value));
  });

  testWidgets('parakeet setup installed', (tester) async {
    await shoot(tester, '04-setup-step1-installed-ios.png', home: OnDeviceSetupPage(controller: controller()));
  });

  testWidgets('schedule', (tester) async {
    await shoot(tester, '05-schedule-step2-ios.png', home: OnDeviceSchedulePage(controller: controller(), step: 2));
    expect(find.text('You can change this anytime.'), findsOneWidget);
  });

  testWidgets('waiting for charger', (tester) async {
    await shoot(
      tester,
      '06-conversations-waiting-for-charger-ios.png',
      home: Scaffold(
          body: OnDeviceQueueBannerView(
        controller: controller(),
        pendingSeconds: 3900,
        atCap: true,
        onSetUp: () {},
        moreLabel: 'Get more usage',
        onGetMoreUsage: () {},
      )),
    );
  });

  testWidgets('transcribing', (tester) async {
    await shoot(
      tester,
      '07-conversations-transcribing-ios.png',
      home: Scaffold(
          body: OnDeviceQueueBannerView(
        controller: controller(transcribing: true),
        pendingSeconds: 3900,
        atCap: true,
        onSetUp: () {},
        moreLabel: 'Get more usage',
        onGetMoreUsage: () {},
      )),
    );
  });

  testWidgets('summary on iphone', (tester) async {
    final value = controller()
      ..recordProvenance(
          'c1', const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.phone, reason: OnDeviceReason.liveHoursUsed));
    await shoot(tester, '08-summary-made-on-iphone-ios.png',
        home: Scaffold(body: OnDeviceProvenanceSection(conversationId: 'c1', controller: value, onRedo: () {})));
    expect(find.textContaining("You reached this month's limit"), findsOneWidget);
  });

  testWidgets('summary by cloud on iphone', (tester) async {
    final value = controller()
      ..recordProvenance(
          'c1', const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.cloud, reason: OnDeviceReason.liveHoursUsed));
    await shoot(tester, '09-summary-by-omi-cloud-ios.png',
        home: Scaffold(body: OnDeviceProvenanceSection(conversationId: 'c1', controller: value)));
    expect(find.textContaining("doesn't count toward your usage"), findsOneWidget);
  });

  Widget settings(OnDeviceTranscriptionController value, {StorefrontUsage? meter}) {
    return OnDeviceSettingsView(
      controller: value,
      usage: meter ?? usage,
      plansSheetAvailable: true,
      showSaveUsage: true,
      pendingSeconds: 12000,
      pendingBytes: 180 * 1024 * 1024,
      onGetMoreUsage: () {},
    );
  }

  OnDeviceTranscriptionController parakeetSettings() => controller(
      status:
          const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed, sizeBytes: OnDeviceTuning.parakeetSizeBytes));

  testWidgets('parakeet settings top', (tester) async {
    await shoot(tester, '10-settings-top-ios.png', home: settings(parakeetSettings()));
    expect(find.text('80% used · about 3 hours of recording left · resets Nov 1'), findsOneWidget);
    expect(find.text('Get more usage'), findsOneWidget);
    expect(find.text('Installed · 443 MB'), findsOneWidget);
    expect(find.text('Always transcribe on this phone'), findsOneWidget);
    expect(find.text('Saves your usage. No speaker labels.'), findsOneWidget);
  });

  testWidgets('parakeet settings scrolled', (tester) async {
    await shoot(tester, '11-settings-scrolled-ios.png', home: settings(parakeetSettings()), afterPump: (tester) async {
      await tester.drag(find.byType(ListView), const Offset(0, -500));
      await tester.pump();
    });
    expect(find.text('Remove Speech Model'), findsOneWidget);
  });

  testWidgets('settings below 80 omit the hours estimate', (tester) async {
    const low = StorefrontUsage(
      kind: 'usage_budget',
      percent: 40,
      resetLabel: 'resets Nov 1',
      meterLine: '40% used · resets Nov 1',
      moreLabel: 'Get more usage',
    );
    await shoot(tester, '26-settings-40-percent-ios.png', home: settings(parakeetSettings(), meter: low));
    expect(find.text('40% used · resets Nov 1'), findsOneWidget);
    expect(find.textContaining('hours of recording left'), findsNothing);
  });

  testWidgets('spanish settings at 80 show the backend meter', (tester) async {
    await shoot(
      tester,
      '27-settings-80-es.png',
      locale: const Locale('es'),
      home: settings(parakeetSettings()),
    );
    expect(find.text('80% used · about 3 hours of recording left · resets Nov 1'), findsOneWidget);
    expect(find.text('Get more usage'), findsOneWidget);
  });

  testWidgets('unsupported banner', (tester) async {
    await shoot(
      tester,
      '12-conversations-unsupported-ios.png',
      home: Scaffold(
          body: OnDeviceQueueBannerView(
        controller: controller(status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.unsupported)),
        pendingSeconds: 3900,
        atCap: true,
        onSetUp: () {},
        moreLabel: 'Get more usage',
        onGetMoreUsage: () {},
      )),
    );
  });

  testWidgets('waiting light', (tester) async {
    await shoot(
      tester,
      '13-conversations-waiting-light-ios.png',
      light: true,
      home: Scaffold(
          body: OnDeviceQueueBannerView(
        controller: controller(),
        pendingSeconds: 3900,
        atCap: true,
        onSetUp: () {},
        moreLabel: 'Get more usage',
        onGetMoreUsage: () {},
      )),
    );
  });

  testWidgets('android finish setup', (tester) async {
    await shoot(
      tester,
      '14-android-no-model-finish-setup.png',
      platform: TargetPlatform.android,
      home: Scaffold(
          body: OnDeviceQueueBannerView(
        controller: controller(
            status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded, sizeBytes: 538 * 1024 * 1024)),
        pendingSeconds: 3900,
        atCap: true,
        onSetUp: () {},
        moreLabel: 'Get more usage',
        onGetMoreUsage: () {},
      )),
    );
  });

  testWidgets('android downloading', (tester) async {
    await shoot(
      tester,
      '15-android-downloading.png',
      platform: TargetPlatform.android,
      home: OnDeviceSetupPage(
          controller: controller(
        status: const OnDeviceModelStatus(
            phase: OnDeviceModelPhase.downloading, progress: 0.4, sizeBytes: 538 * 1024 * 1024),
      )),
    );
  });

  testWidgets('android cloud summary', (tester) async {
    final value = controller()
      ..recordProvenance(
          'c1', const OnDeviceProvenance(summary: OnDeviceSummaryOrigin.cloud, reason: OnDeviceReason.savingLiveHours));
    await shoot(
      tester,
      '16-android-summary-by-omi-cloud.png',
      platform: TargetPlatform.android,
      home: Scaffold(body: OnDeviceProvenanceSection(conversationId: 'c1', controller: value)),
    );
    expect(find.textContaining("doesn't count toward your usage"), findsOneWidget);
  });

  testWidgets('ios 26 asset install is a settings row', (tester) async {
    await shoot(
      tester,
      '18-ios26-os-asset-installing.png',
      home: settings(controller(
        engine: 'speech_analyzer',
        status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.downloading, progress: 0.4),
      )),
    );
    expect(find.text(lookupAppLocalizations(const Locale('en')).onDeviceGettingSpeechReady(40)), findsOneWidget);
    expect(find.byType(OnDeviceSetupPage), findsNothing);
    expect(find.text('Speech model'), findsNothing);
  });

  testWidgets('parakeet setup page', (tester) async {
    await shoot(
      tester,
      '19-ios17-parakeet-setup.png',
      home: OnDeviceSetupPage(
          controller: controller(
        status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded, sizeBytes: 538 * 1024 * 1024),
      )),
    );
  });

  testWidgets('free at cap', (tester) async {
    await shoot(tester, '20-free-user-at-cap.png', home: conversationsBackdrop(), afterPump: (tester) async {
      showOnDeviceAtCapSheet(tester.element(find.text('Conversations')), liveHoursReturnOn: DateTime(2026, 11, 1));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
    });
  });

  testWidgets('transcribing progress', (tester) async {
    await shoot(
      tester,
      '21-transcribing-on-phone-progress.png',
      home: Scaffold(
          body: OnDeviceQueueBannerView(
        controller: controller(transcribing: true),
        pendingSeconds: 900,
        atCap: true,
        onSetUp: () {},
        moreLabel: 'Get more usage',
        onGetMoreUsage: () {},
      )),
    );
  });

  testWidgets('ios 15 asset progress is a settings row', (tester) async {
    await shoot(
      tester,
      '22-ios15-lower-quality-fallback.png',
      home: settings(controller(
        engine: 'sfspeech',
        status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.downloading, progress: 0.2),
      )),
    );
    expect(find.text(lookupAppLocalizations(const Locale('en')).onDeviceGettingSpeechReady(20)), findsOneWidget);
    expect(find.text(lookupAppLocalizations(const Locale('en')).onDeviceSetupBody), findsNothing);
  });

  testWidgets('ios 26 settings top and scrolled', (tester) async {
    final value =
        controller(engine: 'speech_analyzer', status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed));
    await shoot(tester, '23-ios26-settings-top.png', home: settings(value));
    expect(find.text('80% used · about 3 hours of recording left · resets Nov 1'), findsOneWidget);
    expect(find.text('Speech model'), findsNothing);
    await shoot(tester, '24-ios26-settings-scrolled.png', home: settings(value), afterPump: (tester) async {
      await tester.drag(find.byType(ListView), const Offset(0, -400));
      await tester.pump();
    });
    expect(find.text('Remove Speech Model'), findsNothing);
  });

  HeldAudioSummary heldSummary({bool retainLive = true, String state = 'paused'}) => HeldAudioSummary(
        state: state,
        seconds: 150,
        count: 22,
        resetAt: DateTime.utc(2026, 11, 1).millisecondsSinceEpoch ~/ 1000,
        retainLive: retainLive,
        recordings: [
          HeldAudioRecording(
              id: 'newer', startedAt: DateTime.utc(2026, 10, 17, 15, 4).millisecondsSinceEpoch ~/ 1000, seconds: 90),
          HeldAudioRecording(
              id: 'older', startedAt: DateTime.utc(2026, 10, 17, 9, 12).millisecondsSinceEpoch ~/ 1000, seconds: 60),
        ],
      );

  Widget heldHome(OnDeviceTranscriptionController value) {
    return Scaffold(
      body: ListView(
        children: [
          HeldAudioHomeSection(
            controller: value,
            gate: true,
            summary: heldSummary(),
            onUpgrade: () {},
            onPhone: () {},
          ),
        ],
      ),
    );
  }

  for (final language in const ['en', 'es', 'ja']) {
    for (final light in const [false, true]) {
      final theme = light ? 'light' : 'dark';
      testWidgets('held audio home $language $theme', (tester) async {
        final value = controller(settings: const OnDeviceSettings(enabled: false));
        await shoot(
          tester,
          'held-audio-a-$language-$theme.png',
          light: light,
          locale: Locale(language),
          fontFallback: language == 'ja' ? const ['SF Pro Display', 'Hiragino Sans'] : const ['SF Pro Display'],
          home: heldHome(value),
        );
      });
    }
  }

  testWidgets('held audio home after choosing the phone', (tester) async {
    final value = controller(settings: const OnDeviceSettings(enabled: true));
    await shoot(tester, 'held-audio-a-phone-en-dark.png', home: heldHome(value));
    expect(find.textContaining('New recordings will transcribe on this phone'), findsOneWidget);
    expect(
      find.textContaining('Waiting recordings will be transcribed after your limit resets'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('held_audio_on_phone')), findsNothing);
  });

  for (final language in const ['en', 'es', 'ja']) {
    for (final light in const [false, true]) {
      final theme = light ? 'light' : 'dark';
      testWidgets('held audio live $language $theme', (tester) async {
        final value = controller(settings: const OnDeviceSettings(enabled: false));
        await shoot(
          tester,
          'held-audio-b-$language-$theme.png',
          light: light,
          locale: Locale(language),
          fontFallback: language == 'ja' ? const ['SF Pro Display', 'Hiragino Sans'] : const ['SF Pro Display'],
          home: Scaffold(
            body: HeldAudioLiveBanner(
              controller: value,
              gate: true,
              summary: heldSummary(),
              recordedSeconds: 185,
              onUpgrade: () {},
              onPhone: () {},
            ),
          ),
        );
      });
    }
  }

  for (final language in const ['en', 'es', 'ja']) {
    for (final light in const [false, true]) {
      final theme = light ? 'light' : 'dark';
      testWidgets('held audio usage $language $theme', (tester) async {
        final value = controller(settings: const OnDeviceSettings(enabled: false, saveLiveHours: true));
        await shoot(
          tester,
          'held-audio-c-$language-$theme.png',
          light: light,
          locale: Locale(language),
          fontFallback: language == 'ja' ? const ['SF Pro Display', 'Hiragino Sans'] : const ['SF Pro Display'],
          home: Scaffold(
            body: HeldAudioUsageSection(
              controller: value,
              gate: true,
              summary: heldSummary(retainLive: false),
              paid: true,
              onUpgrade: () {},
              onSaveLiveHours: (_) {},
            ),
          ),
        );
      });
    }
  }

  for (final language in const ['en', 'es', 'ja']) {
    for (final light in const [false, true]) {
      for (final surface in const ['a', 'b', 'c']) {
        testWidgets('held audio recovering $surface $language $light', (tester) async {
          final value = controller(settings: const OnDeviceSettings(enabled: false));
          final held = heldSummary(retainLive: false, state: 'recovering');
          final Widget content;
          if (surface == 'a') {
            content = HeldAudioHomeSection(controller: value, gate: true, summary: held);
          } else if (surface == 'b') {
            content = HeldAudioLiveBanner(controller: value, gate: true, summary: held, recordedSeconds: 185);
          } else {
            content = HeldAudioUsageSection(controller: value, gate: true, summary: held, paid: true);
          }
          await shoot(
            tester,
            'held-audio-$surface-recovering-$language-${light ? 'light' : 'dark'}.png',
            light: light,
            locale: Locale(language),
            fontFallback: language == 'ja' ? const ['SF Pro Display', 'Hiragino Sans'] : const ['SF Pro Display'],
            home: Scaffold(body: ListView(children: [content])),
          );
          expect(find.textContaining('resets'), findsNothing);
        });
      }
    }
  }

  testWidgets('android model setup', (tester) async {
    await shoot(
      tester,
      '25-android-setup.png',
      platform: TargetPlatform.android,
      home: OnDeviceSetupPage(
          controller: controller(
        status: const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded, sizeBytes: 538 * 1024 * 1024),
      )),
    );
  });
}

void _paintProductFont(RenderObject object) {
  if (object is RenderParagraph) object.text = _productFont(object.text);
  object.visitChildren(_paintProductFont);
  object.markNeedsPaint();
}

InlineSpan _productFont(InlineSpan span) {
  if (span is! TextSpan) return span;
  final style = span.style ?? const TextStyle();
  return TextSpan(
    text: span.text,
    style: style.copyWith(
      fontFamily: style.fontFamily ?? 'SF Pro Display',
      fontFamilyFallback: <String>[...?style.fontFamilyFallback, 'Hiragino Sans'],
    ),
    children: span.children?.map(_productFont).toList(),
    recognizer: span.recognizer,
    semanticsLabel: span.semanticsLabel,
    locale: span.locale,
  );
}

void _rejectForbiddenCopy(WidgetTester tester) {
  final texts = tester.widgetList<Text>(find.byType(Text)).map((text) => text.data ?? '').join('\n').toLowerCase();
  for (final phrase in const [
    'live hour',
    'barely touches',
    'saves battery',
    'no model download',
    'model download required',
    'transcripts show up after you plug in',
  ]) {
    expect(texts.contains(phrase), isFalse, reason: 'rendered "$phrase"');
  }
}

Future<void> _loadEvidenceFonts() async {
  final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
  final sfAssets = <String>{};
  for (final entry in fonts) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List<dynamic>) {
      final asset = font['asset'] as String;
      if (asset.contains('SFPRODISPLAY')) sfAssets.add(asset);
      loader.addFont(rootBundle.load(asset));
    }
    await loader.load();
  }
  final semibold = _uprightWeight(_packageAsset('omi', 'assets/fonts/SFPRODISPLAYBOLD.OTF'), 600);
  for (final family in const [
    'Roboto',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    '.SF UI Text',
    '.SF UI Display',
    'FlutterTest',
    'Ahem',
    'SF Pro Display',
  ]) {
    final loader = FontLoader(family);
    for (final asset in sfAssets) {
      loader.addFont(rootBundle.load(asset));
    }
    if (semibold != null) {
      loader.addFont(Future.value(ByteData.sublistView(Uint8List.fromList(semibold))));
    }
    await loader.load();
  }
  final cjk = _hiraginoGothic();
  if (cjk != null) {
    final bytes = await cjk.readAsBytes();
    final cjkLoader = FontLoader('Hiragino Sans')
      ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(bytes))));
    await cjkLoader.load();
  }
  final icons = _materialIconsFont();
  final bytes = await icons.readAsBytes();
  final iconLoader = FontLoader('MaterialIcons')
    ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(bytes))));
  await iconLoader.load();
  final cupertino = _packageAsset('cupertino_icons', 'assets/CupertinoIcons.ttf');
  if (cupertino != null) {
    final cupertinoBytes = await cupertino.readAsBytes();
    final cupertinoLoader = FontLoader('CupertinoIcons')
      ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(cupertinoBytes))));
    await cupertinoLoader.load();
  }
}

/// Copies a font and sets its OS/2 weight so Flutter can match upright semibold text.
List<int>? _uprightWeight(File? source, int weight) {
  if (source == null) return null;
  final data = source.readAsBytesSync();
  if (data.length < 12) return null;
  final tables = ByteData.sublistView(Uint8List.fromList(data)).getUint16(4);
  var directory = 12;
  for (var i = 0; i < tables; i++) {
    final tag = String.fromCharCodes(data.sublist(directory, directory + 4));
    final offset = ByteData.sublistView(Uint8List.fromList(data.sublist(directory + 8, directory + 12))).getUint32(0);
    if (tag == 'OS/2') {
      data[offset + 4] = (weight >> 8) & 0xff;
      data[offset + 5] = weight & 0xff;
      return data;
    }
    directory += 16;
  }
  return null;
}

File? _hiraginoGothic() {
  const extracted = '/tmp/held-audio-hiragino-w3.otf';
  if (File(extracted).existsSync()) return File(extracted);
  final dir = Directory('/System/Library/Fonts');
  if (!dir.existsSync()) return null;
  for (final entity in dir.listSync()) {
    if (entity is! File) continue;
    if (entity.path.contains('W3.ttc') && entity.path.contains('角')) return entity;
  }
  return null;
}

File? _packageAsset(String package, String asset) {
  final config = File('app/.dart_tool/package_config.json');
  final path = config.existsSync() ? config : File('.dart_tool/package_config.json');
  if (!path.existsSync()) return null;
  final packages = (jsonDecode(path.readAsStringSync()) as Map<String, dynamic>)['packages'] as List<dynamic>;
  for (final entry in packages) {
    if (entry['name'] != package) continue;
    final root = path.parent.uri.resolveUri(Uri.parse(entry['rootUri'] as String));
    final file = File.fromUri(root.resolve(asset));
    if (file.existsSync()) return file;
  }
  return null;
}

File _materialIconsFont() {
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10; i++) {
    final candidate = File('${dir.path}/artifacts/material_fonts/MaterialIcons-Regular.otf');
    if (candidate.existsSync()) return candidate;
    final direct = File('${dir.path}/material_fonts/MaterialIcons-Regular.otf');
    if (direct.existsSync()) return direct;
    if (dir.path == dir.parent.path) break;
    dir = dir.parent;
  }
  throw StateError('MaterialIcons-Regular.otf not found above ${Platform.resolvedExecutable}');
}
