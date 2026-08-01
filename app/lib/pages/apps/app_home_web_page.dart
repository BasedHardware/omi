import 'dart:math';

import 'package:flutter/material.dart';

import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/utils/browser.dart';

class AppHomeWebPage extends StatefulWidget {
  final App app;

  const AppHomeWebPage({Key? key, required this.app}) : super(key: key);

  @override
  State<AppHomeWebPage> createState() => _AppHomeWebPageState();
}

class _AppHomeWebPageState extends State<AppHomeWebPage> with SingleTickerProviderStateMixin {
  late final WebViewController _controller;
  late final AnimationController _animationController;
  late final Animation<Offset> _slideAnimation;
  static const int _maxRedirectHops = 5;

  bool _isLoading = true;
  final List<Uri> _allowedOrigins = [];
  int _redirectHopsRemaining = _maxRedirectHops;

  bool _isAllowedNavigation(String url) {
    final target = Uri.tryParse(url);
    if (target == null) return false;
    return _allowedOrigins
        .any((origin) => target.scheme == origin.scheme && target.host == origin.host && target.port == origin.port);
  }

  void _allowOrigin(String url) {
    final target = Uri.tryParse(url);
    if (target == null || target.host.isEmpty) return;
    if (_isAllowedNavigation(url)) return;
    _allowedOrigins.add(target);
  }

  void _onNavigationBlocked(String url) {
    if (!mounted) return;
    setState(() {
      _isLoading = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _showError('Blocked navigation to an unrelated site: $url');
    });
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: const TextStyle(color: Colors.white)),
        backgroundColor: Colors.red,
        duration: const Duration(seconds: 3),
        behavior: SnackBarBehavior.floating,
        margin: EdgeInsets.only(bottom: MediaQuery.of(context).size.height - 100, left: 20, right: 20),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 1.0),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _animationController, curve: Curves.easeOut));
    _animationController.forward();
    final initialUrl = '${widget.app.externalIntegration?.appHomeUrl ?? ''}?uid=${SharedPreferencesUtil().uid}';
    _allowOrigin(initialUrl);
    _controller = WebViewController()
      ..setUserAgent(topUserAgents[Random().nextInt(topUserAgents.length)])
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (NavigationRequest request) {
            if (_isAllowedNavigation(request.url)) {
              return NavigationDecision.navigate;
            }
            // A page load in flight means this is a redirect hop off the
            // original host: follow a bounded chain and adopt the landing
            // origin instead of stranding the spinner.
            final target = Uri.tryParse(request.url);
            final isWebScheme = target != null && (target.scheme == 'http' || target.scheme == 'https');
            if (isWebScheme && _isLoading && _redirectHopsRemaining > 0) {
              _redirectHopsRemaining--;
              _allowOrigin(request.url);
              return NavigationDecision.navigate;
            }
            _onNavigationBlocked(request.url);
            return NavigationDecision.prevent;
          },
          onPageStarted: (String url) {
            _allowOrigin(url);
            if (mounted) {
              setState(() {
                _isLoading = true;
              });
            }
          },
          onPageFinished: (String url) {
            _allowOrigin(url);
            _redirectHopsRemaining = _maxRedirectHops;
            if (mounted) {
              setState(() {
                _isLoading = false;
              });
            }
          },
          onWebResourceError: (WebResourceError error) {
            if (!mounted) return;
            setState(() {
              _isLoading = false;
            });
            _showError('Failed to load page: ${error.description}');
          },
        ),
      )
      ..loadRequest(Uri.parse(initialUrl));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SlideTransition(
        position: _slideAnimation,
        child: SafeArea(
          child: Stack(
            children: [
              // Main content with top padding and rounded corners
              Padding(
                padding: const EdgeInsets.only(top: 16, bottom: 48),
                child: ClipRRect(
                  borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
                  child: WebViewWidget(controller: _controller),
                ),
              ),
              if (_isLoading)
                Container(
                  color: Colors.black,
                  child: const Center(
                    child: CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(Colors.white)),
                  ),
                ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: GestureDetector(
                  onTap: () {
                    _animationController.reverse().then((_) {
                      Navigator.of(context).pop();
                    });
                  },
                  child: Container(
                    height: 48,
                    alignment: Alignment.center,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.7)),
                    child: Column(
                      mainAxisSize: MainAxisSize.max,
                      children: [
                        const Icon(Icons.keyboard_double_arrow_down, color: Colors.white, size: 24),
                        Text(
                          "${widget.app.name}'s App Details",
                          style: const TextStyle(color: Colors.white, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }
}
