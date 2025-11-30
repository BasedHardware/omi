import 'package:flutter/material.dart';

/// Data model for a single pie chart segment
class PieChartSegmentData {
  final String label;
  final double value;
  final Color color;

  const PieChartSegmentData({
    required this.label,
    required this.value,
    required this.color,
  });

  /// Parse from XML attributes map
  factory PieChartSegmentData.fromAttributes(
    Map<String, String> attributes,
    Color defaultColor,
  ) {
    return PieChartSegmentData(
      label: attributes['label'] ?? '',
      value: double.tryParse(attributes['value'] ?? '0') ?? 0,
      color: _parseColor(attributes['color']) ?? defaultColor,
    );
  }

  static Color? _parseColor(String? colorString) {
    if (colorString == null || colorString.isEmpty) return null;

    // Handle hex colors like "#8B5CF6" or "8B5CF6"
    String hex = colorString.replaceAll('#', '');
    if (hex.length == 6) {
      hex = 'FF$hex'; // Add alpha
    }
    if (hex.length == 8) {
      return Color(int.parse(hex, radix: 16));
    }
    return null;
  }

  double get percentage => value;
}

/// Data model for a complete pie chart
class PieChartDisplayData {
  final String? title;
  final List<PieChartSegmentData> segments;
  final bool isDonut;

  const PieChartDisplayData({
    this.title,
    required this.segments,
    this.isDonut = false,
  });

  /// Default color palette for chart segments
  static const List<Color> defaultPalette = [
    Color(0xFF8B5CF6), // Purple
    Color(0xFF10B981), // Green
    Color(0xFFF59E0B), // Orange
    Color(0xFF3B82F6), // Blue
    Color(0xFFEF4444), // Red
    Color(0xFFA78BFA), // Light purple
    Color(0xFF06B6D4), // Cyan
    Color(0xFFF97316), // Dark orange
  ];

  double get total => segments.fold(0, (sum, s) => sum + s.value);

  bool get isEmpty => segments.isEmpty;
}
