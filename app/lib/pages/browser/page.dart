import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';

/// Validates and sanitizes URLs for WebView navigation
/// Handles various URL formats and ensures proper structure
class UrlValidator {
  /// Validates if the given URL is properly formatted and uses http/https protocol
  /// Returns false for null, empty, or malformed URLs
  static bool isValidUrl(String? url) {
    if (url == null || url.trim().isEmpty) {
      return false;
    }
    try {
      final uri = Uri.parse(url);
      return uri.hasScheme && (uri.scheme == 'http' || uri.scheme == 'https');
    } catch (_) {
      return false;
    }
  }

  /// Checks if URL contains a protocol specification (e.g., http://, https://)
  static bool hasProtocol(String? url) => url?.contains('://') ?? false;

  /// Checks if URL is protocol-relative (starts with //)
  static bool isProtocolRelative(String? url) => url?.startsWith('//') ?? false;

  /// Checks if URL string is null, empty, or only whitespace
  static bool isEmpty(String? url) => url?.trim().isEmpty ?? true;

  /// Safely extracts hostname from URL string
  /// Returns null if URL is invalid
  static String? getHostname(String? url) {
    if (isEmpty(url)) return null;
    try {
      final uri = Uri.parse(url!);
      return uri.host;
    } catch (_) {
      return null;
    }
  }
}

/// A WebView page that handles external authentication URLs
/// Automatically adds uid parameter and handles various error cases
class BrowserPage extends StatefulWidget {
  /// The initial URL to load in the WebView
  /// Can be null, protocol-relative, or without protocol (will default to https)
  final String? initialUrl;
  
  const BrowserPage({super.key, this.initialUrl});

  @override
  State<BrowserPage> createState() => _BrowserPageState();
}

class _BrowserPageState extends State<BrowserPage> with WidgetsBindingObserver {
  WebViewController? controller;
  bool isLoading = true;
  int _pageStartTime = 0;
  bool _disposed = false;

  String? _sanitizeUrl(String? input) {
    // Handle null or empty input
    if (input == null || input.trim().isEmpty) {
      return null;
    }

    String rawUrl = input.trim();

    // Handle protocol-relative URLs
    if (UrlValidator.isProtocolRelative(rawUrl)) {
      rawUrl = 'https:$rawUrl';
    }
    // Add https:// to URLs without protocol if needed
    else if (!UrlValidator.hasProtocol(rawUrl)) {
      rawUrl = 'https://$rawUrl';
    }
    // Block URLs with other protocols
    else if (!rawUrl.startsWith('http://') && !rawUrl.startsWith('https://')) {
      return null;
    }

    // Validate final URL
    if (!UrlValidator.isValidUrl(rawUrl)) {
      return null;
    }

    // Add uid parameter
    try {
      final uri = Uri.parse(rawUrl);
      final uid = SharedPreferencesUtil().uid;
      
      // Create new parameters map with existing params
      final params = Map<String, String>.from(uri.queryParameters);
      params['uid'] = uid;

      // Rebuild URL with uid parameter
      final finalUri = uri.replace(queryParameters: params);
      return finalUri.toString();
    } catch (e) {
      debugPrint('Error parsing URL: $e');
      return null;
    }
  }

  void _showErrorAndNavigateBack() {
    if (!_disposed && mounted && context.mounted) {
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Website is not reachable'),
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
          backgroundColor: Colors.red[700],
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  void _handlePageStarted(String pageUrl) {
    _pageStartTime = DateTime.now().millisecondsSinceEpoch;
    if (!_disposed && mounted) {
      setState(() => isLoading = true);
    }
    
    MixpanelManager().track('WebView_PageStarted', properties: {
      'url': pageUrl,
      'initial_url': widget.initialUrl,
      'hostname': UrlValidator.getHostname(pageUrl),
    });
  }

  void _handlePageFinished(String pageUrl) {
    final loadTime = DateTime.now().millisecondsSinceEpoch - _pageStartTime;
    if (!_disposed && mounted) {
      setState(() => isLoading = false);
    }
    
    MixpanelManager().track('WebView_PageLoaded', properties: {
      'url': pageUrl,
      'initial_url': widget.initialUrl,
      'hostname': UrlValidator.getHostname(pageUrl),
      'load_time_ms': loadTime,
    });
  }

  void _handleWebResourceError(WebResourceError error) {
    final errorDetails = {
      'url': widget.initialUrl,
      'error_code': error.errorCode,
      'error_description': error.description,
      'error_type': error.errorType.toString(),
      'is_main_frame': error.isForMainFrame,
      'raw_error': error.toString(),
    };
    
    debugPrint('WebView error: ${errorDetails.toString()}');
    MixpanelManager().track('WebView_Error', properties: errorDetails);
    
    // Handle main frame errors
    if (error.isForMainFrame ?? false) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _showErrorAndNavigateBack();
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_disposed) return;

    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        // Clear WebView resources when app goes to background
        controller?.clearCache();
        break;
      case AppLifecycleState.resumed:
        // Reload page if needed when coming back to foreground
        if (mounted && controller != null) {
          controller!.reload();
        }
        break;
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    
    final sanitizedUrl = _sanitizeUrl(widget.initialUrl);
    debugPrint('Loading URL in BrowserPage: $sanitizedUrl');
    
    if (sanitizedUrl == null) {
      // No valid URL provided, go back to app details
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_disposed && mounted && context.mounted) {
          Navigator.of(context).pop();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('No valid URL provided'),
              behavior: SnackBarBehavior.floating,
              margin: const EdgeInsets.all(16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
              backgroundColor: Colors.red[700],
              duration: const Duration(seconds: 3),
            ),
          );
        }
      });
      return;
    }
    
    controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.grey[900]!)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: _handlePageStarted,
          onPageFinished: _handlePageFinished,
          onWebResourceError: _handleWebResourceError,
          onNavigationRequest: (NavigationRequest request) {
            // Block navigation after error to prevent showing error page
            if (request.url.contains('chrome-error://')) {
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(sanitizedUrl));
  }

  @override
  void dispose() {
    _disposed = true;
    WidgetsBinding.instance.removeObserver(this);
    controller?.clearCache();
    super.dispose();
  }

  Widget _buildLoadingWidget() {
    return Container(
      color: Colors.grey[900],
      child: const Center(
        child: CircularProgressIndicator(),
      ),
    );
  }

  Widget _buildWebView() {
    if (controller == null) {
      return const SizedBox.shrink();
    }
    return WebViewWidget(controller: controller!);
  }

  List<Widget> _buildStackChildren() {
    return [
      _buildWebView(),
      if (isLoading && controller != null) _buildLoadingWidget(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    if (controller == null) {
      return const SizedBox.shrink();
    }

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Stack(
        children: _buildStackChildren(),
      ),
    );
  }
}