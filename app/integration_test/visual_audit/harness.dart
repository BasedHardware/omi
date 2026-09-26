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
import 'package:omi/ui/omi_tokens.dart';

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

/// 390x844 logical pixels, captured at 2x. OMI_AUDIT_VIEWPORT=WxH captures at another phone size
/// (e.g. 375x667 for an iPhone SE, 360x740 for a small Android phone).
final Size auditViewport = _sizeFrom(Platform.environment['OMI_AUDIT_VIEWPORT']) ?? const Size(390, 844);

/// OMI_AUDIT_TEXT_SCALE: the reader's text size (1.0 by default; 1.3 is "Larger Text").
final double? _auditTextScale = double.tryParse(Platform.environment['OMI_AUDIT_TEXT_SCALE'] ?? '');

/// OMI_AUDIT_LINT=1: every capture also records layout findings (errors such as overflow, one word
/// alone on a wrapped line, text cut short) in `layout.json` instead of stopping at the first error.
/// OMI_AUDIT_NO_PNG=1 skips the images (a lint-only pass).
final bool _lint = Platform.environment['OMI_AUDIT_LINT'] == '1';
final bool _noPng = Platform.environment['OMI_AUDIT_NO_PNG'] == '1';

Size? _sizeFrom(String? value) {
  final parts = (value ?? '').toLowerCase().split('x');
  if (parts.length != 2) return null;
  final width = double.tryParse(parts[0]);
  final height = double.tryParse(parts[1]);
  return width == null || height == null ? null : Size(width, height);
}

/// Layout findings of this run, rewritten to `layout.json` after every capture.
final List<Map<String, Object?>> _layoutFindings = [];

/// The widgets that made [node], nearest first, without the render-only wrappers.
String _creatorOf(RenderObject node) {
  final creator = node.debugCreator;
  if (creator is! DebugCreator) return '';
  return creator.element.debugGetCreatorChain(10);
}

/// A paragraph's layout finding: one word alone on its last wrapped line ("orphan"), or text cut
/// short by maxLines ("truncated"). Null when it reads fine.
Map<String, Object?>? _paragraphFinding(RenderParagraph paragraph) {
  final plain = paragraph.text.toPlainText(includeSemanticsLabels: false);
  if (plain.trim().isEmpty) return null;
  var placeholder = false;
  paragraph.text.visitChildren((span) {
    if (span is PlaceholderSpan) placeholder = true;
    return !placeholder;
  });
  final text = plain.length > 120 ? '${plain.substring(0, 117)}...' : plain;
  if (paragraph.didExceedMaxLines) {
    return {'kind': 'truncated', 'text': text, 'maxLines': paragraph.maxLines, 'width': paragraph.size.width};
  }
  if (placeholder || !paragraph.softWrap || paragraph.maxLines == 1) return null;
  final painter = TextPainter(
    text: paragraph.text,
    textAlign: paragraph.textAlign,
    textDirection: paragraph.textDirection,
    textScaler: paragraph.textScaler,
    maxLines: paragraph.maxLines,
    locale: paragraph.locale,
    strutStyle: paragraph.strutStyle,
    textWidthBasis: paragraph.textWidthBasis,
    textHeightBehavior: paragraph.textHeightBehavior,
  )..layout(maxWidth: paragraph.constraints.maxWidth);
  try {
    final lines = painter.computeLineMetrics().length;
    if (lines < 2) return null;
    final last = painter.getLineBoundary(TextPosition(offset: plain.length));
    if (last.start <= 0 || last.end > plain.length || plain[last.start - 1] == '\n') return null;
    final lastLine = plain.substring(last.start, last.end).trim();
    if (lastLine.isEmpty || lastLine.contains(RegExp(r'\s'))) return null;
    // A one- or two-word label that wraps does not fit its line ("Voice / Response"); longer copy
    // left one word alone ("… to listen all / day.").
    final words = plain.trim().split(RegExp(r'\s+')).length;
    return {
      'kind': words < 3 ? 'cramped' : 'orphan',
      'text': text,
      'lastLine': lastLine,
      'lines': lines,
      'width': paragraph.size.width,
    };
  } finally {
    painter.dispose();
  }
}

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
    tester.view.physicalSize = auditViewport;
    tester.view.devicePixelRatio = 1;
    final scale = _auditTextScale;
    if (scale != null) tester.platformDispatcher.textScaleFactorTestValue = scale;
    await tester.pumpWidget(MultiProvider(
      providers: [..._suite.providers(), ...providers],
      child: RepaintBoundary(
        key: _surface,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          navigatorKey: globalNavigatorKey,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          // The app's own theme at this revision; Android font metrics (Roboto).
          theme: _suite.theme(),
          home: scaffold ? Scaffold(backgroundColor: _suite.hostBackground, body: page) : page,
        ),
      ),
    ));
    await settle();
  }

  /// Pumps a neutral host whose only job is to open [open] (a sheet or dialog), then opens it.
  Future<void> pumpHost(void Function(BuildContext context) open,
      {List<SingleChildWidget> providers = const [], Color? background}) async {
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
  Future<void> settle() async {
    for (var i = 0; i < 6; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 80)));
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
    final name = step == null ? scenario.id : '${scenario.id}-$step';
    if (_lint) {
      _recordLayout(name, tester.takeException());
    } else {
      expect(tester.takeException(), isNull, reason: 'Capture must not hide layout or runtime errors');
    }
    expect(_shots.any((s) => s['file'] == '$name.png'), isFalse, reason: 'duplicate capture name $name');
    if (_write && !_noPng) {
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

  /// Lint mode: records [error] and the text findings of what is on screen now for capture [name].
  void _recordLayout(String name, Object? error) {
    final base = {
      'scenario': scenario.id,
      'shot': name,
      'viewport': '${auditViewport.width.round()}x${auditViewport.height.round()}',
      'textScale': _auditTextScale ?? 1.0,
    };
    if (error != null) {
      _layoutFindings.add({...base, 'kind': 'error', 'text': '$error'.split('\n').take(3).join(' ')});
    }
    void visit(RenderObject node) {
      if (node is RenderParagraph && node.attached && node.hasSize) {
        final finding = _paragraphFinding(node);
        if (finding != null) _layoutFindings.add({...base, ...finding, 'creator': _creatorOf(node)});
      }
      node.visitChildren(visit);
    }

    visit(tester.renderObject(find.byKey(_surface)));
    // Full-width buttons and where they sit, so a journey's primary buttons can be compared: every
    // step's Continue should share one bottom gap and side inset. Matched by name: this harness
    // imports nothing from the app.
    final surface = tester.getRect(find.byKey(_surface));
    for (final element in find.byWidgetPredicate((w) => w.runtimeType.toString() == 'OmiButton').evaluate()) {
      final box = element.renderObject;
      if (box is! RenderBox || !box.attached || !box.hasSize) continue;
      final rect = box.localToGlobal(Offset.zero) & box.size;
      if (rect.width < surface.width * 0.8) continue;
      final label = find.descendant(of: find.byWidget(element.widget), matching: find.byType(RichText)).evaluate();
      _layoutFindings.add({
        ...base,
        'kind': 'button',
        'text': label.isEmpty ? '' : (label.first.widget as RichText).text.toPlainText(),
        'bottomGap': (surface.bottom - rect.bottom).roundToDouble(),
        'left': (rect.left - surface.left).roundToDouble(),
        'right': (surface.right - rect.right).roundToDouble(),
      });
    }
    final dir = _outputDir;
    if (dir != null) {
      File('${dir.path}/layout.json').writeAsStringSync(const JsonEncoder.withIndent('  ').convert(_layoutFindings));
    }
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
      position.jumpTo(offset);
      await settle();
      await shot('$action (scrolled ${offset.round()} of ${max.round()} px)', step: letters[i]);
    }
    position.jumpTo(max);
    await settle();
    await shot('$action (bottom, ${max.round()} px)', step: letters[i]);
  }
}

Directory? _outputDir;

/// Registers one test per scenario. With [output] set, writes `<id>*.png` and `frames.json` there;
/// without it (the smoke test), renders every scenario and writes nothing.
void runAuditScenarios(AuditSuite suite, {List<AuditScenario>? only, Directory? output}) {
  final scenarios = only ?? suite.scenarios;
  final frames = <Map<String, Object?>>[];
  setUpAll(() async {
    HttpOverrides.global = LoopbackOnly();
    // OMI_AUDIT_THEME=light captures every scenario in the light palette (Settings → Appearance).
    OmiColors.use(Platform.environment['OMI_AUDIT_THEME'] == 'light' ? OmiPalette.light : OmiPalette.dark);
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
      await tester.pump(tester.binding is AutomatedTestWidgetsFlutterBinding
          ? const Duration(seconds: 16)
          : const Duration(seconds: 1));
      expect(shots, isNotEmpty, reason: '${scenario.id} captured nothing');
      if (output == null) return;
      for (final shot in shots) {
        frames.add({...shot, 'title': scenario.title, 'page': scenario.page, 'state': scenario.state});
      }
      File('${output.path}/frames.json').writeAsStringSync(const JsonEncoder.withIndent('  ').convert(frames));
    });
  }
}
