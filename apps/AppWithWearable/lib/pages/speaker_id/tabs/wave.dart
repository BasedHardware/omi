import 'package:flutter/material.dart';

class DashedLinePainter extends CustomPainter {
  final List<int> bucket;
  final int maxHeight;

  DashedLinePainter(this.bucket, {this.maxHeight = 1500});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 1.0
      ..style = PaintingStyle.stroke;

    final path = Path();
    double dashWidth = 5.0;
    double dashSpace = 5.0;
    double x = 0.0;
    double centerY = size.height / 2;
    int windowSize = 24000;
    int startIndex = (bucket.length > windowSize) ? bucket.length - windowSize : 0;

    // Apply smoothing to the bucket values
    List<double> smoothedBucket = _applySmoothing(bucket.sublist(startIndex));

    for (int i = 0; i < smoothedBucket.length; i++) {
      if (i % (dashWidth + dashSpace) < dashWidth) {
        // Normalize the value to fit within 0 to 1000
        double rawValue = smoothedBucket[i];
        double scaledValue = (rawValue < 100) ? 0 : ((rawValue / 32768.0) * maxHeight).clamp(0, 1000);
        // Ensure minimum value for the line height
        double minHeight = 1.0;
        scaledValue = scaledValue < minHeight ? minHeight : scaledValue;
        double y = centerY - scaledValue / 2;
        double yPositive = centerY + scaledValue / 2;
        y = y.clamp(0, size.height); // Ensure y is within the container bounds
        yPositive = yPositive.clamp(0, size.height); // Ensure yPositive is within the container bounds
        path.moveTo(x, yPositive);
        path.lineTo(x, y);
      }
      x += size.width / windowSize;
    }

    canvas.drawPath(path, paint);
  }

  List<double> _applySmoothing(List<int> data) {
    List<double> smoothedData = List.filled(data.length, 0.0);
    int smoothingWindow = 5;
    for (int i = 0; i < data.length; i++) {
      double sum = 0.0;
      int count = 0;
      for (int j = i - smoothingWindow; j <= i + smoothingWindow; j++) {
        if (j >= 0 && j < data.length) {
          sum += data[j];
          count++;
        }
      }
      smoothedData[i] = sum / count;
    }
    return smoothedData;
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) {
    return true;
  }
}