import 'package:flutter/material.dart';
import 'package:omi/utils/browser.dart';
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

    // Launch the custom tab after animation completes
    var url = '${widget.app.externalIntegration?.appHomeUrl ?? ''}?uid=${SharedPreferencesUtil().uid}';
    _animationController.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        _openCustomTab(url);
      }
    });
  }

  void _openCustomTab(String url) async {
    setState(() {
      _isLoading = false;
    });

    try {
      await launchCustomTab(context, url);
      // Close this page after the custom tab is closed
      if (mounted) {
        _animationController.reverse().then((_) {
          Navigator.of(context).pop();
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Failed to load page: $e',
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
      }
    }
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
              // Loading indicator
              if (_isLoading)
                Container(
                  color: Colors.black,
                  child: const Center(
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  ),
                ),
              // Bottom bar
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
