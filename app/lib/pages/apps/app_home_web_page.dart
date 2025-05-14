import 'dart:math';

import 'package:flutter/material.dart';
import 'package:omi/utils/browser.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/preferences.dart';

class AppHomeWebPage extends StatefulWidget {
  final App app;

  const AppHomeWebPage({
    Key? key,
    required this.app,
  }) : super(key: key);

  @override
  State<AppHomeWebPage> createState() => _AppHomeWebPageState();
}

class _AppHomeWebPageState extends State<AppHomeWebPage> with SingleTickerProviderStateMixin {
  late final WebViewController _controller;
  late final AnimationController _animationController;
  late final Animation<Offset> _slideAnimation;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 1.0),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOut,
    ));
    _animationController.forward();
    _controller = WebViewController()
      ..setUserAgent(topUserAgents[Random().nextInt(topUserAgents.length)])
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (String url) {
            if (mounted) {
              setState(() {
                _isLoading = false;
              });
            }
          },
          onWebResourceError: (WebResourceError error) {
            setState(() {
              _isLoading = false;
            });
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  'Failed to load page: ${error.description}',
                  style: const TextStyle(color: Colors.white),
                ),
                backgroundColor: Colors.red,
                duration: const Duration(seconds: 3),
                behavior: SnackBarBehavior.floating,
                margin: EdgeInsets.only(
                  bottom: MediaQuery.of(context).size.height - 100,
                  left: 20,
                  right: 20,
                ),
              ),
            );
          },
        ),
      )
      ..loadRequest(Uri.parse(
        '${widget.app.externalIntegration?.appHomeUrl ?? ''}?uid=${SharedPreferencesUtil().uid}',
      ));
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
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(16),
                      topRight: Radius.circular(16),
                    ),
                    child: WebViewWidget(controller: _controller),
                  ),
                ),
                if (_isLoading)
                  Container(
                    color: Colors.black,
                    child: const Center(
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
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
                      decoration: BoxDecoration(
                        color: Colors.black.withOpacity(0.7),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.max,
                        children: [
                          const Icon(
                            Icons.keyboard_double_arrow_down,
                            color: Colors.white,
                            size: 24,
                          ),
                          Text(
                            "${widget.app.name}'s App Details",
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          )),
    );
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }
}
