import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:provider/provider.dart';

/// Daily Score Widget - Shows task completion rate as a 0-5 score
class DailyScoreWidget extends StatefulWidget {
  const DailyScoreWidget({super.key});

  @override
  State<DailyScoreWidget> createState() => _DailyScoreWidgetState();
}

class _DailyScoreWidgetState extends State<DailyScoreWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        // Calculate today's tasks - only tasks due today
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
          score = 0; // No tasks = 0 score
        } else {
          final ratio = completedTasks / totalTasks;
          // Map 0-1 ratio to 0-5 score
          score = (ratio * 5).clamp(0.0, 5.0);
        }

        // Round to nearest 0.5
        score = (score * 2).roundToDouble() / 2;

        final statusColor = _getStatusColor(score);

        return GestureDetector(
          onTap: () {
            HapticFeedback.lightImpact();
            _showScoreDetails(context, score, completedTasks, totalTasks);
          },
          child: Container(
            margin: const EdgeInsets.only(bottom: 20),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: const Color(0xFF1A1A1C),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                // Left side: Text content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'DAILY SCORE',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1.2,
                          color: Colors.white.withOpacity(0.5),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'A score to help you better\nfocus on execution.',
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.white.withOpacity(0.5),
                          height: 1.4,
                        ),
                      ),
                      const SizedBox(height: 14),
                      // "your score >" link
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              'Your score',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: Colors.white.withOpacity(0.8),
                              ),
                            ),
                            const SizedBox(width: 4),
                            Icon(
                              Icons.chevron_right,
                              size: 16,
                              color: Colors.white.withOpacity(0.5),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                // Right side: Semicircular gauge
                SizedBox(
                  width: 130,
                  height: 85,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      // Gauge arc
                      Positioned(
                        top: 0,
                        child: CustomPaint(
                          size: const Size(130, 75),
                          painter: _SemicircleGaugePainter(
                            score: score,
                            color: statusColor,
                          ),
                        ),
                      ),
                      // Score text positioned inside the arc - aligned with arch start
                      Positioned(
                        top: 38,
                        child: Text(
                          _formatScore(score),
                          style: TextStyle(
                            fontSize: 44,
                            fontWeight: FontWeight.w500,
                            color: statusColor,
                            height: 1,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _formatScore(double score) {
    // Show integer if whole number, otherwise one decimal
    if (score == score.roundToDouble()) {
      return score.toInt().toString();
    }
    return score.toStringAsFixed(1);
  }

  Color _getStatusColor(double score) {
    // When no progress (0), use neutral grey for consistency
    if (score == 0) return Colors.grey.shade500;
    if (score >= 4.5) return const Color(0xFFFFD60A); // Gold/Yellow
    if (score >= 3.5) return const Color(0xFFFFD60A); // Gold/Yellow
    if (score >= 2.5) return const Color(0xFFF59E0B); // Amber
    if (score >= 1.5) return const Color(0xFFF97316); // Orange
    return const Color(0xFFEF4444); // Red
  }

  void _showScoreDetails(BuildContext context, double score, int completed, int total) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        decoration: const BoxDecoration(
          color: Color(0xFF1A1A1A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.all(24),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 24),
                decoration: BoxDecoration(
                  color: Colors.grey.shade700,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Text(
                'Daily Score Breakdown',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 20),
              _buildDetailRow('Today\'s Score', _formatScore(score), _getStatusColor(score)),
              const SizedBox(height: 12),
              _buildDetailRow('Tasks Completed', '$completed / $total', Colors.white70),
              const SizedBox(height: 12),
              _buildDetailRow(
                'Completion Rate',
                total > 0 ? '${(completed / total * 100).toStringAsFixed(0)}%' : 'N/A',
                Colors.white70,
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'How it works',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: Colors.white.withOpacity(0.8),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Your daily score is based on task completion. Complete your tasks to improve your score!',
                      style: TextStyle(
                        fontSize: 13,
                        color: Colors.white.withOpacity(0.5),
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text(
                    'Got it',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 15,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDetailRow(String label, String value, Color valueColor) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 14,
            color: Colors.white.withOpacity(0.5),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: valueColor,
          ),
        ),
      ],
    );
  }
}

/// Custom painter for semicircular gauge (like the design)
class _SemicircleGaugePainter extends CustomPainter {
  final double score;
  final Color color;

  _SemicircleGaugePainter({required this.score, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height);
    final radius = size.width / 2 - 6;

    // Background arc (semicircle)
    final bgPaint = Paint()
      ..color = Colors.white.withOpacity(0.12)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      math.pi, // Start from left
      math.pi, // Sweep 180 degrees (semicircle)
      false,
      bgPaint,
    );

    // Progress arc
    final progress = score / 5.0;
    final progressPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      math.pi, // Start from left
      math.pi * progress, // Sweep based on progress
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(_SemicircleGaugePainter old) =>
      old.score != score || old.color != color;
}
