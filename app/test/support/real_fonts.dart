import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

/// Loads the app's own fonts (FontManifest) and Roboto, the font widget tests render with, so text
/// measures as it does on a phone instead of in the test font's square glyphs. For tests about
/// wrapping, heights and overflow.
Future<void> loadRealFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  var dir = File(Platform.resolvedExecutable).parent;
  for (var i = 0; i < 8; i++) {
    final fonts = Directory('${dir.path}/material_fonts');
    if (File('${fonts.path}/Roboto-Regular.ttf').existsSync()) {
      final roboto = FontLoader('Roboto');
      for (final weight in ['Regular', 'Medium', 'Bold']) {
        roboto.addFont(Future.value(ByteData.sublistView(File('${fonts.path}/Roboto-$weight.ttf').readAsBytesSync())));
      }
      await roboto.load();
      return;
    }
    dir = dir.parent;
  }
}
