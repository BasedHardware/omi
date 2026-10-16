import 'dart:js_interop';

@JS('OmiOnboarding')
external JSObject? get _channel;

@JS('OmiOnboarding.postMessage')
external void _post(JSString message);

/// Posts to the Omi app's `OmiOnboarding` JavaScript channel when the page runs inside the app's
/// onboarding webview; a plain browser has no channel and the call is a no-op.
void postToHost(String json) {
  if (_channel == null) return;
  _post(json.toJS);
}
