import 'package:flutter/material.dart';

/// Data model for a highlight item
class HighlightData {
  final String text;
  final Color color;

  const HighlightData({
    required this.text,
    required this.color,
  });
}

/// Display data for a list of highlights
class HighlightDisplayData {
  final List<HighlightData> items;

  const HighlightDisplayData({required this.items});

  bool get isEmpty => items.isEmpty;
}
