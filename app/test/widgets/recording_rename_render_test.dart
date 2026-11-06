import 'package:omi/env/env.dart';
import '../helpers/recording_speaker_fixtures.dart';
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
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

const output = String.fromEnvironment('SPEAKER_RENDER_OUTPUT');
const capturePartial = bool.fromEnvironment('SPEAKER_RENDER_PARTIAL');
const frame = String.fromEnvironment('SPEAKER_RENDER_FRAME', defaultValue: '002-mobile-ios-recording-rename-after');
Future<void> loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final entry in manifest) {
    final loader = FontLoader(entry['family']);
    for (final font in entry['fonts']) {
      loader.addFont(rootBundle.load(font['asset']));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final file in ['SFPRODISPLAYREGULAR.OTF', 'SFPRODISPLAYMEDIUM.OTF', 'SFPRODISPLAYBOLD.OTF']) {
      loader.addFont(sfProFont(file));
    }
    await loader.load();
  }
}

void main() {
  setUpAll(() => Env.init(RecordingSpeakerFixtureEnv()));
  for (final partialCoverage in [false, true]) {
    testWidgets('recording rename renders honest scope, partial=$partialCoverage', (tester) async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      OmiColors.active = OmiPalette.dark;
      final boundary = GlobalKey();
      if (output.isNotEmpty) await tester.runAsync(loadFonts);
      final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []))
        ..people = [
          Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026)),
          Person(id: 'sam', name: 'Sam', createdAt: DateTime(2026), updatedAt: DateTime(2026)),
        ];
      await tester.pumpWidget(RepaintBoundary(
          key: boundary,
          child: ChangeNotifierProvider.value(
              value: people,
              child: MaterialApp(
                debugShowCheckedModeBanner: false,
                theme: buildOmiTheme(brightness: Brightness.dark),
                localizationsDelegates: AppLocalizations.localizationsDelegates,
                supportedLocales: AppLocalizations.supportedLocales,
                home: Scaffold(
                    body: NameSpeakerBottomSheet(
                  speakerId: 1,
                  segmentId: 'one',
                  defaultApplyToSpeaker: true,
                  wholeRecording: true,
                  recordingCoverageComplete: () => !partialCoverage,
                  segments: [
                    for (final (id, text, start) in [
                      ('one', 'Let’s review the plan together.', 0.0),
                      ('two', 'We can finish this tomorrow.', 6.0),
                      ('three', 'I will send the notes after lunch.', 12.0)
                    ])
                      TranscriptSegment(
                          id: id,
                          text: text,
                          speaker: 'SPEAKER_1',
                          speakerId: 1,
                          isUser: false,
                          personId: null,
                          start: start,
                          end: start + 4,
                          translations: [])
                  ],
                  onSpeakerAssigned: (_, __, ___, ____, _____) async => true,
                )),
              ))));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      if (partialCoverage) {
        expect(find.text('Other lines from this voice (recording coverage unconfirmed)'), findsOneWidget);
        expect(find.text('Apply to the whole recording'), findsNothing);
      }
      if (output.isNotEmpty && capturePartial == partialCoverage) {
        await tester.runAsync(() async {
          final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await render.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory(output).create(recursive: true);
          await File('$output/$frame.png').writeAsBytes(bytes!.buffer.asUint8List());
        });
      }
      await tester.pumpWidget(const SizedBox.shrink());
      people.dispose();
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
