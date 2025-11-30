import '../models/pie_chart_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <pie-chart> tags containing segment elements.
/// Despite the name, this data can be rendered as pie, donut, or bar charts.
///
/// Example:
/// ```xml
/// <pie-chart title="Distribution" type="donut">
///   <segment label="Category A" value="40" color="#8B5CF6"/>
///   <segment label="Category B" value="30" color="#10B981"/>
/// </pie-chart>
/// ```
class ChartParser extends BaseTagParser {
  // Pattern to match <pie-chart ...>...</pie-chart> blocks
  static final _chartPattern = RegExp(
    r'<pie-chart([^>]*)>([\s\S]*?)</pie-chart>',
    caseSensitive: false,
  );

  // Pattern to match <segment .../> tags within pie-chart
  static final _segmentPattern = RegExp(
    r'<segment\s+((?:[^>"]*|"[^"]*")+)\s*\/?>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _chartPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final chartAttributes = match.group(1) ?? '';
    final innerContent = match.group(2) ?? '';
    return _parseChart(chartAttributes, innerContent);
  }

  PieChartSegment? _parseChart(String chartAttributes, String innerContent) {
    final attributes = parseAttributes(chartAttributes);
    final segments = <PieChartSegmentData>[];

    int colorIndex = 0;
    for (final segmentMatch in _segmentPattern.allMatches(innerContent)) {
      final segmentAttrString = segmentMatch.group(1) ?? '';
      final segmentAttrs = parseAttributes(segmentAttrString);

      // Use default palette color if not specified
      final defaultColor = PieChartDisplayData
          .defaultPalette[colorIndex % PieChartDisplayData.defaultPalette.length];

      segments.add(PieChartSegmentData.fromAttributes(segmentAttrs, defaultColor));
      colorIndex++;
    }

    if (segments.isEmpty) return null;

    return PieChartSegment(PieChartDisplayData(
      title: attributes['title'],
      segments: segments,
      chartType: _parseChartType(attributes['type']),
    ));
  }

  /// Parse chart type from string attribute
  ChartType _parseChartType(String? type) {
    switch (type?.toLowerCase()) {
      case 'pie':
        return ChartType.pie;
      case 'donut':
        return ChartType.donut;
      case 'bar':
      default:
        return ChartType.bar;
    }
  }
}
