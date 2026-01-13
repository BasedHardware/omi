import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

/// Desktop Daily Score Widget - Shows task completion rate as a 0-5 score
class DesktopDailyScoreWidget extends StatelessWidget {
  const DesktopDailyScoreWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        // Calculate today's tasks
        final now = DateTime.now();
        final todayStart = DateTime(now.year, now.month, now.day);
        final todayEnd = todayStart.add(const Duration(days: 1));

        // Get tasks due today only
        final todayTasks = provider.actionItems.where((item) {
          if (item.dueAt == null) return false;
          return item.dueAt!.isAfter(todayStart.subtract(const Duration(days: 1))) && 
                 item.dueAt!.isBefore(todayEnd);
        }).toList();

        final totalTasks = todayTasks.length;
        final completedTasks = todayTasks.where((t) => t.completed).length;

        // Calculate score (0-5)
        double score;
        if (totalTasks == 0) {
          score = 0;
        } else {
          final ratio = completedTasks / totalTasks;
          score = (ratio * 5).clamp(0.0, 5.0);
        }

        // Round to nearest 0.5
        score = (score * 2).roundToDouble() / 2;

        final statusColor = _getStatusColor(score);

        return Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.8),
              width: 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Text(
                'DAILY SCORE',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'A score to help you better focus on execution.',
                style: TextStyle(
                  fontSize: 13,
                  color: ResponsiveHelper.textSecondary,
                  height: 1.3,
                ),
              ),
              const SizedBox(height: 12),
              // Center: Semicircular gauge with score
              Expanded(
                child: Center(
                  child: SizedBox(
                    width: 130,
                    height: 80,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        // Gauge arc
                        Positioned(
                          top: 0,
                          child: CustomPaint(
                            size: const Size(130, 70),
                            painter: _SemicircleGaugePainter(
                              score: score,
                              color: statusColor,
                            ),
                          ),
                        ),
                      // Score text
                      Positioned(
                        top: 28,
                        child: Text(
                          _formatScore(score),
                          style: TextStyle(
                            fontSize: 40,
                            fontWeight: FontWeight.w500,
                            color: statusColor,
                            height: 1,
                          ),
                        ),
                      ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  String _formatScore(double score) {
    if (score == score.roundToDouble()) {
      return score.toInt().toString();
    }
    return score.toStringAsFixed(1);
  }

  Color _getStatusColor(double score) {
    if (score == 0) return ResponsiveHelper.textTertiary;
    if (score >= 4.5) return const Color(0xFFFFD60A);
    if (score >= 3.5) return const Color(0xFFFFD60A);
    if (score >= 2.5) return const Color(0xFFF59E0B);
    if (score >= 1.5) return const Color(0xFFF97316);
    return const Color(0xFFEF4444);
  }
}

class _SemicircleGaugePainter extends CustomPainter {
  final double score;
  final Color color;

  _SemicircleGaugePainter({required this.score, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height);
    final radius = size.width / 2 - 6;

    // Background arc
    final bgPaint = Paint()
      ..color = ResponsiveHelper.backgroundTertiary.withOpacity(0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      math.pi,
      math.pi,
      false,
      bgPaint,
    );

    // Progress arc
    final progress = score / 5.0;
    final progressPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      math.pi,
      math.pi * progress,
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(_SemicircleGaugePainter old) =>
      old.score != score || old.color != color;
}
