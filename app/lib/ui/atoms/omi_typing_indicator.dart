import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';

class OmiTypingIndicator extends AdaptiveWidget {
  const OmiTypingIndicator({super.key});

  @override
  Widget buildDesktop(BuildContext context) => _Indicator();

  @override
  Widget buildMobile(BuildContext context) => _Indicator();
}

class _Indicator extends StatefulWidget {
  @override
  State<_Indicator> createState() => _IndicatorState();
}

class _IndicatorState extends State<_Indicator> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _anim1;
  late final Animation<Offset> _anim2;
  late final Animation<Offset> _anim3;
  late final Animation<Color?> _color;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    _anim1 = _tween(0.2);
    _anim2 = _tween(0.1);
    _anim3 = _tween(0.15);

    _color = ColorTween(
      begin: Colors.grey[400],
      end: Colors.grey[600],
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));
  }

  Animation<Offset> _tween(double delta) => Tween<Offset>(
        begin: Offset(0, delta),
        end: Offset(0, -delta),
      ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

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
        _bubble(_anim1),
        const SizedBox(width: 5),
        _bubble(_anim2),
        const SizedBox(width: 5),
        _bubble(_anim3),
      ],
    );
  }

  Widget _bubble(Animation<Offset> anim) => SlideTransition(
        position: anim,
        child: AnimatedBuilder(
          animation: _color,
          builder: (context, _) => ScaleTransition(
            scale: _controller,
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: _color.value,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ),
      );
}
