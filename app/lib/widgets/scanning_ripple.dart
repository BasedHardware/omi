import 'package:flutter/material.dart';

class ScanningRippleWidget extends StatefulWidget {
  final bool isScanning;
  final double size;

  const ScanningRippleWidget({
    super.key,
    required this.isScanning,
    this.size = 300,
  });

  @override
  State<ScanningRippleWidget> createState() => _ScanningRippleWidgetState();
}

class _ScanningRippleWidgetState extends State<ScanningRippleWidget> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 2500),
      vsync: this,
    );
    if (widget.isScanning) _controller.repeat();
  }

  @override
  void didUpdateWidget(ScanningRippleWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isScanning && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!widget.isScanning && _controller.isAnimating) {
      _controller.stop();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return CustomPaint(
            size: Size(widget.size, widget.size),
            painter: _RipplePainter(
              progress: _controller.value,
              color: Colors.white,
            ),
          );
        },
      ),
    );
  }
}

class _RipplePainter extends CustomPainter {
  final double progress;
  final Color color;
  static const int _rippleCount = 3;

  _RipplePainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width / 2;

    for (int i = 0; i < _rippleCount; i++) {
      final rippleProgress = (progress + i / _rippleCount) % 1.0;
      final radius = maxRadius * rippleProgress;
      final opacity = (1.0 - rippleProgress) * 0.6;
      final paint = Paint()
        ..color = color.withValues(alpha: opacity.clamp(0.0, 1.0))
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5 + (1.0 - rippleProgress) * 1.5;
      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(_RipplePainter oldDelegate) => oldDelegate.progress != progress;
}
