import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';

class MemoriesOnboardingWidget extends StatelessWidget {
  const MemoriesOnboardingWidget({super.key});

  @override
  Widget build(BuildContext context) {
    if (SharedPreferencesUtil().isHomeOnboardingCompleted) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Arrow pointing up to brain icon - positioned to align with brain button
          Align(
            alignment: Alignment.centerRight,
            child: Padding(
              // Position arrow under the brain button (first icon after search)
              padding: const EdgeInsets.only(right: 44),
              child: const MemoriesOnboardingArrow(),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            "Let's see your brain!",
            style: TextStyle(
              color: Colors.grey.shade400,
              fontSize: 18,
              fontWeight: FontWeight.w400,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// Arrow that points UP to the brain icon from below
class MemoriesOnboardingArrow extends StatelessWidget {
  const MemoriesOnboardingArrow({super.key});

  @override
  Widget build(BuildContext context) {
    if (SharedPreferencesUtil().isHomeOnboardingCompleted) {
      return const SizedBox.shrink();
    }

    // Arrow pointing up from below the brain icon
    return SizedBox(
      width: 44,
      height: 45,
      child: Center(
        child: CustomPaint(
          size: const Size(20, 40),
          painter: _ArrowUpPainter(),
        ),
      ),
    );
  }
}

// Arrow pointing up
class _ArrowUpPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.grey.shade500
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // Vertical line going up
    final path = Path();
    path.moveTo(size.width * 0.5, size.height);
    path.lineTo(size.width * 0.5, size.height * 0.2);

    canvas.drawPath(path, paint);

    // Arrow head pointing up
    final arrowPath = Path();
    arrowPath.moveTo(size.width * 0.5 - 5, size.height * 0.35);
    arrowPath.lineTo(size.width * 0.5, size.height * 0.2);
    arrowPath.lineTo(size.width * 0.5 + 5, size.height * 0.35);

    canvas.drawPath(arrowPath, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
