import 'package:flutter/material.dart';

class ProgressBarWithPercentage extends StatefulWidget {
  final double progressValue;

  /// Renders the percentage as plain white text to the right of the bar
  /// instead of the floating bubble+pointer. Used by onboarding; the
  /// Settings speech-profile page keeps the bubble.
  final bool showPercentageAsPlainText;

  const ProgressBarWithPercentage({
    super.key,
    required this.progressValue,
    this.showPercentageAsPlainText = false,
  });
  @override
  _ProgressBarWithPercentageState createState() => _ProgressBarWithPercentageState();
}

class _ProgressBarWithPercentageState extends State<ProgressBarWithPercentage> {
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final barWidth = constraints.maxWidth;
        final targetProgress = double.parse(widget.progressValue.toStringAsFixed(2));

        // Eases the bar (and the bubble/percentage riding on it) toward each
        // new progress value instead of snapping instantly.
        return TweenAnimationBuilder<double>(
          tween: Tween<double>(begin: targetProgress, end: targetProgress),
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeOut,
          builder: (context, progress, child) {
            final displayPercent = '${(progress * 100).toInt()}%';

            if (widget.showPercentageAsPlainText) {
              return Row(
                children: [
                  Expanded(
                    child: Container(
                      height: 8,
                      decoration: BoxDecoration(
                        borderRadius: const BorderRadius.all(Radius.circular(10)),
                        border: Border.all(color: Colors.white),
                      ),
                      child: ClipRRect(
                        borderRadius: const BorderRadius.all(Radius.circular(9)),
                        child: LinearProgressIndicator(
                          value: progress,
                          backgroundColor: Colors.grey.shade300,
                          valueColor: const AlwaysStoppedAnimation<Color>(Colors.black),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(displayPercent, style: const TextStyle(color: Colors.white, fontSize: 14)),
                ],
              );
            }

            return SizedBox(
              height: 60,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: 46,
                    width: barWidth,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Positioned(
                          left: (barWidth * progress),
                          child: FractionalTranslation(
                            translation: const Offset(-0.5, 0.0),
                            child: ProgressBubble(content: displayPercent),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    width: barWidth,
                    height: 8,
                    decoration: BoxDecoration(
                      borderRadius: const BorderRadius.all(Radius.circular(10)),
                      border: Border.all(color: Colors.white),
                    ),
                    child: ClipRRect(
                      borderRadius: const BorderRadius.all(Radius.circular(9)),
                      child: LinearProgressIndicator(
                        value: progress,
                        backgroundColor: Colors.grey.shade300,
                        valueColor: const AlwaysStoppedAnimation<Color>(Colors.black),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class TrianglePainter extends CustomPainter {
  final Color color;
  final Color shadowColor;
  final double triangleHeight;
  final double triangleBaseWidth;

  TrianglePainter({
    required this.color,
    required this.shadowColor,
    this.triangleHeight = 10.0, // Default height
    this.triangleBaseWidth = 10.0, // Default base width
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    final trianglePath = Path()
      // Move to the left point of the base of the triangle
      ..moveTo(size.width / 2 - triangleBaseWidth / 2, 0)
      // Draw a line to the right point of the base
      ..lineTo(size.width / 2 + triangleBaseWidth / 2, 0)
      // Draw a line to the tip of the triangle (height)
      ..lineTo(size.width / 2, triangleHeight)
      ..close();

    // Draw triangle
    canvas.drawPath(trianglePath, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class ProgressBubble extends StatelessWidget {
  final String content;
  final double triangleHeight;

  const ProgressBubble({super.key, required this.content, this.triangleHeight = 10});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Text(content, style: const TextStyle(fontSize: 14, color: Colors.black)),
          ),
        ),
        CustomPaint(
          painter: TrianglePainter(color: Colors.white, shadowColor: Colors.grey.withValues(alpha: 0.5)),
          size: Size(10, triangleHeight),
        ),
      ],
    );
  }
}
