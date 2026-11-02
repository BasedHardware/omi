import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/processing_backlog_view.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Renders the held-recordings card for a Free, a Plus and an Unlimited owner on an iPhone-sized
/// screen with the app's real fonts, and asserts each lays out without overflow. With
/// `--dart-define=HELD_AUDIO_CARD_RENDER_OUTPUT=<dir>` it also writes the PNGs used as PR evidence.
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
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

UserSubscriptionResponse _subscription(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

void main() {
  setUpAll(_loadFonts);
  const output = String.fromEnvironment('HELD_AUDIO_CARD_RENDER_OUTPUT');
  final boundary = GlobalKey();

  setUp(() async {
    // A synthetic owner outside the 10% copy holdout.
    SharedPreferences.setMockInitialValues({'uid': 'synthetic-0'});
    await SharedPreferencesUtil.init();
  });

  Future<void> shoot(WidgetTester tester, String name, PlanType plan, ProcessingBacklog backlog) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 520);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final previous = OmiColors.active;
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    addTearDown(() => OmiColors.active = previous);
    final usage = UsageProvider()..debugSetSubscription(_subscription(plan));
    addTearDown(usage.dispose);

    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          locale: const Locale('en'),
          theme: buildOmiTheme(brightness: Brightness.dark),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: SafeArea(
              child: SingleChildScrollView(
                child: Builder(
                  builder: (context) => ProcessingBacklogView(
                    backlog: backlog,
                    surface: 'a',
                    onUpgrade: () {},
                    onProcess: () async => true,
                    phoneAction: backlog.isCapped
                        ? OmiButton.tertiary(label: context.l10n.onDeviceTranscribeOnPhone, onPressed: () {})
                        : null,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump();

    expect(tester.takeException(), isNull);
    if (output.isNotEmpty) {
      await tester.runAsync(() async {
        final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
      });
    }
    debugDefaultTargetPlatformOverride = null;
  }

  const held = 6 * 3600 + 20 * 60;

  testWidgets('Free owner under the monthly limit with held audio', (tester) async {
    await shoot(
      tester,
      '001-mobile-ios-held-audio-free-card',
      PlanType.basic,
      const ProcessingBacklog(state: 'capped', budgetExhausted: false, heldAudioCount: 40, heldAudioSeconds: held),
    );
  });

  testWidgets('Plus owner at the monthly limit', (tester) async {
    await shoot(
      tester,
      '002-mobile-ios-held-audio-plus-paused',
      PlanType.plus,
      const ProcessingBacklog(state: 'capped', budgetExhausted: true, heldAudioCount: 40, heldAudioSeconds: held),
    );
  });

  testWidgets('Unlimited owner with recordings waiting for a choice', (tester) async {
    await shoot(
      tester,
      '003-mobile-ios-held-audio-unlimited-process',
      PlanType.unlimitedV2,
      const ProcessingBacklog(
        state: 'waiting_choice',
        budgetExhausted: false,
        heldAudioCount: 40,
        heldAudioSeconds: held,
        estimatedHours: 6.3,
        estimatedPercent: 0,
      ),
    );
  });
}
