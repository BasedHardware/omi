import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'package:intl/intl.dart';

import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/http/api/conversations.dart' hide getActionItems;
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

/// Daily grade record for history tracking
class DailyGrade {
  final DateTime date;
  final double rating;
  final double learnScore;
  final double execScore;
  final int memoriesCount;
  final int tasksDone;
  final int tasksTotal;

  DailyGrade({
    required this.date,
    required this.rating,
    required this.learnScore,
    required this.execScore,
    required this.memoriesCount,
    required this.tasksDone,
    required this.tasksTotal,
  });
}

class ScoreWidget extends StatefulWidget {
  const ScoreWidget({super.key});

  @override
  State<ScoreWidget> createState() => _ScoreWidgetState();
}

class _ScoreWidgetState extends State<ScoreWidget> with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  Map<String, dynamic>? _scoreData;
  bool _isLoading = true;
  bool _isExpanded = false;
  List<DailyGrade> _history = [];
  late AnimationController _animationController;
  late Animation<double> _expandAnimation;

  // Persist expanded state
  static const String _expandedKey = 'scoreWidgetExpanded';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _expandAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    );
    _loadExpandedState();
    _calculateScore();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _animationController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Refresh score when app comes back to foreground
    if (state == AppLifecycleState.resumed) {
      _calculateScore();
    }
  }

  void _loadExpandedState() {
    final prefs = SharedPreferencesUtil();
    _isExpanded = prefs.getBool(_expandedKey);
    if (_isExpanded) {
      _animationController.value = 1.0;
    }
  }

  void _saveExpandedState() {
    SharedPreferencesUtil().saveBool(_expandedKey, _isExpanded);
  }

  void _toggleExpanded() {
    setState(() {
      _isExpanded = !_isExpanded;
      if (_isExpanded) {
        _animationController.forward();
      } else {
        _animationController.reverse();
      }
      _saveExpandedState();
    });
  }

  double _clamp(double a, double b, double x) {
    return math.min(b, math.max(a, x));
  }

  Future<void> _calculateScore() async {
    setState(() => _isLoading = true);

    try {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      final todayEnd = today.add(const Duration(days: 1));
      final sevenDaysAgo = today.subtract(const Duration(days: 6));

      // Fetch all memories
      final allMemories = await getMemories(limit: 500, offset: 0);

      // Fetch conversations from last 7 days
      final allConversations = await getConversations(
        limit: 500,
        offset: 0,
        startDate: sevenDaysAgo.toUtc(),
        endDate: now.toUtc(),
      );

      // Fetch action items created TODAY only
      final todayActionItems = await getActionItems(
        limit: 500,
        offset: 0,
        startDate: today.toUtc(),
        endDate: todayEnd.toUtc(),
      );

      // Count today's tasks from standalone action items
      int todayTasksDone = 0;
      int todayTasksTotal = 0;

      for (var item in todayActionItems.actionItems) {
        todayTasksTotal++;
        if (item.completed) {
          todayTasksDone++;
        }
      }

      // Also count tasks from today's conversations
      for (var conv in allConversations) {
        final convDate = conv.createdAt;
        if (convDate.isAfter(today) && convDate.isBefore(todayEnd)) {
          if (conv.structured?.actionItems != null) {
            for (var item in conv.structured!.actionItems) {
              todayTasksTotal++;
              if (item.completed) {
                todayTasksDone++;
              }
            }
          }
        }
      }

      // Count today's memories
      final todayMemories = allMemories.where((m) {
        final createdAt = m.createdAt;
        return createdAt.isAfter(today) && createdAt.isBefore(todayEnd);
      }).toList();

      // Calculate today's score
      final todayL = todayMemories.length;
      final todayLearnScore = todayL >= 5 ? 5.0 : 5 * (1 - math.exp(-todayL / 3));

      double todayExecScore;
      if (todayTasksTotal == 0) {
        todayExecScore = 2.5; // Neutral when no tasks
      } else {
        final p = todayTasksDone / todayTasksTotal;
        todayExecScore = 5 * _clamp(0, 1, 1.5 * p - 0.5);
      }

      final todayRawScore = 0.4 * todayLearnScore + 0.6 * todayExecScore;
      final todayRating = _clamp(0, 5, (todayRawScore * 2).roundToDouble() / 2);

      // Calculate historical scores for the graph
      _history = [];
      for (int i = 6; i >= 0; i--) {
        final dayStart = today.subtract(Duration(days: i));
        final dayEnd = dayStart.add(const Duration(days: 1));

        // Count memories for this day
        final dayMemories = allMemories.where((m) {
          final createdAt = m.createdAt;
          return createdAt.isAfter(dayStart) && createdAt.isBefore(dayEnd);
        }).toList();

        // Count tasks from conversations for this day
        int tasksDone = 0;
        int tasksTotal = 0;

        for (var conv in allConversations) {
          final convDate = conv.createdAt;
          if (convDate.isAfter(dayStart) && convDate.isBefore(dayEnd)) {
            if (conv.structured?.actionItems != null) {
              for (var item in conv.structured!.actionItems) {
                tasksTotal++;
                if (item.completed) {
                  tasksDone++;
                }
              }
            }
          }
        }

        // For today, also add standalone action items
        if (i == 0) {
          for (var item in todayActionItems.actionItems) {
            tasksTotal++;
            if (item.completed) {
              tasksDone++;
            }
          }
        }

        // Calculate score for this day
        final L = dayMemories.length;
        const learningGoal = 5;
        final learnScore = L >= learningGoal ? 5.0 : 5 * (1 - math.exp(-L / 3));

        double execScore;
        if (tasksTotal == 0) {
          execScore = 2.5;
        } else {
          final p = tasksDone / tasksTotal;
          execScore = 5 * _clamp(0, 1, 1.5 * p - 0.5);
        }

        final rawScore = 0.4 * learnScore + 0.6 * execScore;
        final rating = _clamp(0, 5, (rawScore * 2).roundToDouble() / 2);

        _history.add(DailyGrade(
          date: dayStart,
          rating: rating,
          learnScore: learnScore,
          execScore: execScore,
          memoriesCount: L,
          tasksDone: tasksDone,
          tasksTotal: tasksTotal,
        ));
      }

      setState(() {
        _scoreData = {
          'rating': todayRating,
          'rawScore': todayRawScore,
          'learnScore': todayLearnScore,
          'execScore': todayExecScore,
          'memoriesCount': todayL,
          'tasksDone': todayTasksDone,
          'tasksTotal': todayTasksTotal,
          'tasksMissed': todayTasksTotal - todayTasksDone,
          'completionRate': todayTasksTotal > 0 ? (todayTasksDone / todayTasksTotal * 100) : null,
        };
        _isLoading = false;
      });
    } catch (e) {
      Logger.debug('Error calculating grade: $e');
      setState(() => _isLoading = false);
    }
  }

  Color _getStatusColor(double rating) {
    if (rating >= 4.5) return const Color(0xFF22C55E); // Green
    if (rating >= 4.0) return const Color(0xFF84CC16); // Lime
    if (rating >= 3.0) return const Color(0xFFF59E0B); // Amber
    if (rating >= 2.0) return const Color(0xFFF97316); // Orange
    return const Color(0xFFEF4444); // Red
  }

  String _getStatusLabel(double rating) {
    if (rating >= 4.5) return 'Excellent';
    if (rating >= 4.0) return 'Great';
    if (rating >= 3.0) return 'Good';
    if (rating >= 2.0) return 'Fair';
    return 'Needs Work';
  }

  String _getQuickTip(double rating, double learnScore, double execScore, int tasksTotal) {
    final learningWeak = learnScore < 3.0;
    final executionWeak = execScore < 3.0;
    final noTasks = tasksTotal == 0;

    if (rating >= 4.5) {
      return "Keep up the great work! 🔥";
    }
    if (noTasks && learningWeak) {
      return "Set goals and learn something new today";
    }
    if (noTasks) {
      return "Set clear goals to track your progress";
    }
    if (executionWeak) {
      return "Focus on completing your tasks";
    }
    if (learningWeak) {
      return "Read, listen, or have a deep conversation";
    }
    return "Stay consistent to improve";
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return _buildLoadingState();
    }

    if (_scoreData == null) {
      return const SizedBox.shrink();
    }

    return _buildWidget();
  }

  Widget _buildLoadingState() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: const Color(0xFF35343B),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white38),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Calculating grade...',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: Colors.white70,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWidget() {
    final rating = _scoreData!['rating'] as double;
    final learnScore = _scoreData!['learnScore'] as double;
    final execScore = _scoreData!['execScore'] as double;
    final memoriesCount = _scoreData!['memoriesCount'] as int;
    final tasksDone = _scoreData!['tasksDone'] as int;
    final tasksTotal = _scoreData!['tasksTotal'] as int;

    final statusColor = _getStatusColor(rating);
    final statusLabel = _getStatusLabel(rating);
    final quickTip = _getQuickTip(rating, learnScore, execScore, tasksTotal);

    // Format rating display (0-5 scale)
    String ratingDisplay = rating.toStringAsFixed(1);

    return GestureDetector(
      onTap: _toggleExpanded,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Compact header - always visible
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  // Grade score - clean design, just the number
                  SizedBox(
                    width: 52,
                    height: 52,
                    child: Center(
                      child: Text(
                        ratingDisplay,
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w700,
                          color: statusColor,
                          height: 1,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Info
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              'Today\'s Grade',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: Colors.white.withOpacity(0.6),
                              ),
                            ),
                            const SizedBox(width: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: statusColor.withOpacity(0.2),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                statusLabel,
                                style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w600,
                                  color: statusColor,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          quickTip,
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.white.withOpacity(0.5),
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  // Expand icon
                  AnimatedRotation(
                    turns: _isExpanded ? 0.5 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: Icon(
                      Icons.keyboard_arrow_down_rounded,
                      color: Colors.white.withOpacity(0.4),
                      size: 24,
                    ),
                  ),
                ],
              ),
            ),

            // 7-day graph - ALWAYS visible
            if (_history.isNotEmpty) ...[
              Container(
                height: 1,
                color: const Color(0xFF35343B),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Last 7 Days',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                        if (_history.length >= 2) _buildTrendIndicator(),
                      ],
                    ),
                    const SizedBox(height: 10),
                    _buildHistoryGraph(statusColor),
                  ],
                ),
              ),
            ],

            // Expanded content (details only)
            SizeTransition(
              sizeFactor: _expandAnimation,
              child: Column(
                children: [
                  // Divider
                  Container(
                    height: 1,
                    color: const Color(0xFF35343B),
                  ),

                  // Score breakdown
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Score Breakdown',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: _buildScoreBar(
                                'Learning',
                                learnScore,
                                '$memoriesCount/5 memories',
                                Icons.lightbulb_outline_rounded,
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _buildScoreBar(
                                'Execution',
                                execScore,
                                tasksTotal > 0 ? '$tasksDone/$tasksTotal tasks' : 'No tasks',
                                Icons.check_circle_outline_rounded,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),

                  // How to improve section
                  Container(
                    margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF35343B).withOpacity(0.5),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.tips_and_updates_outlined,
                              size: 14,
                              color: Colors.white.withOpacity(0.5),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'How to improve',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: Colors.white.withOpacity(0.5),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        _buildImprovementTips(learnScore, execScore, tasksTotal, tasksDone),
                      ],
                    ),
                  ),

                  // Info button - larger tap target
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _showInfoDialog(context),
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.info_outline_rounded,
                              size: 14,
                              color: Colors.white.withOpacity(0.4),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'How is this calculated?',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.white.withOpacity(0.4),
                              ),
                            ),
                          ],
                        ),
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
  }

  Widget _buildTrendIndicator() {
    if (_history.length < 2) return const SizedBox.shrink();

    // Get last 3 days average vs previous 3 days
    final sorted = List<DailyGrade>.from(_history)..sort((a, b) => b.date.compareTo(a.date));
    final recent = sorted.take(3).map((e) => e.rating).toList();
    final recentAvg = recent.reduce((a, b) => a + b) / recent.length;

    if (sorted.length > 3) {
      final older = sorted.skip(3).take(3).map((e) => e.rating).toList();
      if (older.isNotEmpty) {
        final olderAvg = older.reduce((a, b) => a + b) / older.length;
        final diff = recentAvg - olderAvg;

        if (diff.abs() >= 0.3) {
          final isUp = diff > 0;
          return Row(
            children: [
              Icon(
                isUp ? Icons.trending_up_rounded : Icons.trending_down_rounded,
                size: 14,
                color: isUp ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
              ),
              const SizedBox(width: 2),
              Text(
                isUp ? '+${diff.toStringAsFixed(1)}' : diff.toStringAsFixed(1),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: isUp ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
                ),
              ),
            ],
          );
        }
      }
    }

    return const SizedBox.shrink();
  }

  Widget _buildHistoryGraph(Color accentColor) {
    // Generate last 7 days
    final now = DateTime.now();
    final days = List.generate(7, (i) {
      return DateTime(now.year, now.month, now.day).subtract(Duration(days: 6 - i));
    });

    // Build data points for the chart
    final dataPoints = <_ChartPoint>[];
    for (int i = 0; i < days.length; i++) {
      final day = days[i];
      final grade = _history.cast<DailyGrade?>().firstWhere(
            (g) => g != null && g.date.year == day.year && g.date.month == day.month && g.date.day == day.day,
            orElse: () => null,
          );
      final isToday = day.day == now.day && day.month == now.month && day.year == now.year;
      dataPoints.add(_ChartPoint(
        index: i,
        rating: grade?.rating,
        isToday: isToday,
        dayLabel: DateFormat('E').format(day).substring(0, 1),
      ));
    }

    return SizedBox(
      height: 80,
      child: CustomPaint(
        painter: _LineChartPainter(
          dataPoints: dataPoints,
          accentColor: accentColor,
          getStatusColor: _getStatusColor,
        ),
        child: Row(
          children: dataPoints.map((point) {
            return Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Text(
                    point.dayLabel,
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: point.isToday ? FontWeight.w600 : FontWeight.w400,
                      color: point.isToday ? Colors.white.withOpacity(0.8) : Colors.white.withOpacity(0.4),
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildScoreBar(
    String label,
    double score,
    String detail,
    IconData icon,
  ) {
    final color = _getStatusColor(score);
    final percentage = score / 5;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              icon,
              size: 14,
              color: Colors.white.withOpacity(0.6),
            ),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: Colors.white.withOpacity(0.8),
              ),
            ),
            const Spacer(),
            Text(
              '${score.toStringAsFixed(1)}/5',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: color,
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        // Progress bar
        Container(
          height: 6,
          decoration: BoxDecoration(
            color: const Color(0xFF35343B),
            borderRadius: BorderRadius.circular(3),
          ),
          child: FractionallySizedBox(
            alignment: Alignment.centerLeft,
            widthFactor: percentage.clamp(0.0, 1.0),
            child: Container(
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          detail,
          style: TextStyle(
            fontSize: 10,
            color: Colors.white.withOpacity(0.4),
          ),
        ),
      ],
    );
  }

  Widget _buildImprovementTips(double learnScore, double execScore, int tasksTotal, int tasksDone) {
    final tips = <String>[];

    if (learnScore < 3.0) {
      tips.add('📚 Learn: Save insights from podcasts, books, or conversations');
    }
    if (tasksTotal == 0) {
      tips.add('🎯 Goals: Add tasks for today or tomorrow to track progress');
    } else if (execScore < 3.0) {
      final pending = tasksTotal - tasksDone;
      tips.add('✅ Execute: Mark your $pending pending task${pending > 1 ? 's' : ''} as done');
    }

    if (tips.isEmpty) {
      tips.add('🔄 Consistency: Keep up your routine to maintain high scores');
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: tips
          .map((tip) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  tip,
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.white.withOpacity(0.7),
                    height: 1.4,
                  ),
                ),
              ))
          .toList(),
    );
  }

  void _showInfoDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1F1F25),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Text(
            'How Grade Works',
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildInfoRow(
                '📚 Learning (40%)',
                'Based on memories saved in the last 24h. Goal: 5 memories/day.',
              ),
              const SizedBox(height: 12),
              _buildInfoRow(
                '✅ Execution (60%)',
                'Based on task completion rate. Complete action items to improve.',
              ),
              const SizedBox(height: 12),
              _buildInfoRow(
                '📊 Scale',
                '0-5 rating. 4.5+ = Excellent, 4+ = Great, 3+ = Good, 2+ = Fair.',
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text(
                'Got it',
                style: TextStyle(
                  color: Color(0xFF22C55E),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildInfoRow(String title, String description) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.white.withOpacity(0.9),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          description,
          style: TextStyle(
            fontSize: 13,
            color: Colors.white.withOpacity(0.6),
            height: 1.4,
          ),
        ),
      ],
    );
  }
}

/// Data point for the line chart
class _ChartPoint {
  final int index;
  final double? rating;
  final bool isToday;
  final String dayLabel;

  _ChartPoint({
    required this.index,
    required this.rating,
    required this.isToday,
    required this.dayLabel,
  });
}

/// Custom painter for connected dot line chart (like Whoop)
class _LineChartPainter extends CustomPainter {
  final List<_ChartPoint> dataPoints;
  final Color accentColor;
  final Color Function(double) getStatusColor;

  _LineChartPainter({
    required this.dataPoints,
    required this.accentColor,
    required this.getStatusColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final chartHeight = size.height - 20; // Leave space for labels at bottom
    final chartWidth = size.width;
    final pointSpacing = chartWidth / (dataPoints.length);

    // Calculate Y position for a rating (0-5 scale)
    double getY(double rating) {
      // Invert Y because canvas Y increases downward
      // Map 0-5 to chartHeight-10 to 10 (with some padding)
      final padding = 12.0;
      final availableHeight = chartHeight - padding * 2;
      return padding + (1 - rating / 5) * availableHeight;
    }

    // Collect valid points for drawing lines
    final validPoints = <Offset>[];
    final validRatings = <double>[];

    for (int i = 0; i < dataPoints.length; i++) {
      final point = dataPoints[i];
      if (point.rating != null) {
        final x = pointSpacing * i + pointSpacing / 2;
        final y = getY(point.rating!);
        validPoints.add(Offset(x, y));
        validRatings.add(point.rating!);
      }
    }

    // Draw connecting lines between valid points
    if (validPoints.length >= 2) {
      final linePaint = Paint()
        ..color = Colors.white.withOpacity(0.3)
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round;

      final path = Path();
      path.moveTo(validPoints[0].dx, validPoints[0].dy);

      for (int i = 1; i < validPoints.length; i++) {
        path.lineTo(validPoints[i].dx, validPoints[i].dy);
      }

      canvas.drawPath(path, linePaint);
    }

    // Draw dots and labels for all points
    for (int i = 0; i < dataPoints.length; i++) {
      final point = dataPoints[i];
      final x = pointSpacing * i + pointSpacing / 2;

      if (point.rating != null) {
        final y = getY(point.rating!);
        final color = point.isToday ? accentColor : getStatusColor(point.rating!);

        // Outer glow for today
        if (point.isToday) {
          final glowPaint = Paint()
            ..color = color.withOpacity(0.3)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6);
          canvas.drawCircle(Offset(x, y), 8, glowPaint);
        }

        // Dot fill
        final dotPaint = Paint()
          ..color = color
          ..style = PaintingStyle.fill;
        canvas.drawCircle(Offset(x, y), point.isToday ? 6 : 5, dotPaint);

        // White border
        final borderPaint = Paint()
          ..color = const Color(0xFF1F1F25)
          ..strokeWidth = 2
          ..style = PaintingStyle.stroke;
        canvas.drawCircle(Offset(x, y), point.isToday ? 6 : 5, borderPaint);

        // Rating label above dot
        final textPainter = TextPainter(
          text: TextSpan(
            text: point.rating!.toStringAsFixed(1),
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: point.isToday ? color : Colors.white.withOpacity(0.6),
            ),
          ),
          textDirection: ui.TextDirection.ltr,
        );
        textPainter.layout();
        textPainter.paint(
          canvas,
          Offset(x - textPainter.width / 2, y - 18),
        );
      } else {
        // Draw empty placeholder dot for days without data
        final emptyPaint = Paint()
          ..color = const Color(0xFF35343B)
          ..style = PaintingStyle.fill;
        canvas.drawCircle(Offset(x, chartHeight / 2), 3, emptyPaint);
      }
    }
  }

  @override
  bool shouldRepaint(_LineChartPainter oldDelegate) {
    return oldDelegate.dataPoints != dataPoints || oldDelegate.accentColor != accentColor;
  }
}
