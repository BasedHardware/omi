import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:math' as math;

class CustomRefreshIndicator extends StatefulWidget {
  final Widget child;
  final Future<void> Function() onRefresh;
  final double triggerDistance;
  final double minDragStartThreshold;

  const CustomRefreshIndicator({
    Key? key,
    required this.child,
    required this.onRefresh,
    this.triggerDistance = 120.0,
    this.minDragStartThreshold = 60.0,
  }) : super(key: key);

  @override
  State<CustomRefreshIndicator> createState() => _CustomRefreshIndicatorState();
}

class _CustomRefreshIndicatorState extends State<CustomRefreshIndicator> with TickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  double _dragOffset = 0.0;
  double _totalDragDistance = 0.0;
  bool _isRefreshing = false;
  bool _canRefresh = false;
  int _previousFilledDots = 0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );
    _animation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.linear),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _handleScrollNotification(ScrollNotification notification) {
    if (_isRefreshing) return;

    if (notification is ScrollUpdateNotification) {
      final ScrollMetrics metrics = notification.metrics;

      // Check if we're at the top and pulling down
      if (metrics.pixels <= 0 && notification.scrollDelta! < 0) {
        setState(() {
          _totalDragDistance = math.min(widget.triggerDistance + widget.minDragStartThreshold, _totalDragDistance + (-notification.scrollDelta!));

          // Only show visual feedback after minimum threshold is exceeded
          if (_totalDragDistance > widget.minDragStartThreshold) {
            _dragOffset = _totalDragDistance - widget.minDragStartThreshold;
            _canRefresh = _dragOffset >= widget.triggerDistance;
          } else {
            _dragOffset = 0.0;
            _canRefresh = false;
          }
        });

        if (_dragOffset > 0) {
          _checkForHapticFeedback();
        }
      } else if (metrics.pixels > 0 && (_dragOffset > 0 || _totalDragDistance > 0)) {
        // Reset if user scrolls back up
        _resetDrag();
      }
    } else if (notification is ScrollEndNotification) {
      if (_canRefresh && !_isRefreshing) {
        _triggerRefresh();
      } else if (!_isRefreshing) {
        _resetDrag();
      }
    }
  }

  void _checkForHapticFeedback() {
    final progress = _dragOffset / widget.triggerDistance;
    final currentFilledDots = (progress * 8).round().clamp(0, 8);

    if (currentFilledDots > _previousFilledDots) {
      // Stronger haptic feedback when all dots are filled
      if (currentFilledDots == 8) {
        HapticFeedback.mediumImpact();
      } else {
        HapticFeedback.lightImpact();
      }
      _previousFilledDots = currentFilledDots;
    } else if (currentFilledDots < _previousFilledDots) {
      _previousFilledDots = currentFilledDots;
    }
  }

  void _triggerRefresh() async {
    setState(() {
      _isRefreshing = true;
    });

    // Haptic feedback when refresh is triggered
    HapticFeedback.heavyImpact();

    // Start continuous spinning animation
    _controller.repeat();

    try {
      await widget.onRefresh();
    } finally {
      if (mounted) {
        _controller.stop();
        _controller.reset();
        _resetDrag();
      }
    }
  }

  void _resetDrag() {
    setState(() {
      _dragOffset = 0.0;
      _totalDragDistance = 0.0;
      _canRefresh = false;
      _isRefreshing = false;
      _previousFilledDots = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    return NotificationListener<ScrollNotification>(
      onNotification: (ScrollNotification notification) {
        _handleScrollNotification(notification);
        return false;
      },
      child: Stack(
        children: [
          widget.child,
          if (_dragOffset > 0)
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                height: _dragOffset,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.black.withOpacity(0.3),
                      Colors.transparent,
                    ],
                  ),
                ),
                child: CustomPaint(
                  size: const Size(60, 60),
                  painter: CircularDotsIndicator(
                    progress: _dragOffset / widget.triggerDistance,
                    isRefreshing: _isRefreshing,
                    animation: _animation,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class CircularDotsIndicator extends CustomPainter {
  final double progress;
  final bool isRefreshing;
  final Animation<double> animation;

  CircularDotsIndicator({
    required this.progress,
    required this.isRefreshing,
    required this.animation,
  }) : super(repaint: animation);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 12;
    final dotRadius = 3.0;

    // Calculate how many dots should be filled
    final totalDots = 8;
    final filledDots = isRefreshing ? totalDots : (progress * totalDots).round().clamp(0, totalDots);

    // Add rotation when refreshing
    if (isRefreshing) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(animation.value * 2 * math.pi);
      canvas.translate(-center.dx, -center.dy);
    }

    for (int i = 0; i < totalDots; i++) {
      final angle = (i * 2 * math.pi / totalDots) - math.pi / 2;
      final dotCenter = Offset(
        center.dx + radius * math.cos(angle),
        center.dy + radius * math.sin(angle),
      );

      final isFilled = i < filledDots;

      // Enhanced animation when refreshing
      if (isRefreshing) {
        // Create a wave effect with varying opacity and size
        final wavePhase = (animation.value * 2 * math.pi) + (i * math.pi / 4);
        final opacity = 0.4 + (0.6 * (math.sin(wavePhase) + 1) / 2);
        final sizeFactor = 0.8 + (0.4 * (math.cos(wavePhase) + 1) / 2);

        final paint = Paint()
          ..style = PaintingStyle.fill
          ..color = Colors.white.withOpacity(opacity);

        // Add enhanced shadow for spinning dots
        final shadowPaint = Paint()
          ..style = PaintingStyle.fill
          ..color = Colors.white.withOpacity(opacity * 0.3)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3.0);
        canvas.drawCircle(dotCenter, (dotRadius + 1) * sizeFactor, shadowPaint);

        canvas.drawCircle(dotCenter, dotRadius * sizeFactor, paint);
      } else {
        // Static dots during pull-down
        final paint = Paint()
          ..style = PaintingStyle.fill
          ..color = isFilled ? Colors.white : Colors.white.withOpacity(0.3);

        // Add shadow for filled dots
        if (isFilled) {
          final shadowPaint = Paint()
            ..style = PaintingStyle.fill
            ..color = Colors.white.withOpacity(0.3)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.0);
          canvas.drawCircle(dotCenter, dotRadius + 1, shadowPaint);
        }

        canvas.drawCircle(dotCenter, dotRadius, paint);
      }
    }

    if (isRefreshing) {
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
