import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/message.dart';

class ChartMessageWidget extends StatelessWidget {
  final ChartData chartData;

  const ChartMessageWidget({super.key, required this.chartData});

  Color _parseColor(String? hex) {
    if (hex == null || hex.isEmpty) return const Color(0xFF448AFF);
    hex = hex.replaceFirst('#', '');
    if (hex.length == 6) hex = 'FF$hex';
    return Color(int.parse(hex, radix: 16));
  }

  @override
  Widget build(BuildContext context) {
    if (chartData.datasets.isEmpty || chartData.datasets.first.dataPoints.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.fromLTRB(12, 16, 16, 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A20),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            chartData.title,
            style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 20),
          SizedBox(
            height: 200,
            child: chartData.chartType == 'bar' ? _buildBarChart() : _buildLineChart(),
          ),
        ],
      ),
    );
  }

  int _labelInterval(List<ChartDataPoint> points) {
    if (points.isEmpty) return 1;
    double avgLen = points.map((p) => p.label.length).reduce((a, b) => a + b) / points.length;
    if (points.length <= 4) return 1;
    if (avgLen <= 4) return points.length > 12 ? 2 : 1;
    if (avgLen <= 7) return points.length > 7 ? 2 : 1;
    // Long labels — show first, last, and a few in between
    return (points.length / 4).ceil().clamp(2, points.length);
  }

  Widget _bottomLabel(String text, int idx, int total, int interval) {
    // Always show first and last; otherwise respect interval
    bool show = idx == 0 || idx == total - 1 || idx % interval == 0;
    if (!show) return const SizedBox.shrink();
    return SizedBox(
      width: 48,
      child: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(
          text,
          style: TextStyle(color: Colors.grey.shade500, fontSize: 10),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
        ),
      ),
    );
  }

  Widget _buildLineChart() {
    final dataset = chartData.datasets.first;
    final color = _parseColor(dataset.color);
    final points = dataset.dataPoints;

    double minY = points.map((p) => p.value).reduce((a, b) => a < b ? a : b);
    double maxY = points.map((p) => p.value).reduce((a, b) => a > b ? a : b);
    double padding = (maxY - minY) * 0.15;
    if (padding == 0) padding = 1;
    minY = (minY - padding).clamp(0, double.infinity);
    maxY = maxY + padding;

    return LineChart(
      LineChartData(
        minY: minY,
        maxY: maxY,
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: _niceInterval(minY, maxY),
          getDrawingHorizontalLine: (value) => FlLine(
            color: Colors.white.withOpacity(0.06),
            strokeWidth: 1,
          ),
        ),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 32,
              interval: 1,
              getTitlesWidget: (value, meta) {
                int idx = value.toInt();
                if (idx < 0 || idx >= points.length) return const SizedBox.shrink();
                return _bottomLabel(points[idx].label, idx, points.length, _labelInterval(points));
              },
            ),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 42,
              interval: _niceInterval(minY, maxY),
              getTitlesWidget: (value, meta) {
                if (value == meta.max || value == meta.min) return const SizedBox.shrink();
                return Text(
                  _formatValue(value),
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 11),
                );
              },
            ),
          ),
        ),
        borderData: FlBorderData(show: false),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => const Color(0xFF2C2C34),
            tooltipRoundedRadius: 8,
            getTooltipItems: (spots) {
              return spots.map((spot) {
                int idx = spot.x.toInt();
                String label = idx >= 0 && idx < points.length ? points[idx].label : '';
                return LineTooltipItem(
                  '$label\n${_formatValue(spot.y)}',
                  const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                );
              }).toList();
            },
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: List.generate(points.length, (i) => FlSpot(i.toDouble(), points[i].value)),
            isCurved: true,
            curveSmoothness: 0.25,
            color: color,
            barWidth: 2.5,
            isStrokeCapRound: true,
            dotData: FlDotData(
              show: points.length <= 14,
              getDotPainter: (spot, percent, barData, index) => FlDotCirclePainter(
                radius: 3,
                color: color,
                strokeWidth: 0,
              ),
            ),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [color.withOpacity(0.25), color.withOpacity(0.0)],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBarChart() {
    final dataset = chartData.datasets.first;
    final color = _parseColor(dataset.color);
    final points = dataset.dataPoints;

    double maxY = points.map((p) => p.value).reduce((a, b) => a > b ? a : b);
    double padding = maxY * 0.15;
    if (padding == 0) padding = 1;
    maxY = maxY + padding;

    return BarChart(
      BarChartData(
        maxY: maxY,
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: _niceInterval(0, maxY),
          getDrawingHorizontalLine: (value) => FlLine(
            color: Colors.white.withOpacity(0.06),
            strokeWidth: 1,
          ),
        ),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 32,
              getTitlesWidget: (value, meta) {
                int idx = value.toInt();
                if (idx < 0 || idx >= points.length) return const SizedBox.shrink();
                return _bottomLabel(points[idx].label, idx, points.length, _labelInterval(points));
              },
            ),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 42,
              interval: _niceInterval(0, maxY),
              getTitlesWidget: (value, meta) {
                if (value == meta.max || value == meta.min) return const SizedBox.shrink();
                return Text(
                  _formatValue(value),
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 11),
                );
              },
            ),
          ),
        ),
        borderData: FlBorderData(show: false),
        barTouchData: BarTouchData(
          touchTooltipData: BarTouchTooltipData(
            getTooltipColor: (_) => const Color(0xFF2C2C34),
            tooltipRoundedRadius: 8,
            getTooltipItem: (group, groupIndex, rod, rodIndex) {
              int idx = group.x;
              String label = idx >= 0 && idx < points.length ? points[idx].label : '';
              return BarTooltipItem(
                '$label\n${_formatValue(rod.toY)}',
                const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
              );
            },
          ),
        ),
        barGroups: List.generate(
          points.length,
          (i) => BarChartGroupData(
            x: i,
            barRods: [
              BarChartRodData(
                toY: points[i].value,
                color: color,
                width: points.length <= 7 ? 20 : (points.length <= 14 ? 12 : 8),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  double _niceInterval(double min, double max) {
    double range = max - min;
    if (range <= 0) return 1;
    double rawInterval = range / 5;
    double magnitude = 1;
    while (rawInterval > 10) {
      rawInterval /= 10;
      magnitude *= 10;
    }
    while (rawInterval < 1) {
      rawInterval *= 10;
      magnitude /= 10;
    }
    if (rawInterval <= 1.5) return 1 * magnitude;
    if (rawInterval <= 3.5) return 2.5 * magnitude;
    if (rawInterval <= 7.5) return 5 * magnitude;
    return 10 * magnitude;
  }

  String _formatValue(double value) {
    if (value >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M';
    if (value >= 1000) return '${(value / 1000).toStringAsFixed(1)}K';
    if (value == value.roundToDouble()) return value.toInt().toString();
    return value.toStringAsFixed(1);
  }
}
