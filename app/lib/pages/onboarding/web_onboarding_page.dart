import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/logger.dart';

/// What the web onboarding page asked for when it closed.
enum WebOnboardingResult { completed, fallback }

/// First-run onboarding rendered from a web page (flag `onboarding-webview`), so the steps, copy
/// and order change over the air. The page runs after sign-in and consent; the native wrapper still
/// owns completion (server sync, preferences, home routing).
///
/// Bridge: the page posts JSON to the `OmiOnboarding` channel —
/// `{"type":"ready"}`, `{"type":"set_name","name":"…"}`,
/// `{"type":"permission","kind":"notifications"|"location"|"background"}`,
/// `{"type":"complete"}`, `{"type":"fallback"}` — and may define
/// `window.OmiOnboardingHost.onPermission(kind, status)` to receive results.
///
/// Fail-open: a page that errors or never reports ready within [loadTimeout] returns
/// [WebOnboardingResult.fallback] and the native steps run exactly as before.
class WebOnboardingPage extends StatefulWidget {
  const WebOnboardingPage({super.key, required this.url});

  final Uri url;

  static const loadTimeout = Duration(seconds: 10);
  static const channel = 'OmiOnboarding';

  @override
  State<WebOnboardingPage> createState() => _WebOnboardingPageState();
}

class _WebOnboardingPageState extends State<WebOnboardingPage> {
  WebViewController? _controller;
  Timer? _timeout;
  bool _ready = false;
  bool _closed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _prepare());
  }

  @override
  void dispose() {
    _timeout?.cancel();
    super.dispose();
  }

  void _prepare() {
    if (!mounted) return;
    final params = Map<String, String>.from(widget.url.queryParameters)
      ..['platform'] = Platform.isIOS ? 'ios' : (Platform.isAndroid ? 'android' : 'other')
      ..['locale'] = Localizations.localeOf(context).toLanguageTag();
    final name = SharedPreferencesUtil().givenName;
    if (name.isNotEmpty) params['name'] = name;
    final controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..addJavaScriptChannel(WebOnboardingPage.channel, onMessageReceived: (message) => _onMessage(message.message))
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (request) =>
              request.url.startsWith('https://') ? NavigationDecision.navigate : NavigationDecision.prevent,
          onWebResourceError: (error) {
            if (error.isForMainFrame == false) return;
            Logger.debug('Web onboarding load error: ${error.description}');
            _fallback(OnboardingWebviewFallbackReason.loadError);
          },
          onHttpError: (error) {
            final status = error.response?.statusCode ?? 0;
            if (status >= 400 && _isMainFrame(error.request?.uri)) {
              _fallback(OnboardingWebviewFallbackReason.loadError);
            }
          },
        ),
      );
    setState(() => _controller = controller);
    _timeout = Timer(WebOnboardingPage.loadTimeout, () {
      if (!_ready) _fallback(OnboardingWebviewFallbackReason.timeout);
    });
    controller.loadRequest(widget.url.replace(queryParameters: params));
  }

  /// Whether a failed request is the page itself rather than something it loads.
  bool _isMainFrame(Uri? uri) => uri == null || (uri.host == widget.url.host && uri.path == widget.url.path);

  Future<void> _onMessage(String raw) async {
    Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return;
    }
    if (decoded is! Map) return;
    switch (decoded['type']) {
      case 'ready':
        _timeout?.cancel();
        if (mounted && !_ready) setState(() => _ready = true);
      case 'set_name':
        final name = decoded['name'];
        if (name is String && name.trim().isNotEmpty) SharedPreferencesUtil().givenName = name.trim();
      case 'permission':
        await _permission(decoded['kind']);
      case 'complete':
        _close(WebOnboardingResult.completed);
      case 'fallback':
        _fallback(OnboardingWebviewFallbackReason.pageRequested);
    }
  }

  Future<void> _permission(Object? kind) async {
    OnboardingPermission? permission;
    for (final value in OnboardingPermission.values) {
      if (value.name == kind) permission = value;
    }
    if (permission == null || !mounted) return;
    final source = PlatformOnboardingPermissionsSource(context.read<OnboardingProvider>());
    try {
      await source.request(permission);
    } catch (_) {}
    final status = await source.status(permission);
    final controller = _controller;
    if (controller == null) return;
    try {
      await controller.runJavaScript(
        'window.OmiOnboardingHost && window.OmiOnboardingHost.onPermission && '
        'window.OmiOnboardingHost.onPermission(${jsonEncode(permission.name)}, ${jsonEncode(status.name)})',
      );
    } catch (_) {}
  }

  void _close(WebOnboardingResult result) {
    if (_closed || !mounted) return;
    _closed = true;
    _timeout?.cancel();
    Navigator.of(context).pop(result);
  }

  void _fallback(OnboardingWebviewFallbackReason reason) {
    if (_closed) return;
    const TypedEvents().emit(OnboardingWebviewFallback(reason: reason));
    _close(WebOnboardingResult.fallback);
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(
          children: [
            if (controller != null) Positioned.fill(child: WebViewWidget(controller: controller)),
            if (!_ready) const Center(child: OmiSpinner(color: Colors.white)),
          ],
        ),
      ),
    );
  }
}
