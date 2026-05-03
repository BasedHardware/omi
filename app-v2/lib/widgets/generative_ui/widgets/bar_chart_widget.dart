import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/pie_chart_data.dart';

/// Widget for rendering vertical bar charts from LLM-generated data.
class GenerativeBarChartWidget extends StatefulWidget {
  final PieChartDisplayData data;
  final double height;
  final bool showLegend;

  const GenerativeBarChartWidget({super.key, required this.data, this.height = 220, this.showLegend = true});

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

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.data.title != null && widget.data.title!.isNotEmpty) ...[
            Text(
              widget.data.title!,
              style: const TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: AppStyles.spacingL),
          ],
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
                    getTooltipColor: (group) => AppColors.backgroundTertiary,
                    getTooltipItem: (group, groupIndex, rod, rodIndex) {
                      final segment = widget.data.segments[group.x];
                      final total = widget.data.total;
                      final percentage = total > 0 ? (segment.value / total * 100).toStringAsFixed(1) : '0';
                      return BarTooltipItem(
                        '${segment.label}\n${segment.value.toStringAsFixed(0)} ($percentage%)',
                        const TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.w500, fontSize: 12),
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
                          padding: const EdgeInsets.only(top: AppStyles.spacingS),
                          child: Text(
                            _truncateLabel(segment.label),
                            style: TextStyle(
                              color: isTouched ? AppColors.textPrimary : AppColors.textTertiary,
                              fontSize: 11,
                              fontWeight: isTouched ? FontWeight.w600 : FontWeight.normal,
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
                          style: const TextStyle(color: AppColors.textQuaternary, fontSize: 10),
                        );
                      },
                    ),
                  ),
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                ),
                borderData: FlBorderData(show: false),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: _getMaxValue() / 4,
                  getDrawingHorizontalLine: (value) {
                    return FlLine(color: Colors.white.withValues(alpha: 0.1), strokeWidth: 1);
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
    return widget.data.segments.map((s) => s.value).reduce((a, b) => a > b ? a : b);
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
              color: Colors.white.withValues(alpha: 0.05),
            ),
          ),
        ],
      );
    }).toList();
  }

  Widget _buildEmptyState() {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Text('No chart data available', style: TextStyle(color: AppColors.textTertiary, fontSize: 14)),
    );
  }
}
