import 'package:flutter/material.dart';
import 'package:gradient_borders/gradient_borders.dart';

class AnimatedGradientBorder extends StatefulWidget {
  final Widget child;
  final List<Color> gradientColors;
  final double borderWidth;
  final BorderRadius borderRadius;
  final Duration animationDuration;
  final double pulseIntensity;

  const AnimatedGradientBorder({
    super.key,
    required this.child,
    required this.gradientColors,
    this.borderWidth = 1.0,
    this.borderRadius = const BorderRadius.all(Radius.circular(16)),
    this.animationDuration = const Duration(seconds: 2),
    this.pulseIntensity = 0.3,
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

    // Start the infinite pulse animation
    _animationController.repeat(reverse: true);
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        // Create animated gradient colors with opacity pulse
        final animatedColors = widget.gradientColors.map((color) {
          return color.withOpacity(color.opacity * _pulseAnimation.value);
        }).toList();

        return Container(
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: widget.borderRadius,
            border: GradientBoxBorder(
              gradient: LinearGradient(colors: animatedColors),
              width: widget.borderWidth,
            ),
            shape: BoxShape.rectangle,
          ),
          child: widget.child,
        );
      },
    );
  }
}
