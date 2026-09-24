import 'package:flutter/material.dart';

import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A pushed page that shows one web page in the app (referral program, an app's home page).
///
/// * Leading back goes back within the page's own history first, then leaves — the same as
///   Android system back. (While there is web history the iOS edge swipe is held so it cannot
///   skip past it.)
/// * First load shows a spinner; a failed main-frame load shows the reason and **Try Again**.
class OmiWebPage extends StatefulWidget {
  const OmiWebPage({super.key, required this.title, required this.url, this.userAgent});

  final String title;
  final Uri url;

  /// Overrides the web view's user agent (some app home pages sniff it).
  final String? userAgent;

  @override
  State<OmiWebPage> createState() => _OmiWebPageState();
}

class _OmiWebPageState extends State<OmiWebPage> {
  late final WebViewController _controller;
  // Covers the page only until it first appears; later navigations happen in place.
  bool _loading = true;
  bool _failed = false;
  bool _canGoBack = false;
  // The page the reader was going to; Try Again reloads it, not the first URL.
  Uri? _lastRequested;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()..setJavaScriptMode(JavaScriptMode.unrestricted);
    if (widget.userAgent != null) _controller.setUserAgent(widget.userAgent);
    _controller
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (url) => _lastRequested = Uri.tryParse(url),
          onPageFinished: (_) async {
            final canGoBack = await _controller.canGoBack();
            if (!mounted) return;
            setState(() {
              _loading = false;
              _canGoBack = canGoBack;
            });
          },
          onWebResourceError: (error) {
            // A failed image or script is the page's business; only a failed page is ours.
            if (error.isForMainFrame == false) return;
            if (!mounted) return;
            setState(() {
              _loading = false;
              _failed = true;
            });
          },
        ),
      )
      ..loadRequest(widget.url);
  }

  Future<void> _retry() async {
    setState(() {
      _failed = false;
      _loading = true;
    });
    await _controller.loadRequest(_lastRequested ?? widget.url);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_canGoBack || _failed,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        await _controller.goBack();
        final canGoBack = await _controller.canGoBack();
        if (mounted) setState(() => _canGoBack = canGoBack);
      },
      child: Scaffold(
        appBar: AppBar(
          leading: const OmiBackButton(),
          title: Text(widget.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
        body: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_failed)
              ColoredBox(
                color: OmiColors.surface0,
                child: OmiErrorState(message: context.l10n.couldNotLoadPage, onRetry: _retry),
              )
            else if (_loading)
              const ColoredBox(color: OmiColors.surface0, child: OmiLoadingState()),
          ],
        ),
      ),
    );
  }
}
