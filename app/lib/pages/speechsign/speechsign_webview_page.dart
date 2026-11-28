import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class SpeechSignWebViewPage extends StatefulWidget {
  final String url;
  final String title;

  const SpeechSignWebViewPage({
    super.key,
    this.url = 'https://speechsign.vercel.app',
    this.title = 'SpeechSign',
  });

  @override
  State<SpeechSignWebViewPage> createState() => _SpeechSignWebViewPageState();
}

class _SpeechSignWebViewPageState extends State<SpeechSignWebViewPage> {
  late final WebViewController _controller;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (_) {
            if (mounted) setState(() => _isLoading = false);
          },
          onWebResourceError: (_) {
            if (mounted) setState(() => _isLoading = false);
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_isLoading)
            const Center(child: CircularProgressIndicator()),
        ],
      ),
    );
  }
}
