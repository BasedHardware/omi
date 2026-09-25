import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/env/env.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
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
  bool _hasError = false;

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
            if (progress == 100 && mounted) {
              setState(() {
                _isLoading = false;
              });
            }
          },
          onPageStarted: (String url) {
            if (!mounted) return;
            setState(() {
              _isLoading = true;
            });
          },
          onWebResourceError: (WebResourceError error) {
            // Sub-resource failures (an analytics pixel, a font) do not break checkout; only a
            // failed page load leaves the reader looking at a blank or broken page.
            if (error.isForMainFrame == false) return;
            Logger.debug('Payment page failed to load: ${error.errorCode} ${error.description}');
            if (!mounted) return;
            setState(() {
              _hasError = true;
              _isLoading = false;
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

  Future<void> _retry() async {
    setState(() {
      _hasError = false;
      _isLoading = true;
    });
    final current = await _controller.currentUrl();
    if (current == null || current.isEmpty || current == 'about:blank') {
      await _controller.loadRequest(Uri.parse(widget.checkoutUrl));
    } else {
      await _controller.reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    // Pop on build if the server-driven visibility flag is off, in case any
    // caller reached here through a stale route.
    if (!context.watch<UsageProvider>().showSubscriptionUI) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (Navigator.of(context).canPop()) Navigator.of(context).pop(false);
      });
      return const SizedBox.shrink();
    }

    return Scaffold(
      appBar: AppBar(
        // A pushed page: back, not close. It reports "not completed" like the cancel URL does.
        leading: OmiBackButton(onPressed: () => Navigator.of(context).pop(false)),
        title: Text(widget.title ?? context.l10n.completeYourUpgrade),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_hasError)
            Positioned.fill(
              child: ColoredBox(
                color: OmiColors.surface0,
                child: OmiErrorState(message: context.l10n.couldNotLoadCheckout, onRetry: _retry),
              ),
            )
          else if (_isLoading)
            const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
        ],
      ),
    );
  }
}
