import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Folder for review PNGs of a widget test's screen; empty (the default) writes nothing and loads no fonts.
/// `flutter test --dart-define=SURFACE_RENDER_OUTPUT=<dir> <test>`.
const surfaceRenderOutput = String.fromEnvironment('SURFACE_RENDER_OUTPUT');

/// Real fonts for readable PNGs; only when [surfaceRenderOutput] is set, so text metrics stay unchanged otherwise.
Future<void> loadSurfaceRenderFonts() async {
  if (surfaceRenderOutput.isEmpty) return;
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
    '.SF Pro Text',
    'SF Pro Display',
    'CupertinoSystemText',
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

/// Writes the whole test view as `<name>.png` under [surfaceRenderOutput].
Future<void> writeSurfaceRender(WidgetTester tester, String name) async {
  if (surfaceRenderOutput.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = find.byType(RepaintBoundary).evaluate().first.renderObject! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(surfaceRenderOutput).create(recursive: true);
    await File('$surfaceRenderOutput/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
  });
}
