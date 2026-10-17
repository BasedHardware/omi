import 'dart:io';
import 'dart:async';
import 'dart:typed_data';

import 'package:image/image.dart' as image;
import 'package:integration_test/integration_test_driver_extended.dart';

bool hasBackGlyph(image.Image screenshot) {
  var bright = 0;
  // These inert dark phone fixtures use one Back control to the left of the
  // centered title. Exclude the status bar and the first content section.
  for (var y = (screenshot.height * 0.065).round(); y < screenshot.height * 0.125; y++) {
    for (var x = (screenshot.width * 0.02).round(); x < screenshot.width * 0.20; x++) {
      if (screenshot.getPixel(x, y).luminance > 180) bright++;
    }
  }
  return bright > 50;
}

Future<void> main() async {
  final directory = Directory(Platform.environment['NATIVE_UI_EVIDENCE_DIR'] ?? 'build/native-ui-evidence');
  await directory.create(recursive: true);
  final port = int.tryParse(Platform.environment['NATIVE_UI_SCREENSHOT_PORT'] ?? '') ?? 0;
  if (port != 0) {
    final simulator = Platform.environment['NATIVE_UI_SIMULATOR_ID'];
    if (simulator == null || !RegExp(r'^[A-Fa-f0-9-]{36}$').hasMatch(simulator)) {
      throw ArgumentError('Display capture requires an explicitly selected Simulator');
    }
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, port);
    unawaited(server.forEach((request) async {
      final name = request.uri.queryParameters['name'] ?? '';
      if (request.method != 'GET' || request.uri.path != '/capture' || !RegExp(r'^[a-z0-9-]{1,100}$').hasMatch(name)) {
        request.response.statusCode = 400;
      } else {
        try {
          // UIKit drawViewHierarchy is retained below as separate evidence.
          // CoreSimulator captures the native glass compositor's displayed pixels.
          final screenshotPath = '${directory.path}/$name-display.png';
          final needsBack = ['real-native-voice-review-dark', 'real-native-phone-number-dark'].contains(name);
          final deadline = DateTime.now().add(const Duration(seconds: 12));
          var ready = false;
          do {
            final capture = await Process.run('xcrun', ['simctl', 'io', simulator, 'screenshot', screenshotPath])
                .timeout(const Duration(seconds: 5));
            if (capture.exitCode != 0) break;
            final screenshot = needsBack ? image.decodePng(await File(screenshotPath).readAsBytes()) : null;
            ready = !needsBack || screenshot != null && hasBackGlyph(screenshot);
            if (!ready) await Future<void>.delayed(const Duration(milliseconds: 400));
          } while (!ready && DateTime.now().isBefore(deadline));
          request.response.statusCode = ready ? 200 : 500;
        } catch (_) {
          request.response.statusCode = 500;
        }
      }
      await request.response.close();
    }));
  }
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
