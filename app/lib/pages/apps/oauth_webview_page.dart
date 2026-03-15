import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:webview_flutter/webview_flutter.dart';
import 'package:omi/utils/logger.dart';

/// WebView page for OAuth flows that redirect to localhost.
///
/// Many MCP servers (Zomato, Swiggy, etc.) only whitelist localhost redirect URIs.
/// This page intercepts the localhost redirect, extracts the auth code,
/// and sends it to the app's server callback endpoint.
class OAuthWebViewPage extends StatefulWidget {
  final String authUrl;
  final String callbackBaseUrl;
  final String title;

  const OAuthWebViewPage({
    super.key,
    required this.authUrl,
    required this.callbackBaseUrl,
    this.title = 'Connect',
  });

  @override
  State<OAuthWebViewPage> createState() => _OAuthWebViewPageState();
}

class _OAuthWebViewPageState extends State<OAuthWebViewPage> {
  late final WebViewController _controller;
  bool _isLoading = true;
  bool _isExchanging = false;

  @override
  void initState() {
    super.initState();

    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int progress) {
            if (progress == 100 && mounted) {
              setState(() => _isLoading = false);
            }
          },
          onPageStarted: (String url) {
            if (mounted) setState(() => _isLoading = true);
          },
          onNavigationRequest: (NavigationRequest request) {
            final url = request.url;

            // Intercept localhost redirects (OAuth callback)
            if (url.startsWith('http://localhost') || url.startsWith('http://127.0.0.1')) {
              Logger.debug('OAuth: Intercepted localhost redirect: $url');
              _handleLocalhostRedirect(url);
              return NavigationDecision.prevent;
            }

            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.authUrl));
  }

  Future<void> _handleLocalhostRedirect(String url) async {
    if (_isExchanging) return;
    setState(() => _isExchanging = true);

    try {
      final uri = Uri.parse(url);
      final code = uri.queryParameters['code'];
      final state = uri.queryParameters['state'];

      if (code == null || state == null) {
        Logger.warning('OAuth: Missing code or state in callback URL');
        if (mounted) Navigator.of(context).pop(false);
        return;
      }

      // Forward code and state to the app's server callback
      final callbackUrl =
          '${widget.callbackBaseUrl}?code=${Uri.encodeComponent(code)}&state=${Uri.encodeComponent(state)}';
      Logger.debug('OAuth: Exchanging code via $callbackUrl');

      final response = await http.get(Uri.parse(callbackUrl));

      if (response.statusCode == 200) {
        Logger.debug('OAuth: Token exchange successful');
        if (mounted) Navigator.of(context).pop(true);
      } else {
        Logger.warning('OAuth: Token exchange failed with ${response.statusCode}');
        if (mounted) Navigator.of(context).pop(false);
      }
    } catch (e) {
      Logger.error('OAuth: Error during token exchange: $e');
      if (mounted) Navigator.of(context).pop(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(widget.title),
        backgroundColor: Colors.black,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.of(context).pop(false),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_isLoading || _isExchanging)
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(color: Colors.deepPurple),
                  if (_isExchanging) ...[
                    const SizedBox(height: 16),
                    const Text('Completing setup...', style: TextStyle(color: Colors.white70)),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}
