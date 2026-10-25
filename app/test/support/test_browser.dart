import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Native bridge seam: model an installed browser hidden from package queries.
class TestBrowser {
  static const channel = MethodChannel('plugins.flutter.io/url_launcher');
  bool opened = true;
  int queries = 0;

  /// When set, a launch answers only once this completes, holding the browser open.
  Completer<bool>? pending;
  final launches = <(String, bool, bool)>[];

  void install() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'canLaunch') {
        queries++;
        return false;
      }
      if (call.method == 'launch') {
        final arguments = call.arguments as Map;
        launches.add((arguments['url'] as String, arguments['useWebView'] as bool, arguments['useSafariVC'] as bool));
        return pending?.future ?? opened;
      }
      return null;
    });
  }

  void dispose() =>
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
}
