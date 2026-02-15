import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Daily Score Widget - Shows task completion rate as a 0-5 score
class DailyScoreWidget extends StatefulWidget {
  final GlobalKey<GoalsWidgetState>? goalsWidgetKey;

  const DailyScoreWidget({super.key, this.goalsWidgetKey});

  @override
  State<DailyScoreWidget> createState() => DailyScoreWidgetState();
}

class DailyScoreWidgetState extends State<DailyScoreWidget> {
  // Public method to reload goals when they change (now a no-op since provider handles it)
  void reloadGoals() {
    // Goals are now managed by GoalsProvider, no need to reload manually
  }

  void _addGoal() {
    widget.goalsWidgetKey?.currentState?.addGoal();
  }

  void _showCreateTaskSheet(BuildContext context) {
    final now = DateTime.now();
    final defaultDueDate = DateTime(now.year, now.month, now.day, 23, 59);
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ActionItemFormSheet(
        defaultDueDate: defaultDueDate,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<ActionItemsProvider, GoalsProvider>(
      builder: (context, provider, goalsProvider, child) {
        final goals = goalsProvider.goals;
        final isLoadingGoals = goalsProvider.isLoading;

        // Calculate today's tasks - only tasks due today
        final now = DateTime.now();
        final todayStart = DateTime(now.year, now.month, now.day);
        final todayEnd = todayStart.add(const Duration(days: 1));

        // Get tasks due today only
        final todayTasks = provider.actionItems.where((item) {
          if (item.dueAt == null) return false;
          return item.dueAt!.isAfter(todayStart.subtract(const Duration(days: 1))) && item.dueAt!.isBefore(todayEnd);
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

        // Round to nearest 0.1
        score = (score * 10).roundToDouble() / 10;

        final statusColor = _getStatusColor(score);

        return Container(
          margin: const EdgeInsets.only(bottom: 20),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Stack(
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  // Left side: Text content
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.dailyScore,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 1.2,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.l10n.dailyScoreDescription,
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.white.withOpacity(0.5),
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 14),
                        // "Add Goals" or "New Task" button
                        if (!isLoadingGoals)
                          GestureDetector(
                            onTap: () {
                              HapticFeedback.lightImpact();
                              MixpanelManager().dailyScoreCtaTapped(ctaType: goals.isEmpty ? 'add_goal' : 'new_task');
                              if (goals.isEmpty) {
                                _addGoal();
                              } else {
                                _showCreateTaskSheet(context);
                              }
                            },
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(
                                    goals.isEmpty ? context.l10n.addGoal : context.l10n.newTask,
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500,
                                      color: Colors.white.withOpacity(0.8),
                                    ),
                                  ),
                                  const SizedBox(width: 4),
                                  Icon(
                                    goals.isEmpty ? Icons.chevron_right : Icons.add,
                                    size: 16,
                                    color: Colors.white.withOpacity(0.5),
                                  ),
                                ],
                              ),
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
              // Question mark icon in top right (always visible)
              if (!isLoadingGoals)
                Positioned(
                  top: 0,
                  right: 0,
                  child: GestureDetector(
                    onTap: () {
                      HapticFeedback.lightImpact();
                      MixpanelManager().dailyScoreHelpTapped();
                      _showScoreDetails(context, score, completedTasks, totalTasks);
                    },
                    child: Container(
                      padding: const EdgeInsets.all(2),
                      child: Icon(
                        Icons.help_outline,
                        size: 16,
                        color: Colors.white.withOpacity(0.3),
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
                context.l10n.dailyScoreBreakdown,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 20),
              _buildDetailRow(context.l10n.todaysScore, _formatScore(score), _getStatusColor(score)),
              const SizedBox(height: 12),
              _buildDetailRow(context.l10n.tasksCompleted, '$completed / $total', Colors.white70),
              const SizedBox(height: 12),
              _buildDetailRow(
                context.l10n.completionRate,
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
                      context.l10n.howItWorks,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: Colors.white.withOpacity(0.8),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      context.l10n.dailyScoreExplanation,
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
                  child: Text(
                    context.l10n.gotIt,
                    style: const TextStyle(
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
  bool shouldRepaint(_SemicircleGaugePainter old) => old.score != score || old.color != color;
}
