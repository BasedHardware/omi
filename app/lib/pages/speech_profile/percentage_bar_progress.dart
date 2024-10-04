import 'package:flutter/material.dart';

class ProgressBarWithPercentage extends StatefulWidget {
  final double progressValue;

  const ProgressBarWithPercentage({super.key, required this.progressValue});
  @override
  _ProgressBarWithPercentageState createState() => _ProgressBarWithPercentageState();
}

class _ProgressBarWithPercentageState extends State<ProgressBarWithPercentage> {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 60,
      width: 400,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            height: 46,
            child: Stack(
              children: [
                Positioned(
                  left: widget.progressValue * (400 - 122),
                  child: ProgressBubble(
                    content: '${(widget.progressValue * 100).toInt()}%',
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 300,
            height: 8,
            child: ClipRRect(
              borderRadius: const BorderRadius.all(Radius.circular(10)),
              child: LinearProgressIndicator(
                value: widget.progressValue,
                backgroundColor: Colors.grey.shade300,
                valueColor: const AlwaysStoppedAnimation<Color>(Colors.deepPurple),
              ),
            ),
          ),
        ],
      ),
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

  const ProgressBubble({
    super.key,
    required this.content,
    this.triangleHeight = 10,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          // margin: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Text(
              content,
              style: const TextStyle(
                fontSize: 14,
                color: Colors.grey,
              ),
            ),
          ),
        ),
        CustomPaint(
          painter: TrianglePainter(
            color: Colors.white,
            shadowColor: Colors.grey.withOpacity(0.5),
          ),
          size: Size(10, triangleHeight),
        ),
      ],
    );
  }
}
