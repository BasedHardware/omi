import 'package:omi/ui/ui.dart';
// Visual audit harness: real production widgets, synthetic local I/O, one registry of scenarios.
// How to run it and how to add a scenario: app/e2e/SKILL.md, "Visual audit".
//
// The same harness serves two callers:
//   * integration_test/visual_audit/capture_test.dart writes 2x PNGs (OMI_AUDIT_OUTPUT is set);
//   * test/visual_audit/visual_audit_smoke_test.dart renders every scenario and writes nothing,
//     so a scenario that stops compiling or throws fails the ordinary app test suite.
//
// This file is copied over older revisions (see compat/README.md), so it imports nothing from the
// app beyond what every supported revision has: the theme and providers come from the suite.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/l10n/app_localizations.dart';

import '../journeys/support/fixture_backend.dart';
import '../journeys/support/hermetic_boot.dart';

/// The scenarios for one family of app revisions, with the theme and default providers they pump
/// into. `registry.dart` is the suite for current main; `compat/<name>/registry.dart` holds the
/// equivalent pages for older revisions, under the same ids where an equivalent exists.
class AuditSuite {
  const AuditSuite({
    required this.name,
    required this.scenarios,
    required this.providers,
    required this.theme,
    this.hostBackground,
  });

  final String name;
  final List<AuditScenario> scenarios;

  /// A provider for every type a registered page reads; a scenario's own providers win.
  final List<SingleChildWidget> Function() providers;

  /// The app's theme at this family of revisions.
  final ThemeData Function() theme;

  /// The background behind a pumped page, as the app's own host (home, onboarding) painted it at
  /// these revisions; null uses the theme's scaffold colour.
  final Color? hostBackground;
}

/// One registered screen state. [id] names its PNGs (`<id>.png`, or `<id>-<step>.png` for a
/// scenario that captures several steps) and is what `--only` selects.
class AuditScenario {
  const AuditScenario({
    required this.id,
    required this.title,
    required this.page,
    required this.state,
    required this.run,
    this.prefs = const {},
  });

  /// Lowercase words joined by hyphens, unique across the registry.
  final String id;

  /// What a reviewer sees in the gallery.
  final String title;

  /// The production widget this scenario pumps, as `path/to/file.dart` (Widget).
  final String page;

  /// The seeded provider and fixture state, in one sentence.
  final String state;

  /// Extra SharedPreferences values on top of the signed-in fixture account.
  final Map<String, Object> prefs;

  /// Pumps the page and captures it; see [AuditRun].
  final Future<void> Function(AuditRun audit) run;
}

/// Blocks every connection that is not to the loopback fixture backend.
class LoopbackOnly extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..findProxy = (uri) {
        if (uri.host != '127.0.0.1') throw StateError('Visual audit blocks external request: ${uri.host}');
        return 'DIRECT';
      };
  }
}

const _surface = ValueKey('audit-surface');

/// Device walk. [app/scripts/demo_walk.sh] sets this so each [AuditRun.pump] pushes a real route
/// on one navigator. Providers stay above that navigator: a sheet opened from a page (the plans
/// sheet) looks up through the overlay, which is not a child of the page route. PNG capture leaves
/// this false and is unchanged.
bool auditWalkMode = false;

/// How long a walk holds each captured frame, in wall-clock time. `OMI_DEMO_WALK_HOLD_MS` overrides
/// it (the hermetic check uses a short hold).
Duration get auditWalkShotHold =>
    Duration(milliseconds: int.tryParse(Platform.environment['OMI_DEMO_WALK_HOLD_MS'] ?? '') ?? 1600);

/// 390x844 logical pixels, captured at 2x.
const auditViewport = Size(390, 844);

void walkLog(String message) {
  stdout.writeln(message);
  stdout.flush();
  // A piped `flutter test` can hold stdout. The recorder polls this file instead.
  final marker = Platform.environment['OMI_DEMO_WALK_MARKER'];
  if (marker == null || marker.isEmpty) return;
  if (message == 'DEMO_WALK_READY' || message == 'DEMO_WALK_DONE') {
    File(marker).writeAsStringSync('$message\n', flush: true);
  }
}

/// The app's fonts, for a walk that pumps pages outside `flutter test`'s font setup.
Future<void> loadAuditFonts() => _loadFonts();

/// Loads the app's fonts (FontManifest) plus Roboto from the pinned Flutter SDK, instead of the
/// test font's placeholder glyphs, so text metrics and overflow match the app.
Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  final dir = _materialFontsDir();
  if (dir == null) return;
  final loader = FontLoader('Roboto');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    final bytes = File('${dir.path}/Roboto-$weight.ttf').readAsBytesSync();
    loader.addFont(Future.value(ByteData.sublistView(bytes)));
  }
  await loader.load();
}

/// OMI_AUDIT_FONTS, else `<flutter>/bin/cache/artifacts/material_fonts` found above flutter_tester.
Directory? _materialFontsDir() {
  final explicit = Platform.environment['OMI_AUDIT_FONTS'];
  if (explicit != null && explicit.isNotEmpty) return Directory(explicit);
  var dir = File(Platform.resolvedExecutable).parent;
  for (var i = 0; i < 8; i++) {
    final candidate = Directory('${dir.path}/material_fonts');
    if (File('${candidate.path}/Roboto-Regular.ttf').existsSync()) return candidate;
    dir = dir.parent;
  }
  return null;
}

/// The per-scenario handle a scenario's [AuditScenario.run] drives.
class AuditRun {
  AuditRun._(this.tester, this.scenario, this.server, this._suite, this._shots, this._write);

  final WidgetTester tester;
  final AuditScenario scenario;

  /// The loopback fixture backend (hermetic boot), already started and signed in.
  final JourneyFixtureBackend server;
  final List<Map<String, Object?>> _shots;
  final AuditSuite _suite;
  final bool _write;

  /// Pumps [page] inside the production theme and localizations, with a broad inert provider
  /// roster. [providers] come last, so they win the lookup for the types they seed.
  Future<void> pump(Widget page, {List<SingleChildWidget> providers = const [], bool scaffold = true}) async {
    OmiColors.active = OmiColors.forBrightness(_auditLight ? Brightness.light : Brightness.dark);
    if (auditWalkMode) {
      await _walkPump(page, providers: providers, scaffold: scaffold);
      return;
    }
    tester.view.physicalSize = auditViewport;
    tester.view.devicePixelRatio = 1;
    await tester.pumpWidget(
      MultiProvider(
        providers: [..._suite.providers(), ...providers],
        child: RepaintBoundary(
          key: _surface,
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            navigatorKey: globalNavigatorKey,
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            // The app's own theme at this revision; Android font metrics (Roboto).
            theme: _auditLight ? buildOmiTheme(brightness: Brightness.light) : _suite.theme(),
            home: scaffold ? Scaffold(backgroundColor: _suite.hostBackground, body: page) : page,
          ),
        ),
      ),
    );
    await settle();
  }

  /// Pushes [page] so the route animation plays. The suite's providers wrap the navigator once;
  /// [providers] wrap only this page, so they win for the page and a sheet still sees the suite.
  Future<void> _walkPump(Widget page, {required List<SingleChildWidget> providers, required bool scaffold}) async {
    final body = scaffold ? Scaffold(backgroundColor: _suite.hostBackground, body: page) : page;
    final wrapped = providers.isEmpty ? body : MultiProvider(providers: providers, child: body);
    var nav = globalNavigatorKey.currentState;
    if (nav == null) {
      // A host test has no phone screen. A booted simulator keeps its own size.
      if (!Platform.isIOS && !Platform.isAndroid) {
        tester.view.physicalSize = auditViewport;
        tester.view.devicePixelRatio = 1;
      }
      await tester.pumpWidget(
        MultiProvider(
          providers: _suite.providers(),
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            navigatorKey: globalNavigatorKey,
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            theme: _auditLight ? buildOmiTheme(brightness: Brightness.light) : _suite.theme(),
            home: const SizedBox.shrink(),
          ),
        ),
      );
      nav = globalNavigatorKey.currentState;
      if (nav == null) throw StateError('Demo walk host installed without a navigator');
    }
    nav.push(MaterialPageRoute<void>(builder: (_) => wrapped));
    // Wall-clock: a live binding paints the push while this wait runs.
    await Future<void>.delayed(const Duration(milliseconds: 480));
    await tester.pump();
    await settle();
  }

  /// Pumps a neutral host whose only job is to open [open] (a sheet or dialog), then opens it.
  Future<void> pumpHost(
    void Function(BuildContext context) open, {
    List<SingleChildWidget> providers = const [],
    Color? background,
  }) async {
    await pump(
      Scaffold(
        backgroundColor: background,
        body: Builder(
          builder: (context) => Center(
            child: TextButton(onPressed: () => open(context), child: const Text('Open audit host')),
          ),
        ),
      ),
      providers: providers,
      scaffold: false,
    );
    await tap(find.text('Open audit host'));
  }

  /// Gives loopback I/O real event-loop turns, then finishes finite animations.
  /// Six turns, not one long wait: each turn yields the event loop so loopback
  /// responses (sub-millisecond locally) can land and the pump between turns
  /// advances fake frame time. This helper runs several times per scenario, so
  /// the per-turn delay dominated the smoke suite's wall time at 80 ms x 6.
  Future<void> settle() async {
    if (auditWalkMode) {
      await Future<void>.delayed(const Duration(milliseconds: 160));
      await tester.pump();
      final error = tester.takeException();
      if (error != null) throw error;
      return;
    }
    for (var i = 0; i < 6; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pump(const Duration(milliseconds: 200));
    }
  }

  Future<void> tap(Finder finder) async {
    await tester.tap(finder);
    await settle();
  }

  Future<void> longPress(Finder finder) async {
    await tester.longPress(finder);
    await settle();
  }

  Future<void> enterText(Finder finder, String text) async {
    await tester.enterText(finder, text);
    await settle();
  }

  /// Captures the surface as `<id>.png`, or `<id>-<step>.png` when [step] is given.
  Future<void> shot(String action, {String? step}) async {
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'Capture must not hide layout or runtime errors');
    if (auditWalkMode) {
      if (!_walkReadyAnnounced) {
        _walkReadyAnnounced = true;
        // The recorder starts when it sees this line. Stay on the first painted page until it does.
        walkLog('DEMO_WALK_READY');
        await Future<void>.delayed(const Duration(seconds: 3));
        await tester.pump();
      }
      final hold = auditWalkShotHold;
      if (hold > Duration.zero) {
        await Future<void>.delayed(hold);
        await tester.pump();
        expect(tester.takeException(), isNull, reason: 'Walk hold surfaced $action');
      }
      final name = step == null ? scenario.id : '${scenario.id}-$step';
      _shots.add({
        'scenario': scenario.id,
        'file': '$name.png',
        'action': action,
        'captured_at': DateTime.now().toUtc().toIso8601String(),
      });
      return;
    }
    final name = step == null ? scenario.id : '${scenario.id}-$step';
    expect(_shots.any((s) => s['file'] == '$name.png'), isFalse, reason: 'duplicate capture name $name');
    if (_write) {
      final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_surface));
      await tester.runAsync(() async {
        final image = await boundary.toImage(pixelRatio: 2);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await File('${_outputDir!.path}/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
        image.dispose();
      });
    }
    _shots.add({
      'scenario': scenario.id,
      'file': '$name.png',
      'action': action,
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    });
  }

  /// Captures the whole scroll range: the top, then one frame per [step] logical pixels, then the
  /// exact bottom (`-a`, `-b`, …). A page that does not scroll gets one frame, `<id>-a`.
  Future<void> scrollSeries(String action, {Finder? scrollable, double step = 700}) async {
    const letters = 'abcdefghijklmnop';
    await shot('$action (top)', step: letters[0]);
    final position = tester.state<ScrollableState>(scrollable ?? find.byType(Scrollable).first).position;
    final max = position.maxScrollExtent;
    if (max <= 0) return;
    var i = 1;
    for (var offset = step; offset < max && i < letters.length - 1; offset += step, i++) {
      await _moveScroll(position, offset);
      await shot('$action (scrolled ${offset.round()} of ${max.round()} px)', step: letters[i]);
    }
    await _moveScroll(position, max);
    await shot('$action (bottom, ${max.round()} px)', step: letters[i]);
  }

  Future<void> _moveScroll(ScrollPosition position, double offset) async {
    if (auditWalkMode) {
      position.animateTo(offset, duration: const Duration(milliseconds: 640), curve: Curves.easeOut);
      await Future<void>.delayed(const Duration(milliseconds: 700));
      await tester.pump();
      return;
    }
    position.jumpTo(offset);
    await settle();
  }
}

bool _walkReadyAnnounced = false;

/// Runs one registered scenario on the walk navigator. The suite's providers must include the
/// demo billing catalog when a later tap opens the plans sheet.
Future<void> driveWalkScenario(WidgetTester tester, AuditSuite suite, AuditScenario scenario) async {
  final server = JourneyHermeticBoot.backend;
  if (server == null) throw StateError('Demo walk requires JourneyHermeticBoot.start');
  await scenario.run(AuditRun._(tester, scenario, server, suite, <Map<String, Object?>>[], false));
}

Directory? _outputDir;
final bool _auditLight = Platform.environment['OMI_AUDIT_BRIGHTNESS'] == 'light';

/// Registers one test per scenario. With [output] set, writes `<id>*.png` and `frames.json` there;
/// without it (the smoke test), renders every scenario and writes nothing.
void runAuditScenarios(AuditSuite suite, {List<AuditScenario>? only, Directory? output}) {
  final scenarios = only ?? suite.scenarios;
  final frames = <Map<String, Object?>>[];
  setUpAll(() async {
    HttpOverrides.global = LoopbackOnly();
    await _loadFonts();
    _outputDir = output?..createSync(recursive: true);
  });
  tearDown(JourneyHermeticBoot.stop);

  for (final scenario in scenarios) {
    testWidgets(scenario.id, (tester) async {
      final server = await tester.runAsync(() => JourneyHermeticBoot.start(extraPrefs: scenario.prefs));
      addTearDown(() => server!.stop());
      final shots = <Map<String, Object?>>[];
      await scenario.run(AuditRun._(tester, scenario, server!, suite, shots, output != null));
      // Unwind the page's animations and timers in the test body: flutter_test checks for pending
      // timers before tearDowns run, and 16 s of fake time outlasts the pooled HTTP client's 15 s
      // idle timer. A live binding would wait in real time and does not check timers.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(
        tester.binding is AutomatedTestWidgetsFlutterBinding ? const Duration(seconds: 16) : const Duration(seconds: 1),
      );
      expect(shots, isNotEmpty, reason: '${scenario.id} captured nothing');
      if (output == null) return;
      for (final shot in shots) {
        frames.add({...shot, 'title': scenario.title, 'page': scenario.page, 'state': scenario.state});
      }
      File('${output.path}/frames.json').writeAsStringSync(const JsonEncoder.withIndent('  ').convert(frames));
    });
  }
}
