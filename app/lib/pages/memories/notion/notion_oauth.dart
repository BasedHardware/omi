import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'dart:async';

class NotionAuthWebView extends StatefulWidget {
  final String authorizationUrl;
  final String redirectUri;

  NotionAuthWebView(
      {required this.authorizationUrl, required this.redirectUri});

  @override
  _NotionAuthWebViewState createState() => _NotionAuthWebViewState();
}

class _NotionAuthWebViewState extends State<NotionAuthWebView> {
  late final WebViewController _controller;
  final _appLinks = AppLinks();

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setNavigationDelegate(NavigationDelegate(
        onNavigationRequest: (NavigationRequest request) {
          if (request.url.startsWith(widget.redirectUri)) {
            // Extract authorization code from the redirected URL
            final uri = Uri.parse(request.url);
            final authorizationCode = uri.queryParameters['code'];
            if (authorizationCode != null) {
              Navigator.pop(context, authorizationCode);
            }
            return NavigationDecision.prevent;
          }
          return NavigationDecision.navigate;
        },
      ))
      ..loadRequest(Uri.parse(widget.authorizationUrl));

    _appLinks.uriLinkStream.listen((Uri? uri) {
      if (uri != null && uri.toString().startsWith(widget.redirectUri)) {
        final authorizationCode = uri.queryParameters['code'];
        if (authorizationCode != null) {
          Navigator.pop(context, authorizationCode);
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Notion Authorization'),
      ),
      body: WebViewWidget(controller: _controller),
    );
  }
}
