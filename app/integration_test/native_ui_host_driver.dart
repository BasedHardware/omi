import 'dart:io';
import 'dart:typed_data';

import 'package:image/image.dart' as image;
import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  final directory = Directory(Platform.environment['NATIVE_UI_EVIDENCE_DIR'] ?? 'build/native-ui-evidence');
  await directory.create(recursive: true);
  await integrationDriver(onScreenshot: (name, bytes, [arguments]) async {
    await File('${directory.path}/$name.png').writeAsBytes(bytes);
    final appearance = RegExp(r'^real-native-settings-(?:system-|search-)?(dark|light)$').firstMatch(name)?.group(1);
    if (appearance != null) {
      final screenshot = image.decodePng(Uint8List.fromList(bytes));
      if (screenshot == null) return false;
      // Sample the empty List margin, away from labels and the debug banner.
      final luminance = screenshot.getPixel(0, screenshot.height ~/ 2).luminance;
      return appearance == 'dark' ? luminance < 70 : luminance > 180;
    }
    return true;
  });
}
