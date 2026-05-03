import 'package:flutter/material.dart';

/// Available chart types for data visualization.
enum ChartType { bar, pie, donut }

/// Data model for a single chart segment.
class PieChartSegmentData {
  final String label;
  final double value;
  final Color color;

  const PieChartSegmentData({required this.label, required this.value, required this.color});

  factory PieChartSegmentData.fromAttributes(Map<String, String> attributes, Color defaultColor) {
    return PieChartSegmentData(
      label: attributes['label'] ?? '',
      value: double.tryParse(attributes['value'] ?? '0') ?? 0,
      color: _parseColor(attributes['color']) ?? defaultColor,
    );
  }

  static const _namedColors = <String, Color>{
    'yellow': Color(0xFFF9D71C),
    'orange': Color(0xFFF97316),
    'green': Color(0xFF22C55E),
    'blue': Color(0xFF3B82F6),
    'purple': Color(0xFF8B5CF6),
    'red': Color(0xFFEF4444),
    'pink': Color(0xFFEC4899),
    'cyan': Color(0xFF06B6D4),
    'amber': Color(0xFFF59E0B),
    'lime': Color(0xFF84CC16),
    'teal': Color(0xFF14B8A6),
    'indigo': Color(0xFF6366F1),
    'white': Color(0xFFFFFFFF),
    'black': Color(0xFF000000),
    'gray': Color(0xFF6B7280),
    'grey': Color(0xFF6B7280),
  };

  static Color? _parseColor(String? colorString) {
    if (colorString == null || colorString.isEmpty) return null;
    final normalized = colorString.trim().toLowerCase();
    if (_namedColors.containsKey(normalized)) {
      return _namedColors[normalized];
    }
    String hex = normalized.replaceAll('#', '');
    if (hex.length == 6) {
      hex = 'FF$hex';
    }
    if (hex.length == 8) {
      try {
        return Color(int.parse(hex, radix: 16));
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  double get percentage => value;
}

/// Data model for chart display.
class PieChartDisplayData {
  final String? title;
  final List<PieChartSegmentData> segments;
  final ChartType chartType;

  const PieChartDisplayData({this.title, required this.segments, this.chartType = ChartType.bar});

  bool get isPieStyle => chartType == ChartType.pie || chartType == ChartType.donut;
  bool get isDonut => chartType == ChartType.donut;

  /// Default color palette for chart segments.
  static const List<Color> defaultPalette = [
    Color(0xFF8B5CF6),
    Color(0xFF10B981),
    Color(0xFFF59E0B),
    Color(0xFF3B82F6),
    Color(0xFFEF4444),
    Color(0xFFA78BFA),
    Color(0xFF06B6D4),
    Color(0xFFF97316),
  ];

  double get total => segments.fold(0, (sum, s) => sum + s.value);
  bool get isEmpty => segments.isEmpty;
}
