import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  final directory = Directory(Platform.environment['NATIVE_UI_EVIDENCE_DIR'] ?? 'build/native-ui-evidence');
  await directory.create(recursive: true);
  await integrationDriver(onScreenshot: (name, bytes, [arguments]) async {
    await File('${directory.path}/$name.png').writeAsBytes(bytes);
    return true;
  });
}
