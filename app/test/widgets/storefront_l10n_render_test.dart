import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/on_device/on_device_settings_page.dart';
import 'package:omi/pages/settings/widgets/plans/storefront_plans_content.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/phone_power_source.dart';
import 'package:omi/ui/ui.dart';

import '../support/on_device_fakes.dart';

/// Localized plans sheet and on-device settings.
/// `--dart-define=OMI_L10N_EVIDENCE_DIR=<dir>` writes the PNGs.
void main() {
  const evidence = String.fromEnvironment('OMI_L10N_EVIDENCE_DIR');
  const boundaryKey = Key('l10n_evidence');

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Map<String, dynamic> sheet(String name) =>
      jsonDecode(File('../backend/tests/fixtures/storefront_v2_l10n/$name.json').readAsStringSync())
          as Map<String, dynamic>;

  Future<void> capture(WidgetTester tester, String name) async {
    if (evidence.isEmpty) return;
    await tester.pump();
    InlineSpan paint(InlineSpan span) {
      if (span is! TextSpan) return span;
      final style = span.style ?? const TextStyle();
      const iconFamilies = {'MaterialIcons', 'CupertinoIcons'};
      if (iconFamilies.contains(style.fontFamily)) return span;
      return TextSpan(
        text: span.text,
        style: style.copyWith(fontFamily: 'Arial Unicode', fontFamilyFallback: const ['Arial Unicode']),
        children: span.children?.map(paint).toList(),
      );
    }

    for (final element in find.byType(RichText).evaluate()) {
      final paragraph = element.renderObject;
      if (paragraph is RenderParagraph) paragraph.text = paint(paragraph.text);
    }
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
    boundary.markNeedsPaint();
    await tester.pump();
    await tester.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: 2);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(evidence).create(recursive: true);
      await File('$evidence/$name').writeAsBytes(bytes!.buffer.asUint8List());
      image.dispose();
    });
  }

  Future<void> pumpLocalized(
    WidgetTester tester, {
    required Locale locale,
    required Widget home,
    Size size = const Size(390, 1500),
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final previous = OmiColors.active;
    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = previous);
    await tester.runAsync(() async {
      final unicode = File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf');
      if (unicode.existsSync()) {
        final loader = FontLoader('Arial Unicode')
          ..addFont(Future.value(ByteData.sublistView(unicode.readAsBytesSync())));
        await loader.load();
      }
      await _loadIconFont('MaterialIcons', _materialIconsFont());
      final cupertino = _packageAsset('cupertino_icons', 'assets/CupertinoIcons.ttf');
      if (cupertino != null) await _loadIconFont('CupertinoIcons', cupertino);
    });
    final theme = buildOmiTheme(brightness: Brightness.dark).copyWith(
      platform: TargetPlatform.iOS,
      textTheme: buildOmiTheme(brightness: Brightness.dark).textTheme.apply(
        fontFamily: 'Arial Unicode',
        fontFamilyFallback: const ['Arial Unicode'],
      ),
    );
    await tester.pumpWidget(RepaintBoundary(
      key: boundaryKey,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        locale: locale,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: theme,
        home: home,
      ),
    ));
    await tester.pump();
  }

  OnDeviceTranscriptionController installed() {
    final controller = OnDeviceTranscriptionController(
      model: FakeOnDeviceModel(
        const OnDeviceModelStatus(phase: OnDeviceModelPhase.installed, sizeBytes: 443 * 1024 * 1024),
        'parakeet_v2',
      ),
      power: const UnknownPhonePowerSource(),
    )..debugActivate(settings: const OnDeviceSettings(enabled: true));
    return controller;
  }

  for (final locale in const [
    (Locale('es'), 'es'),
    (Locale('ja'), 'ja'),
    (Locale('ar'), 'ar'),
  ]) {
    testWidgets('plans sheet ${locale.$2}', (tester) async {
      final data = PlanStorefront.fromJson(sheet('${locale.$2}_free_settings'));
      await pumpLocalized(
        tester,
        locale: locale.$1,
        home: Scaffold(
          body: StorefrontPlansContent(
            storefront: data,
            onRetry: () async {},
            onManage: () async {},
            onSelect: (_, __) async {},
          ),
        ),
      );
      expect(find.text(data.header), findsOneWidget);
      expect(find.textContaining('Choose your plan'), findsNothing);
      expect(tester.takeException(), isNull);
      await capture(tester, 'plans-${locale.$2}.png');
    });

    testWidgets('settings ${locale.$2}', (tester) async {
      final data = PlanStorefront.fromJson(sheet('${locale.$2}_plus_budget80'));
      final usage = data.usage!;
      await pumpLocalized(
        tester,
        locale: locale.$1,
        size: const Size(390, 900),
        home: OnDeviceSettingsView(
          controller: installed(),
          usage: usage,
          plansSheetAvailable: true,
          showSaveUsage: true,
          pendingSeconds: 0,
          pendingBytes: 0,
          onGetMoreUsage: () {},
        ),
      );
      expect(
        find.byWidgetPredicate((widget) {
          if (widget is! Text) return false;
          final shown = (widget.data ?? widget.textSpan?.toPlainText() ?? '').replaceAll('\u2060', '');
          return shown == usage.meterLine;
        }),
        findsOneWidget,
      );
      if (locale.$2 == 'ja') {
        final element = find
            .byWidgetPredicate((widget) {
              if (widget is! RichText) return false;
              return widget.text.toPlainText().contains('リセット'.split('').join('\u2060'));
            })
            .evaluate()
            .single;
        final paragraph = element.renderObject! as RenderParagraph;
        final plain = paragraph.text.toPlainText();
        final start = plain.indexOf('1');
        final end = plain.indexOf('ト') + 1;
        final boxes = paragraph.getBoxesForSelection(TextSelection(baseOffset: start, extentOffset: end));
        expect(boxes.map((box) => box.top.round()).toSet(), hasLength(1));
      }
      expect(find.text(usage.moreLabel!), findsOneWidget);
      expect(find.textContaining('hours of recording left'), findsNothing);
      expect(find.text('Get more usage'), findsNothing);
      expect(tester.takeException(), isNull);
      await capture(tester, 'settings-${locale.$2}.png');
    });
  }

  testWidgets('settings ko', (tester) async {
    final data = PlanStorefront.fromJson(sheet('ko_plus_budget80'));
    final usage = data.usage!;
    await pumpLocalized(
      tester,
      locale: const Locale('ko'),
      size: const Size(390, 900),
      home: OnDeviceSettingsView(
        controller: installed(),
        usage: usage,
        plansSheetAvailable: true,
        showSaveUsage: true,
        pendingSeconds: 0,
        pendingBytes: 0,
        onGetMoreUsage: () {},
      ),
    );
    expect(
      find.byWidgetPredicate((widget) {
        if (widget is! Text) return false;
        final shown = (widget.data ?? widget.textSpan?.toPlainText() ?? '').replaceAll('\u2060', '');
        return shown == usage.meterLine;
      }),
      findsOneWidget,
    );
    final element = find
        .byWidgetPredicate((widget) {
          if (widget is! RichText) return false;
          return widget.text.toPlainText().contains('초기화'.split('').join('\u2060'));
        })
        .evaluate()
        .single;
    final paragraph = element.renderObject! as RenderParagraph;
    final plain = paragraph.text.toPlainText();
    final start = plain.indexOf('1');
    final end = plain.lastIndexOf('화') + 1;
    final boxes = paragraph.getBoxesForSelection(TextSelection(baseOffset: start, extentOffset: end));
    expect(boxes.map((box) => box.top.round()).toSet(), hasLength(1));
    expect(find.text(usage.moreLabel!), findsOneWidget);
    expect(find.text('Get more usage'), findsNothing);
    expect(tester.takeException(), isNull);
    await capture(tester, 'settings-ko.png');
  });
}

Future<void> _loadIconFont(String family, File file) async {
  final loader = FontLoader(family)
    ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(file.readAsBytesSync()))));
  await loader.load();
}

File? _packageAsset(String package, String asset) {
  final path = File('.dart_tool/package_config.json');
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
