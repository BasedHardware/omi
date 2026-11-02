import 'dart:convert';

import 'bridge_stub.dart' if (dart.library.js_interop) 'bridge_web.dart';

/// Messages the Omi app's onboarding webview understands (see `web_onboarding_page.dart` in the app).
abstract final class OmiBridge {
  static void ready() => _send({'type': 'ready'});
  static void setName(String name) => _send({'type': 'set_name', 'name': name});
  static void permission(String kind) => _send({'type': 'permission', 'kind': kind});
  static void complete() => _send({'type': 'complete'});
  static void fallback() => _send({'type': 'fallback'});

  static void _send(Map<String, Object> message) => postToHost(jsonEncode(message));
}
