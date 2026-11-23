import 'package:flutter/material.dart';

import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What a [WebNavigationPolicy] decides for one main-frame navigation.
enum WebNavigationKind { allow, block, replace, finish }

class WebNavigation {
  const WebNavigation._(this.kind, [this.replacement]);

  static const allow = WebNavigation._(WebNavigationKind.allow);

  /// Stay on the current page and tell the reader the page is not available in the app.
  static const block = WebNavigation._(WebNavigationKind.block);

  /// Close the page; it pops with [WebNavigationKind.finish] so the caller can say why.
  static const finish = WebNavigation._(WebNavigationKind.finish);

  /// Load [uri] instead of the requested page.
  const WebNavigation.replace(Uri uri) : this._(WebNavigationKind.replace, uri);

  final WebNavigationKind kind;
  final Uri? replacement;

  @override
  bool operator ==(Object other) => other is WebNavigation && other.kind == kind && other.replacement == replacement;

  @override
  int get hashCode => Object.hash(kind, replacement);

  @override
  String toString() => 'WebNavigation.${kind.name}${replacement == null ? '' : '($replacement)'}';
}

/// Decides a main-frame navigation from the page the reader is on ([current], null before the first
/// page) to [target].
typedef WebNavigationPolicy = WebNavigation Function(Uri? current, Uri target);

/// A check a loaded main-frame page must pass before it is shown: [script] runs in the page and
/// [passes] reads its result. Until it passes the page stays behind the loading state; if it fails
/// the reader sees "not available" with Close.
class WebPageCheck {
  const WebPageCheck({required this.appliesTo, required this.script, required this.passes});

  final bool Function(Uri page) appliesTo;
  final String script;
  final bool Function(Object? result) passes;
}

/// A pushed page that shows one web page in the app (referral program, an app's home page).
///
/// * Leading back goes back within the page's own history first, then leaves — the same as
///   Android system back. (While there is web history the iOS edge swipe is held so it cannot
///   skip past it.)
/// * First load shows a spinner; a failed main-frame load shows the reason and **Try Again**.
class OmiWebPage extends StatefulWidget {
  const OmiWebPage({
    super.key,
    required this.title,
    required this.url,
    this.userAgent,
    this.showClose = false,
    this.navigationPolicy,
    this.pageCheck,
  });

  final String title;
  final Uri url;

  /// Overrides the web view's user agent (some app home pages sniff it).
  final String? userAgent;

  /// A Close (×) that dismisses the whole page, for a page presented as a sheet (the Omi store).
  /// The default back button steps back through the web history first.
  final bool showClose;

  /// When set, decides every main-frame navigation (allow, block with a message, replace, or close).
  final WebNavigationPolicy? navigationPolicy;

  /// When set, a matching page is shown only after its check passes.
  final WebPageCheck? pageCheck;

  @override
  State<OmiWebPage> createState() => _OmiWebPageState();
}

class _OmiWebPageState extends State<OmiWebPage> {
  late final WebViewController _controller;
  // Covers the page only until it first appears; later navigations happen in place.
  bool _loading = true;
  bool _failed = false;
  bool _canGoBack = false;
  // A page that failed [OmiWebPage.pageCheck]: never shown.
  bool _unavailable = false;
  // The main-frame page the reader is on, for the navigation policy.
  Uri? _current;
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
          onNavigationRequest: (request) {
            final policy = widget.navigationPolicy;
            if (policy == null || !request.isMainFrame) return NavigationDecision.navigate;
            final uri = Uri.tryParse(request.url);
            final decision = uri == null ? WebNavigation.block : policy(_current, uri);
            switch (decision.kind) {
              case WebNavigationKind.allow:
                return NavigationDecision.navigate;
              case WebNavigationKind.replace:
                _controller.loadRequest(decision.replacement!);
                return NavigationDecision.prevent;
              case WebNavigationKind.finish:
                if (mounted) Navigator.of(context).pop(WebNavigationKind.finish);
                return NavigationDecision.prevent;
              case WebNavigationKind.block:
                if (mounted) {
                  ScaffoldMessenger.of(context)
                    ..hideCurrentSnackBar()
                    ..showSnackBar(SnackBar(content: Text(context.l10n.pageNotAvailableInApp)));
                }
                return NavigationDecision.prevent;
            }
          },
          onPageStarted: (url) {
            final uri = Uri.tryParse(url);
            _lastRequested = uri;
            _current = uri;
            // A checked page stays covered until its check passes, so it never flashes.
            if (uri != null && (widget.pageCheck?.appliesTo(uri) ?? false) && mounted) {
              setState(() => _loading = true);
            }
          },
          onUrlChange: (change) {
            final uri = change.url == null ? null : Uri.tryParse(change.url!);
            if (uri != null) _current = uri;
          },
          onPageFinished: (url) async {
            final uri = Uri.tryParse(url);
            final check = widget.pageCheck;
            if (check != null && uri != null && check.appliesTo(uri)) {
              Object? result;
              try {
                result = await _controller.runJavaScriptReturningResult(check.script);
              } catch (_) {
                result = null; // A page the check cannot read is not shown.
              }
              if (!mounted) return;
              if (!check.passes(result)) {
                setState(() {
                  _loading = false;
                  _unavailable = true;
                });
                return;
              }
            }
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
      // A sheet closes as a whole; a pushed page walks back through its web history first.
      canPop: widget.showClose || !_canGoBack || _failed || _unavailable,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        await _controller.goBack();
        final canGoBack = await _controller.canGoBack();
        if (mounted) setState(() => _canGoBack = canGoBack);
      },
      child: Scaffold(
        appBar: AppBar(
          leading: widget.showClose
              ? OmiIconButton(
                  key: const Key('omi_web_page_close'),
                  icon: const Icon(Icons.close),
                  label: context.l10n.close,
                  onPressed: () => Navigator.of(context).pop(),
                )
              : const OmiBackButton(),
          title: Text(widget.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
        body: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_unavailable)
              ColoredBox(
                key: const Key('omi_web_page_unavailable'),
                color: OmiColors.surface0,
                child: OmiErrorState(
                  message: context.l10n.pageNotAvailableInApp,
                  retryLabel: context.l10n.close,
                  onRetry: () => Navigator.of(context).pop(),
                ),
              )
            else if (_failed)
              ColoredBox(
                color: OmiColors.surface0,
                child: OmiErrorState(message: context.l10n.couldNotLoadPage, onRetry: _retry),
              )
            else if (_loading)
              ColoredBox(color: OmiColors.surface0, child: const OmiLoadingState()),
          ],
        ),
      ),
    );
  }
}
