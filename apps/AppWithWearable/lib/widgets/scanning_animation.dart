import 'package:flutter/material.dart';

class ScanningAnimation extends StatefulWidget {
  final double sizeMultiplier;

  const ScanningAnimation({super.key, this.sizeMultiplier = 1});

  @override
  State<ScanningAnimation> createState() => _ScanningAnimationState();
}

class _ScanningAnimationState extends State<ScanningAnimation> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 5),
    );

    _animation = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: Curves.fastLinearToSlowEaseIn,
      ),
    );
    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    double getGifSize(double screenHeight) {
      if (screenHeight <= 667) {
        return 200.0; // iPhone SE, iPhone 8 and earlier
      } else if (screenHeight <= 736) {
        return 250.0; // iPhone 8 Plus
      } else if (screenHeight <= 844) {
        return 300.0; // iPhone 12, iPhone 13
      } else if (screenHeight <= 896) {
        return 350.0; // iPhone XR, iPhone 11
      } else if (screenHeight <= 926) {
        return 400.0; // iPhone 12 Pro Max, iPhone 13 Pro Max
      } else {
        return 450.0; // iPhone 14 Pro Max and larger devices
      }
    }

    final gifSize = getGifSize(screenHeight) * widget.sizeMultiplier;

    return SizedBox(
      width: gifSize,
      height: gifSize,
      child: AnimatedBuilder(
        animation: _animation,
        builder: (context, child) {
          return Transform.scale(
            scale: _animation.value,
            child: Container(
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Color.fromARGB(0, 89, 255, 0),
              ),
              child: ClipOval(
                child: Image.asset(
                  'assets/images/sphere.gif',
                  fit: BoxFit.cover,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
