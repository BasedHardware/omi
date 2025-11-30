import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../models/pie_chart_data.dart';

/// Widget for rendering horizontal bar charts from LLM-generated data
class GenerativeBarChartWidget extends StatefulWidget {
  final PieChartDisplayData data;
  final double height;
  final bool showLegend;

  const GenerativeBarChartWidget({
    super.key,
    required this.data,
    this.height = 220,
    this.showLegend = true,
  });

  @override
  State<GenerativeBarChartWidget> createState() => _GenerativeBarChartWidgetState();
}

class _GenerativeBarChartWidgetState extends State<GenerativeBarChartWidget> {
  int? _touchedIndex;

  @override
  Widget build(BuildContext context) {
    if (widget.data.isEmpty) {
      return _buildEmptyState();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withOpacity(0.08),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Title
          if (widget.data.title != null && widget.data.title!.isNotEmpty) ...[
            Text(
              widget.data.title!,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Chart
          SizedBox(
            height: widget.height - (widget.showLegend ? 40 : 0),
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: _getMaxValue() * 1.2,
                barTouchData: BarTouchData(
                  enabled: true,
                  touchTooltipData: BarTouchTooltipData(
                    tooltipRoundedRadius: 8,
                    getTooltipColor: (group) => const Color(0xFF35343B),
                    getTooltipItem: (group, groupIndex, rod, rodIndex) {
                      final segment = widget.data.segments[group.x];
                      final total = widget.data.total;
                      final percentage = total > 0
                          ? (segment.value / total * 100).toStringAsFixed(1)
                          : '0';
                      return BarTooltipItem(
                        '${segment.label}\n${segment.value.toStringAsFixed(0)} ($percentage%)',
                        const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w500,
                          fontSize: 12,
                        ),
                      );
                    },
                  ),
                  touchCallback: (FlTouchEvent event, barTouchResponse) {
                    setState(() {
                      if (!event.isInterestedForInteractions ||
                          barTouchResponse == null ||
                          barTouchResponse.spot == null) {
                        _touchedIndex = null;
                        return;
                      }
                      _touchedIndex = barTouchResponse.spot!.touchedBarGroupIndex;
                    });
                  },
                ),
                titlesData: FlTitlesData(
                  show: true,
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (value, meta) {
                        final index = value.toInt();
                        if (index < 0 || index >= widget.data.segments.length) {
                          return const SizedBox.shrink();
                        }
                        final segment = widget.data.segments[index];
                        final isTouched = index == _touchedIndex;
                        return Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text(
                            _truncateLabel(segment.label),
                            style: TextStyle(
                              color: isTouched
                                  ? Colors.white
                                  : Colors.white.withOpacity(0.7),
                              fontSize: 11,
                              fontWeight:
                                  isTouched ? FontWeight.w600 : FontWeight.normal,
                            ),
                          ),
                        );
                      },
                      reservedSize: 32,
                    ),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 40,
                      getTitlesWidget: (value, meta) {
                        return Text(
                          value.toInt().toString(),
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 10,
                          ),
                        );
                      },
                    ),
                  ),
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                ),
                borderData: FlBorderData(show: false),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: _getMaxValue() / 4,
                  getDrawingHorizontalLine: (value) {
                    return FlLine(
                      color: Colors.white.withOpacity(0.1),
                      strokeWidth: 1,
                    );
                  },
                ),
                barGroups: _buildBarGroups(),
              ),
              swapAnimationDuration: const Duration(milliseconds: 300),
              swapAnimationCurve: Curves.easeInOut,
            ),
          ),
        ],
      ),
    );
  }

  double _getMaxValue() {
    if (widget.data.segments.isEmpty) return 100;
    return widget.data.segments
        .map((s) => s.value)
        .reduce((a, b) => a > b ? a : b);
  }

  String _truncateLabel(String label) {
    if (label.length <= 10) return label;
    return '${label.substring(0, 8)}...';
  }

  List<BarChartGroupData> _buildBarGroups() {
    return widget.data.segments.asMap().entries.map((entry) {
      final index = entry.key;
      final segment = entry.value;
      final isTouched = index == _touchedIndex;

      return BarChartGroupData(
        x: index,
        barRods: [
          BarChartRodData(
            toY: segment.value,
            color: segment.color,
            width: isTouched ? 24 : 20,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
            backDrawRodData: BackgroundBarChartRodData(
              show: true,
              toY: _getMaxValue() * 1.2,
              color: Colors.white.withOpacity(0.05),
            ),
          ),
        ],
      );
    }).toList();
  }

  Widget _buildEmptyState() {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withOpacity(0.08),
          width: 1,
        ),
      ),
      child: Center(
        child: Text(
          'No chart data available',
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 14,
          ),
        ),
      ),
    );
  }
}
