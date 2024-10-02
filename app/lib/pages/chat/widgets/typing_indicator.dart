import 'package:flutter/material.dart';

class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  _TypingIndicatorState createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<Offset> _animation1;
  late Animation<Offset> _animation2;
  late Animation<Offset> _animation3;
  late Animation<Color?> _colorAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    _animation1 = Tween<Offset>(
      begin: const Offset(0, 0.2),
      end: const Offset(0, -0.2),
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

    _animation2 = Tween<Offset>(
      begin: const Offset(0, 0.1),
      end: const Offset(0, -0.1),
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

    _animation3 = Tween<Offset>(
      begin: const Offset(0, 0.15),
      end: const Offset(0, -0.15),
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

    _colorAnimation = ColorTween(
      begin: Colors.grey[400],
      end: Colors.grey[600],
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildBubble(_animation1, 8.0),
        const SizedBox(width: 5),
        _buildBubble(_animation2, 8.0),
        const SizedBox(width: 5),
        _buildBubble(_animation3, 8.0),
      ],
    );
  }

  Widget _buildBubble(Animation<Offset> animation, double size) {
    return SlideTransition(
      position: animation,
      child: AnimatedBuilder(
        animation: _colorAnimation,
        builder: (context, child) {
          return ScaleTransition(
            scale: _controller,
            child: Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                color: _colorAnimation.value,
                shape: BoxShape.circle,
              ),
            ),
          );
        },
      ),
    );
  }
}
