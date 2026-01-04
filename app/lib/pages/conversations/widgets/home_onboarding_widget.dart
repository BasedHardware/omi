import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';

class HomeOnboardingWidget extends StatelessWidget {
  const HomeOnboardingWidget({super.key});

  @override
  Widget build(BuildContext context) {
    if (SharedPreferencesUtil().isHomeOnboardingCompleted) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            "Here you'll see your\nconversations",
            style: TextStyle(
              color: Colors.grey.shade400,
              fontSize: 18,
              fontWeight: FontWeight.w400,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 12),
          // Vertical line
          Padding(
            padding: const EdgeInsets.only(left: 40),
            child: Container(
              width: 2,
              height: 40,
              color: Colors.grey.shade600,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            "Let's check your tasks",
            style: TextStyle(
              color: Colors.grey.shade400,
              fontSize: 18,
              fontWeight: FontWeight.w400,
            ),
          ),
          const SizedBox(height: 8),
          // Arrow pointing down to tasks tab (2nd icon)
          Padding(
            padding: const EdgeInsets.only(left: 85),
            child: CustomPaint(
              size: const Size(40, 70),
              painter: _ArrowDownPainter(),
            ),
          ),
        ],
      ),
    );
  }
}

// Arrow pointing straight down
class _ArrowDownPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.grey.shade600
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // Curved line going down
    final path = Path();
    path.moveTo(size.width * 0.5, 0);
    path.quadraticBezierTo(
      size.width * 0.6,
      size.height * 0.5,
      size.width * 0.5,
      size.height * 0.85,
    );

    canvas.drawPath(path, paint);

    // Arrow head pointing down
    final arrowPath = Path();
    arrowPath.moveTo(size.width * 0.5 - 6, size.height * 0.72);
    arrowPath.lineTo(size.width * 0.5, size.height * 0.85);
    arrowPath.lineTo(size.width * 0.5 + 6, size.height * 0.72);

    canvas.drawPath(arrowPath, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
