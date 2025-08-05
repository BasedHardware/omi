import 'package:flutter/material.dart';
import 'package:omi/env/env.dart';
import 'package:webview_flutter/webview_flutter.dart';

class PaymentWebViewPage extends StatefulWidget {
  final String checkoutUrl;

  const PaymentWebViewPage({super.key, required this.checkoutUrl});

  @override
  State<PaymentWebViewPage> createState() => _PaymentWebViewPageState();
}

class _PaymentWebViewPageState extends State<PaymentWebViewPage> {
  late final WebViewController _controller;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();

    final successUrl = '${Env.apiBaseUrl}v1/payments/success';
    final cancelUrl = '${Env.apiBaseUrl}v1/payments/cancel';

    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int progress) {
            if (progress == 100) {
              setState(() {
                _isLoading = false;
              });
            }
          },
          onPageStarted: (String url) {
            setState(() {
              _isLoading = true;
            });
          },
          onNavigationRequest: (NavigationRequest request) {
            if (request.url.startsWith(successUrl)) {
              debugPrint('Payment successful, closing webview');
              Navigator.of(context).pop(true); // Pop with success result
              return NavigationDecision.prevent;
            }
            if (request.url.startsWith(cancelUrl)) {
              debugPrint('Payment cancelled, closing webview');
              Navigator.of(context).pop(false); // Pop with cancel result
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.checkoutUrl));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Complete Your Upgrade'),
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
          if (_isLoading)
            const Center(
              child: CircularProgressIndicator(color: Colors.deepPurple),
            ),
        ],
      ),
    );
  }
}
