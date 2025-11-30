import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Facebook-style in-app browser as a modal bottom sheet
class InAppBrowser extends StatefulWidget {
  final String url;
  final String? title;

  const InAppBrowser({
    super.key,
    required this.url,
    this.title,
  });

  /// Opens the in-app browser as a modal bottom sheet
  static Future<void> open(BuildContext context, String url, {String? title}) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      useSafeArea: true,
      enableDrag: false, // Disable drag-to-dismiss so WebView can scroll
      builder: (context) => InAppBrowser(url: url, title: title),
    );
  }

  @override
  State<InAppBrowser> createState() => _InAppBrowserState();
}

class _InAppBrowserState extends State<InAppBrowser> {
  late WebViewController _controller;
  bool _isLoading = true;
  double _progress = 0;
  String _currentUrl = '';
  bool _canGoBack = false;
  bool _canGoForward = false;

  @override
  void initState() {
    super.initState();
    _currentUrl = widget.url;
    _initWebView();
  }

  void _initWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF0D0D0D))
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int progress) {
            if (mounted) {
              setState(() {
                _progress = progress / 100;
                _isLoading = progress < 100;
              });
            }
          },
          onPageStarted: (String url) {
            if (mounted) {
              setState(() {
                _currentUrl = url;
                _isLoading = true;
              });
            }
          },
          onPageFinished: (String url) async {
            if (mounted) {
              final canGoBack = await _controller.canGoBack();
              final canGoForward = await _controller.canGoForward();
              setState(() {
                _currentUrl = url;
                _isLoading = false;
                _canGoBack = canGoBack;
                _canGoForward = canGoForward;
              });
            }
          },
          onHttpError: (HttpResponseError error) {},
          onWebResourceError: (WebResourceError error) {},
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;

    return Container(
      height: screenHeight * 0.92,
      decoration: const BoxDecoration(
        color: Color(0xFF0D0D0D),
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 8),
            width: 36,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),

          // Header bar
          _buildHeaderBar(),

          // Progress indicator
          if (_isLoading)
            LinearProgressIndicator(
              value: _progress,
              backgroundColor: Colors.transparent,
              valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF8B5CF6)),
              minHeight: 2,
            )
          else
            const SizedBox(height: 2),

          // WebView
          Expanded(
            child: WebViewWidget(controller: _controller),
          ),
        ],
      ),
    );
  }

  Widget _buildHeaderBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // Navigation buttons
          _buildNavButton(
            icon: Icons.arrow_back_ios_rounded,
            enabled: _canGoBack,
            onTap: () => _controller.goBack(),
          ),
          _buildNavButton(
            icon: Icons.arrow_forward_ios_rounded,
            enabled: _canGoForward,
            onTap: () => _controller.goForward(),
          ),
          _buildNavButton(
            icon: Icons.refresh_rounded,
            enabled: true,
            onTap: () => _controller.reload(),
          ),

          const SizedBox(width: 8),

          // URL display
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.05),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Icon(
                    _currentUrl.startsWith('https')
                        ? Icons.lock_outline
                        : Icons.lock_open_outlined,
                    size: 14,
                    color: _currentUrl.startsWith('https')
                        ? const Color(0xFF10B981)
                        : Colors.white.withOpacity(0.5),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _getDisplayUrl(_currentUrl),
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.7),
                        fontSize: 13,
                      ),
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1,
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(width: 8),

          // Share button
          _buildNavButton(
            icon: Icons.share_outlined,
            enabled: true,
            onTap: () => Share.share(_currentUrl),
          ),

          // Close button
          _buildNavButton(
            icon: Icons.close_rounded,
            enabled: true,
            onTap: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  Widget _buildNavButton({
    required IconData icon,
    required bool enabled,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(
            icon,
            size: 20,
            color: enabled ? Colors.white.withOpacity(0.8) : Colors.white.withOpacity(0.3),
          ),
        ),
      ),
    );
  }

  String _getDisplayUrl(String url) {
    try {
      final uri = Uri.parse(url);
      return uri.host;
    } catch (e) {
      return url;
    }
  }
}
