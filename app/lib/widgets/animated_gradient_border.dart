import 'package:flutter/material.dart';
import 'package:gradient_borders/gradient_borders.dart';

class AnimatedGradientBorder extends StatefulWidget {
  final Widget child;
  final List<Color> gradientColors;
  final double borderWidth;
  final BorderRadius borderRadius;
  final Duration animationDuration;
  final double pulseIntensity;
  final bool isActive;
  final Color backgroundColor;

  const AnimatedGradientBorder({
    super.key,
    required this.child,
    required this.gradientColors,
    this.borderWidth = 1.0,
    this.borderRadius = const BorderRadius.all(Radius.circular(16)),
    this.animationDuration = const Duration(seconds: 2),
    this.pulseIntensity = 0.3,
    this.isActive = true,
    this.backgroundColor = Colors.transparent,
  });

  @override
  State<AnimatedGradientBorder> createState() => _AnimatedGradientBorderState();
}

class _AnimatedGradientBorderState extends State<AnimatedGradientBorder> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();

    _animationController = AnimationController(
      duration: widget.animationDuration,
      vsync: this,
    );

    _pulseAnimation = Tween<double>(
      begin: 1.0 - widget.pulseIntensity,
      end: 1.0 + widget.pulseIntensity,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));

    if (widget.isActive) {
      _animationController.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant AnimatedGradientBorder oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.animationDuration != widget.animationDuration) {
      _animationController.duration = widget.animationDuration;
    }

    if (oldWidget.pulseIntensity != widget.pulseIntensity) {
      _pulseAnimation = Tween<double>(
        begin: 1.0 - widget.pulseIntensity,
        end: 1.0 + widget.pulseIntensity,
      ).animate(CurvedAnimation(parent: _animationController, curve: Curves.easeInOut));
    }

    if (oldWidget.isActive != widget.isActive) {
      if (widget.isActive) {
        if (!_animationController.isAnimating) {
          _animationController.repeat(reverse: true);
        }
      } else {
        _animationController.stop();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        // Create animated gradient colors with opacity pulse
        final double factor = _animationController.isAnimating ? _pulseAnimation.value : 1.0;
        final animatedColors = widget.gradientColors.map((color) {
          final double nextOpacity = (color.opacity * factor).clamp(0.0, 1.0).toDouble();
          return color.withOpacity(nextOpacity);
        }).toList();

        return RepaintBoundary(
          child: Container(
            decoration: BoxDecoration(
              color: widget.backgroundColor,
              borderRadius: widget.borderRadius,
              border: GradientBoxBorder(
                gradient: LinearGradient(colors: animatedColors),
                width: widget.borderWidth,
              ),
              shape: BoxShape.rectangle,
            ),
            child: widget.child,
          ),
        );
      },
    );
  }
}
