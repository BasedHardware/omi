import 'dart:math';
import 'package:flutter/material.dart';

class SyncAnimation extends StatefulWidget {
  final double size;
  final int dotsPerRing;
  final bool isAnimating;
  final VoidCallback onStart;
  final VoidCallback onStop;

  const SyncAnimation({
    super.key,
    this.size = 200,
    this.dotsPerRing = 12,
    required this.isAnimating,
    required this.onStart,
    required this.onStop,
  });

  @override
  _SyncAnimationState createState() => _SyncAnimationState();
}

class _SyncAnimationState extends State<SyncAnimation> with TickerProviderStateMixin {
  late List<AnimationController> _controllers;
  late AnimationController _fadeInController;
  late AnimationController _fadeOutController;
  late Animation<double> _fadeInAnimation;
  late Animation<double> _fadeOutAnimation;
  final int _numRings = 4;

  @override
  void initState() {
    super.initState();

    _controllers = List.generate(_numRings, (index) {
      return AnimationController(
        vsync: this,
        duration: Duration(seconds: 2 + index),
      );
    });

    _fadeInController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );

    _fadeOutController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );

    _fadeInAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeInController, curve: Curves.easeIn),
    );

    _fadeOutAnimation = Tween<double>(begin: 1.0, end: 0.0).animate(
      CurvedAnimation(parent: _fadeOutController, curve: Curves.easeOut),
    );
  }

  void _startAnimation() {
    for (var controller in _controllers) {
      controller.repeat();
    }
    _fadeInController.reset();
    _fadeInController.forward();
  }

  void _stopAnimation() {
    for (var controller in _controllers) {
      controller.stop();
    }
    _fadeOutController.reset();
    _fadeOutController.forward();
  }

  @override
  void didUpdateWidget(SyncAnimation oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isAnimating && !oldWidget.isAnimating) {
      _startAnimation();
      widget.onStart();
    } else if (!widget.isAnimating && oldWidget.isAnimating) {
      _stopAnimation();
      widget.onStop();
    }
  }

  @override
  void dispose() {
    for (var controller in _controllers) {
      controller.dispose();
    }
    _fadeInController.dispose();
    _fadeOutController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Image.asset(
            'assets/images/herologo.png',
            width: widget.size * 0.75,
            height: widget.size * 0.75,
          ),
          if (widget.isAnimating)
            for (int ring = 0; ring < _numRings; ring++) ..._buildRing(ring),
        ],
      ),
    );
  }

  List<Widget> _buildRing(int ringIndex) {
    final int dotsInThisRing = widget.dotsPerRing + ringIndex * 2;
    final double ringRadius = widget.size * (0.45 + ringIndex * 0.1);

    return List.generate(dotsInThisRing, (index) {
      return AnimatedBuilder(
        animation: _controllers[ringIndex],
        builder: (_, child) {
          final double angle =
              2 * pi * _controllers[ringIndex].value + (index * 2 * pi / dotsInThisRing) + (ringIndex * pi / _numRings);

          return Transform(
            transform: Matrix4.identity()
              ..translate(
                ringRadius * cos(angle),
                ringRadius * sin(angle),
                0.0,
              ),
            child: Opacity(
              opacity: widget.isAnimating ? _fadeInAnimation.value : _fadeOutAnimation.value,
              child: Container(
                width: (ringIndex == 0 ? widget.size * 0.055 : widget.size * 0.07) / (ringIndex + 1),
                height: (ringIndex == 0 ? widget.size * 0.055 : widget.size * 0.07) / (ringIndex + 1),
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white,
                ),
              ),
            ),
          );
        },
      );
    });
  }
}
