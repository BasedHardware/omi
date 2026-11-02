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

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/review/widgets/review_entry_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/phone_power_source.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../support/on_device_fakes.dart';

/// Home after the UI cleanup: only Questions for you above the list, and recordings waiting for a
/// plan back as locked rows that offer this phone or a plan. CI runs it as a layout check.
const _output = String.fromEnvironment('UI_CLEANUP_RENDER_OUTPUT');

class _EnvFields implements EnvFields {
  const _EnvFields();
  @override
  String get apiBaseUrl => '';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
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
}

OnDeviceTranscriptionController _phone({OnDeviceSettings settings = const OnDeviceSettings(enabled: false)}) =>
    OnDeviceTranscriptionController(
      model: FakeOnDeviceModel(
          const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed, sizeBytes: 120 * 1024 * 1024), null),
      power: const UnknownPhonePowerSource(),
    )..debugActivate(settings: settings, transcribing: false);

final _start = DateTime(2026, 10, 27, 21, 59).millisecondsSinceEpoch ~/ 1000;
final _recordings = [
  for (final (i, s) in [9, 8, 10].indexed) HeldAudioRecording(id: 'r$i', startedAt: _start + i * 3600, seconds: s * 60),
];

Future<void> _snap(WidgetTester tester, GlobalKey boundary, String name) async {
  expect(tester.takeException(), isNull);
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });
  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<GlobalKey> pump(WidgetTester tester, Widget body, {double height = 852, ReviewProvider? review}) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = Size(393, height);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    final boundary = GlobalKey();
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: MultiProvider(
        providers: [ChangeNotifierProvider<ReviewProvider?>.value(value: review)],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.light),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(backgroundColor: OmiColors.surface0, body: SafeArea(child: body)),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    return boundary;
  }

  testWidgets('Home: Questions for you, then locked recording rows', (tester) async {
    late ReviewProvider review;
    await tester.runAsync(() async {
      review = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [
          ReviewItem(itemId: 'task:c1', kind: ReviewItemKind.task, task: TaskItem(candidateId: 'c1', description: 'x')),
          ReviewItem(itemId: 'task:c2', kind: ReviewItemKind.task, task: TaskItem(candidateId: 'c2', description: 'y')),
        ], remainingToday: 2)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])),
      );
      await review.load();
    });
    final b = await pump(
        tester,
        ListView(children: [
          const ReviewEntryCard(),
          for (final (i, r) in _recordings.indexed)
            HeldRecordingLockedRow(recording: r, more: i == _recordings.length - 1 ? 59 : 0, onPressed: () {}),
        ]),
        review: review);
    expect(find.byType(HeldRecordingLockedRow), findsNWidgets(3));
    await _snap(tester, b, '001-mobile-ios-home-locked-rows');
    review.dispose();
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('tapping a locked row offers this phone or a plan', (tester) async {
    final phone = _phone();
    final b = await pump(
        tester,
        Builder(
          builder: (context) => ListView(children: [
            HeldRecordingLockedRow(
              recording: _recordings.first,
              onPressed: () => openLockedRecordingChoice(context, controller: phone),
            ),
          ]),
        ));
    await tester.tap(find.byType(HeldRecordingLockedRow));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await _snap(tester, b, '002-mobile-ios-locked-row-choice');
    debugDefaultTargetPlatformOverride = null;
  });
}
