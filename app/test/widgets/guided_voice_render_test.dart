import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';
import '../providers/guided_voice_experience_test.dart' show ExperienceIO;

Future<void> loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in ['.SF UI Text', '.SF UI Display', 'SF Pro Display']) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
  Directory? fonts;
  var directory = File(Platform.resolvedExecutable).parent;
  for (var i = 0; i < 7; i++) {
    final candidate = Directory('${directory.path}/material_fonts');
    if (candidate.existsSync()) {
      fonts = candidate;
      break;
    }
    directory = directory.parent;
  }
  if (fonts == null) throw StateError('Pinned Flutter material fonts are required for render evidence');
  final roboto = FontLoader('Roboto');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    roboto.addFont(Future.value(ByteData.sublistView(File('${fonts.path}/Roboto-$weight.ttf').readAsBytesSync())));
  }
  await roboto.load();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(loadFonts);
  const output = String.fromEnvironment('VOICE_RENDER_OUTPUT');
  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    for (final state in [
      'idle',
      'recording',
      'transcribing',
      'confirmation',
      'failed',
      'typing',
      'review',
      'payoff-chat',
      'payoff-fallback',
      'paused'
    ]) {
      testWidgets('${platform.name} $state at 393x852', (tester) async {
        debugDefaultTargetPlatformOverride = platform;
        addTearDown(() => debugDefaultTargetPlatformOverride = null);
        tester.view.physicalSize = const Size(1179, 2556);
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        OmiColors.active = OmiPalette.light;
        final io = ExperienceIO();
        final flow = GuidedVoiceController(io);
        addTearDown(flow.dispose);
        Future<void>? pending;
        if (state != 'idle') {
          if (state == 'typing') {
            await flow.typeInstead();
          } else {
            await flow.start();
            final pcm = Uint8List(32000 * 6);
            final data = ByteData.sublistView(pcm);
            for (var i = 0; i < pcm.length; i += 2) {
              final amplitude = [180, 500, 1100, 1650, 850, 300, 1400][(i ~/ 3200) % 7];
              data.setInt16(i, i % 8 == 0 ? amplitude : amplitude ~/ 3, Endian.little);
            }
            for (var offset = 0; offset < pcm.length; offset += 3200) {
              io.audio!(Uint8List.sublistView(pcm, offset, offset + 3200));
            }
            if (state == 'recording') expect(flow.levelHistory.toSet().length, greaterThan(3));
            if (state == 'paused') {
              await flow.pause();
            } else if (state == 'transcribing') {
              io.pendingTranscription = Completer<String>();
              pending = flow.next();
            } else if (state == 'failed') {
              io.transcriptionFails = true;
              await flow.next();
            } else if (state != 'recording') {
              await flow.next();
              if (state != 'confirmation') {
                await flow.confirmAnswer();
                await flow.skipPrompt();
                await flow.skipPrompt();
                await flow.skipPrompt();
                if (state.startsWith('payoff')) {
                  await flow.saveAll();
                  io.chatFails = state == 'payoff-fallback';
                  if (state == 'payoff-chat') {
                    io.pendingChat = Completer<String>()..complete('Focus on **finishing** your bicycle project.');
                  }
                  await flow.showPayoff('What should I focus on this week?');
                }
              }
            }
          }
        }
        final theme = buildOmiTheme(brightness: Brightness.light);
        final family = platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto';
        final boundary = GlobalKey();
        var continued = false;
        await tester.pumpWidget(MaterialApp(
          theme: theme.copyWith(
              textTheme: theme.textTheme.apply(fontFamily: family),
              primaryTextTheme: theme.primaryTextTheme.apply(fontFamily: family)),
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: RepaintBoundary(
              key: boundary,
              child:
                  Scaffold(body: SpeechProfileWidget(controller: flow, goNext: () => continued = true, onSkip: () {}))),
        ));
        await tester.pump(const Duration(milliseconds: 300));
        if (state == 'typing') {
          await tester.enterText(
              find.byKey(const Key('introduction_typed_0')), 'I build bicycles and want to finish my next design.');
          await tester.pump(const Duration(milliseconds: 300));
        }
        expect(tester.takeException(), isNull);
        for (final key in ['introduction_skip_prompt', 'speech_profile_skip_intro', 'introduction_another']) {
          final link = find.byKey(Key(key));
          if (link.evaluate().isNotEmpty) {
            expect(tester.getRect(link).bottom, lessThanOrEqualTo(852), reason: '$state bottom link $key');
          }
        }
        if (output.isNotEmpty) {
          await tester.runAsync(() async {
            final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
            final shot = await render.toImage(pixelRatio: 3);
            final bytes = await shot.toByteData(format: ui.ImageByteFormat.png);
            const states = [
              'idle',
              'recording',
              'transcribing',
              'confirmation',
              'failed',
              'typing',
              'review',
              'payoff-chat',
              'payoff-fallback'
            ];
            final ordinal = (state == 'paused'
                    ? (platform == TargetPlatform.iOS ? 19 : 20)
                    : states.indexOf(state) + 1 + (platform == TargetPlatform.iOS ? 0 : 9))
                .toString()
                .padLeft(3, '0');
            final platformSlug = platform == TargetPlatform.iOS ? 'mobile-ios' : 'mobile-android';
            final file = File('$output/$ordinal-$platformSlug-$state.png');
            await file.parent.create(recursive: true);
            await file.writeAsBytes(bytes!.buffer.asUint8List());
            shot.dispose();
          });
        }
        if (state.startsWith('payoff')) {
          await tester.tap(find.byKey(const Key('payoff_continue')));
          expect(continued, isTrue);
        }
        await tester.pumpWidget(const SizedBox());
        if (pending != null) {
          io.pendingTranscription!.complete('Heard answer');
          await pending;
          // Discard the confirmation state after the fixture unmounts.
        }
        await flow.pause();
        debugDefaultTargetPlatformOverride = null;
      });
    }
  }
}
