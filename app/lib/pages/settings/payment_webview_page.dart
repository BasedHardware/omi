import 'package:flutter/material.dart';

import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/env/env.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

class PaymentWebViewPage extends StatefulWidget {
  final String checkoutUrl;
  final String? title;

  const PaymentWebViewPage({super.key, required this.checkoutUrl, this.title});

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
              Logger.debug('Payment successful, closing webview');
              Navigator.of(context).pop(true); // Pop with success result
              return NavigationDecision.prevent;
            }
            if (request.url.startsWith(cancelUrl)) {
              Logger.debug('Payment cancelled, closing webview');
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
        title: Text(widget.title ?? context.l10n.completeYourUpgrade),
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
