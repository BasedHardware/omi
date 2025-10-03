import 'dart:async';
import 'package:flutter/material.dart';

enum NotificationType {
  success,
  error,
  info,
}

class TopNotificationBanner extends StatefulWidget {
  final String message;
  final bool isVisible;
  final NotificationType type;
  final VoidCallback? onDismiss;
  final Duration duration;

  const TopNotificationBanner({
    super.key,
    required this.message,
    required this.isVisible,
    this.type = NotificationType.success,
    this.onDismiss,
    this.duration = const Duration(seconds: 3),
  });

  @override
  State<TopNotificationBanner> createState() => _TopNotificationBannerState();
}

class _TopNotificationBannerState extends State<TopNotificationBanner> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _slideAnimation;
  Timer? _autoHideTimer;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _slideAnimation = Tween<double>(
      begin: -1.0,
      end: 0.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOut,
    ));

    if (widget.isVisible) {
      _showBanner();
    }
  }

  @override
  void didUpdateWidget(TopNotificationBanner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isVisible != oldWidget.isVisible) {
      if (widget.isVisible) {
        _showBanner();
      } else {
        _hideBanner();
      }
    }
  }

  void _showBanner() {
    _animationController.forward();
    _autoHideTimer?.cancel();
    _autoHideTimer = Timer(widget.duration, () {
      if (mounted) {
        _hideBanner();
      }
    });
  }

  void _hideBanner() {
    _animationController.reverse().then((_) {
      if (widget.onDismiss != null) {
        widget.onDismiss!();
      }
    });
  }

  @override
  void dispose() {
    _autoHideTimer?.cancel();
    _animationController.dispose();
    super.dispose();
  }

  Color _getBackgroundColor() {
    switch (widget.type) {
      case NotificationType.success:
        return Colors.green; // Match exact color from "syncing messages" design
      case NotificationType.error:
        return Colors.red.shade700;
      case NotificationType.info:
        return Colors.blue.shade700;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isVisible) {
      return const SizedBox(height: 0, width: double.infinity);
    }

    return AnimatedBuilder(
      animation: _slideAnimation,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(0, _slideAnimation.value * 32),
          child: Container(
            width: double.infinity,
            height: 32, // Match exact height from existing "syncing messages" design
            color: _getBackgroundColor(), // Remove shadows to match existing simple design
            child: Center(
              child: Text(
                widget.message,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12, // Match exact font size from existing design
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
