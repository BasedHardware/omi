import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/pie_chart_data.dart';

/// Widget for rendering pie / donut charts from LLM-generated data.
class GenerativePieChartWidget extends StatefulWidget {
  final PieChartDisplayData data;
  final double height;
  final bool showLegend;

  const GenerativePieChartWidget({super.key, required this.data, this.height = 220, this.showLegend = true});

  @override
  State<GenerativePieChartWidget> createState() => _GenerativePieChartWidgetState();
}

class _GenerativePieChartWidgetState extends State<GenerativePieChartWidget> {
  int? _touchedIndex;

  @override
  Widget build(BuildContext context) {
    if (widget.data.isEmpty) {
      return _buildEmptyState();
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.data.title != null && widget.data.title!.isNotEmpty) ...[
            Text(
              widget.data.title!,
              style: const TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: AppStyles.spacingXL),
          ],
          SizedBox(
            height: widget.height,
            child: PieChart(
              PieChartData(
                pieTouchData: PieTouchData(
                  touchCallback: (FlTouchEvent event, pieTouchResponse) {
                    setState(() {
                      if (!event.isInterestedForInteractions ||
                          pieTouchResponse == null ||
                          pieTouchResponse.touchedSection == null) {
                        _touchedIndex = null;
                        return;
                      }
                      _touchedIndex = pieTouchResponse.touchedSection!.touchedSectionIndex;
                    });
                  },
                ),
                borderData: FlBorderData(show: false),
                sectionsSpace: 2,
                centerSpaceRadius: widget.data.isDonut ? 50 : 0,
                sections: _buildSections(),
              ),
              swapAnimationDuration: const Duration(milliseconds: 300),
              swapAnimationCurve: Curves.easeInOut,
            ),
          ),
          if (widget.showLegend) ...[
            const SizedBox(height: AppStyles.spacingXL),
            _buildLegend(),
            const SizedBox(height: AppStyles.spacingL),
          ],
        ],
      ),
    );
  }

  List<PieChartSectionData> _buildSections() {
    final total = widget.data.total;

    return widget.data.segments.asMap().entries.map((entry) {
      final index = entry.key;
      final segment = entry.value;
      final isTouched = index == _touchedIndex;
      final percentage = total > 0 ? (segment.value / total * 100) : 0;

      return PieChartSectionData(
        color: segment.color,
        value: segment.value,
        title: isTouched ? '${percentage.toStringAsFixed(1)}%' : '',
        radius: isTouched ? 65 : 55,
        titleStyle: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: AppColors.textPrimary,
          shadows: [Shadow(color: Colors.black45, blurRadius: 2)],
        ),
        titlePositionPercentageOffset: 0.55,
      );
    }).toList();
  }

  Widget _buildLegend() {
    return Wrap(
      spacing: AppStyles.spacingL,
      runSpacing: AppStyles.spacingS,
      children: widget.data.segments.asMap().entries.map((entry) {
        final index = entry.key;
        final segment = entry.value;
        final isTouched = index == _touchedIndex;
        final total = widget.data.total;
        final percentage = total > 0 ? (segment.value / total * 100) : 0;

        return GestureDetector(
          onTap: () {
            setState(() {
              _touchedIndex = _touchedIndex == index ? null : index;
            });
          },
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: segment.color,
                  borderRadius: BorderRadius.circular(3),
                  border: isTouched ? Border.all(color: AppColors.textPrimary, width: 1.5) : null,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '${segment.label} (${percentage.toStringAsFixed(0)}%)',
                style: TextStyle(
                  color: isTouched ? AppColors.textPrimary : AppColors.textTertiary,
                  fontSize: 12,
                  fontWeight: isTouched ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  Widget _buildEmptyState() {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Text('No chart data available', style: TextStyle(color: AppColors.textTertiary, fontSize: 14)),
    );
  }
}
