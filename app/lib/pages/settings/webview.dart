import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class PageWebView extends StatefulWidget {
  final String url;
  final String title;

  const PageWebView({super.key, required this.url, required this.title});

  @override
  State<PageWebView> createState() => _PageWebViewState();
}

class _PageWebViewState extends State<PageWebView> {
  late WebViewController webViewController;
  int progress = 0;

  @override
  initState() {
    webViewController = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int p) {
            if (mounted) {
              setState(() {
                progress = p;
              });
            }
          },
          onPageStarted: (String url) {},
          onPageFinished: (String url) {},
          onHttpError: (HttpResponseError error) {},
          onWebResourceError: (WebResourceError error) {},
          onNavigationRequest: (NavigationRequest request) {
            // Allow navigation to omi.me domains and common payment/checkout domains
            final Uri uri = Uri.parse(request.url);
            final String host = uri.host.toLowerCase();

            // Allow omi.me and its subdomains, plus common checkout/payment domains
            if (host.contains('omi.me') ||
                host.contains('shopify') ||
                host.contains('stripe') ||
                host.contains('paypal') ||
                request.url == widget.url) {
              return NavigationDecision.navigate;
            }

            return NavigationDecision.prevent;
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: progress != 100
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : WebViewWidget(controller: webViewController),
    );
  }
}
