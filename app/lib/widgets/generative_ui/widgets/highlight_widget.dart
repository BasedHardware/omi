import 'package:flutter/material.dart';
import '../models/highlight_data.dart';

/// Widget that displays a highlighted text with colored background
class HighlightWidget extends StatelessWidget {
  final HighlightData data;

  const HighlightWidget({
    super.key,
    required this.data,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      margin: const EdgeInsets.symmetric(vertical: 4),
      decoration: BoxDecoration(
        color: data.color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: data.color.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Text(
        data.text,
        style: TextStyle(
          color: data.color,
          fontSize: 14,
          fontWeight: FontWeight.w500,
          height: 1.4,
        ),
      ),
    );
  }
}
