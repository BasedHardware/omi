import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart' hide getActionItems;
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api/action_items.dart';

class ScoreWidget extends StatefulWidget {
  const ScoreWidget({super.key});

  @override
  State<ScoreWidget> createState() => _ScoreWidgetState();
}

class _ScoreWidgetState extends State<ScoreWidget> {
  Map<String, dynamic>? _scoreData;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _calculateScore();
  }

  double _clamp(double a, double b, double x) {
    return math.min(b, math.max(a, x));
  }

  Future<void> _calculateScore() async {
    setState(() => _isLoading = true);

    try {
      final now = DateTime.now().toUtc();
      final yesterday = now.subtract(const Duration(hours: 24));

      // Fetch memories from last 24h
      final allMemories = await getMemories(limit: 100, offset: 0);
      final recentMemories = allMemories.where((m) {
        final createdAt = m.createdAt.toUtc();
        return createdAt.isAfter(yesterday);
      }).toList();

      // Fetch conversations from last 24h
      final allConversations = await getConversations(
        limit: 100,
        offset: 0,
        startDate: yesterday,
        endDate: now,
      );

      // Extract tasks from conversations AND standalone action items
      int tasksDone = 0;
      int tasksTotal = 0;

      // Get tasks from conversations
      for (var conv in allConversations) {
        if (conv.structured?.actionItems != null) {
          for (var item in conv.structured!.actionItems) {
            tasksTotal++;
            if (item.completed) {
              tasksDone++;
            }
          }
        }
      }

      // Also get standalone action items from last 24h
      final actionItemsResponse = await getActionItems(
        limit: 100,
        offset: 0,
        startDate: yesterday,
        endDate: now,
      );
      for (var item in actionItemsResponse.actionItems) {
        tasksTotal++;
        if (item.completed ?? false) {
          tasksDone++;
        }
      }

      // Calculate score using the same formula as the plugin
      final L = recentMemories.length;
      final Td = tasksDone;
      final T = tasksTotal;

      final learnScore = 5 * (1 - math.exp(-L / 3));
      
      double execScore;
      // Use neutral baseline when no tasks exist (matches plugin behavior)
      if (T == 0) {
        execScore = 2.5;
      } else {
        final p = Td / T;
        execScore = 5 * _clamp(0, 1, 1.5 * p - 0.5);
      }

      final rawScore = 0.4 * learnScore + 0.6 * execScore;
      final rating = _clamp(0, 5, (rawScore * 2).roundToDouble() / 2);

      setState(() {
        _scoreData = {
          'rating': rating,
          'rawScore': rawScore,
          'learnScore': learnScore,
          'execScore': execScore,
          'memoriesCount': L,
          'tasksDone': Td,
          'tasksTotal': T,
          'tasksMissed': T - Td,
          'completionRate': T > 0 ? (Td / T * 100) : null,
        };
        _isLoading = false;
      });
    } catch (e) {
      debugPrint('Error calculating grade: $e');
      setState(() => _isLoading = false);
    }
  }

  Color _getStatusColor(double rating) {
    if (rating >= 4.5) return const Color(0xFF00D4AA); // Teal/cyan
    if (rating >= 4.0) return const Color(0xFF4CAF50); // Green
    if (rating >= 3.0) return const Color(0xFFFFB74D); // Amber
    if (rating >= 2.0) return const Color(0xFFFF9800); // Orange
    return const Color(0xFFFF6B6B); // Soft red
  }

  String _getAdviceText(double rating, double learnScore, double execScore, int tasksTotal, int memoriesCount) {
    final learningWeak = learnScore < 3.0;
    final executionWeak = execScore < 3.0;
    final noTasks = tasksTotal == 0;

    if (rating >= 4.5) {
      return "Strong execution and continuous learning. This is what peak performance looks like. Keep this rhythm going tomorrow.";
    }
    if (rating >= 4.0) {
      return "You're doing well on both fronts. Small improvements compound over time—see if you can push a little further tomorrow.";
    }
    if (learningWeak && (executionWeak || noTasks)) {
      if (noTasks) {
        return "Set clear goals for tomorrow. Define what you want to accomplish and track your progress.";
      } else {
        return "Time to execute. If there are challenging tasks on your list, today could be the day to tackle them!";
      }
    }
    if (executionWeak || (noTasks && !learningWeak)) {
      if (noTasks) {
        return "Define your goals. Setting clear targets helps drive focus and achievement.";
      } else {
        return "Focus on execution. Complete those tasks you've set for yourself. Small wins create momentum.";
      }
    }
    if (learningWeak) {
      return "Feed your mind. Learning new things helps you grow. Try reading, listening to podcasts, or having deep conversations.";
    }
    return "You're making progress. Stay consistent and push a bit harder tomorrow to reach your potential.";
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        height: 260,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              const Color(0xFF0F172A),
              const Color(0xFF1E293B),
            ],
          ),
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: const Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(
              strokeWidth: 2.5,
              valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF00D4AA)),
            ),
          ),
        ),
      );
    }

    if (_scoreData == null) {
      return const SizedBox.shrink();
    }

    final rating = _scoreData!['rating'] as double;
    final learnScore = _scoreData!['learnScore'] as double;
    final execScore = _scoreData!['execScore'] as double;
    final memoriesCount = _scoreData!['memoriesCount'] as int;
    final tasksDone = _scoreData!['tasksDone'] as int;
    final tasksTotal = _scoreData!['tasksTotal'] as int;

      final statusColor = _getStatusColor(rating);
      final adviceText = _getAdviceText(rating, learnScore, execScore, tasksTotal, memoriesCount);

    // Format rating display (0-5 scale)
    String ratingDisplay = rating.toStringAsFixed(1);
    if (ratingDisplay.endsWith('.0')) {
      ratingDisplay = rating.toInt().toString();
    }

    return GestureDetector(
      onTap: _calculateScore,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              const Color(0xFF0F172A),
              const Color(0xFF1E293B),
              const Color(0xFF0F172A),
            ],
            stops: const [0.0, 0.5, 1.0],
          ),
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: statusColor.withOpacity(0.15),
              blurRadius: 30,
              offset: const Offset(0, 15),
              spreadRadius: 0,
            ),
            BoxShadow(
              color: Colors.black.withOpacity(0.4),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.white.withOpacity(0.05),
                    Colors.white.withOpacity(0.02),
                  ],
                ),
                border: Border.all(
                  color: Colors.white.withOpacity(0.1),
                  width: 1,
                ),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Header
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'OMI GRADE',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 2.5,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                        GestureDetector(
                          onTap: () {
                            showDialog(
                              context: context,
                              builder: (BuildContext context) {
                                return AlertDialog(
                                  backgroundColor: const Color(0xFF1E293B),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                  content: Text(
                                    'OMI grade is calculated based on how many things you learned and accomplished during the last 24 hours',
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: Colors.white,
                                      height: 1.5,
                                    ),
                                  ),
                                  actions: [
                                    TextButton(
                                      onPressed: () => Navigator.of(context).pop(),
                                      child: const Text(
                                        'OK',
                                        style: TextStyle(
                                          color: Color(0xFF00D4AA),
                                        ),
                                      ),
                                    ),
                                  ],
                                );
                              },
                            );
                          },
                          child: Icon(
                            Icons.info_outline,
                            size: 18,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    // Grade display with semi-circular arc
                    Center(
                      child: SizedBox(
                        width: 220,
                        height: 130,
                        child: Stack(
                          children: [
                            // Semi-circular arc background and progress
                            CustomPaint(
                              size: const Size(220, 130),
                              painter: _SemiCircularArcPainter(
                                progress: rating / 5,
                                color: statusColor,
                              ),
                            ),
                            // Grade text - aligned with bottom baseline of arc
                            Positioned(
                              bottom: -10, // Position at the baseline where arc ends
                              left: 0,
                              right: 0,
                              child: Text(
                                ratingDisplay,
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 64,
                                  fontWeight: FontWeight.w200,
                                  color: Colors.white,
                                  height: 1,
                                  letterSpacing: -3,
                                  shadows: [
                                    Shadow(
                                      color: statusColor.withOpacity(0.3),
                                      blurRadius: 20,
                                      offset: const Offset(0, 0),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 28),
                    // Advice text
                    Text(
                      adviceText,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w400,
                        color: Colors.white.withOpacity(0.7),
                        height: 1.5,
                        letterSpacing: 0.2,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    // Metrics row
                    Row(
                      children: [
                      Expanded(
                        child: _buildMetricItem(
                          'LEARNING',
                          memoriesCount.toString(),
                          null, // Don't show score calculation
                          statusColor,
                          goal: 5, // Goal of 5 learnings per day
                        ),
                      ),
                      Container(
                        width: 1,
                        height: 50,
                        margin: const EdgeInsets.symmetric(horizontal: 16),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              Colors.transparent,
                              Colors.white.withOpacity(0.2),
                              Colors.transparent,
                            ],
                          ),
                        ),
                      ),
                      Expanded(
                        child: _buildMetricItem(
                          'EXECUTION',
                          tasksTotal > 0 ? '$tasksDone/$tasksTotal' : '—',
                          null, // Don't show score calculation
                          statusColor,
                        ),
                      ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMetricItem(String label, String value, double? score, Color accentColor, {int? goal}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 9,
            fontWeight: FontWeight.w600,
            letterSpacing: 2,
            color: Colors.white.withOpacity(0.4),
          ),
        ),
        const SizedBox(height: 10),
        // For learning, show as "current/goal", for execution just show the value
        Text(
          label == 'LEARNING' && goal != null ? '$value/$goal' : value,
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w300,
            color: Colors.white,
            height: 1,
            letterSpacing: -1,
          ),
        ),
        const SizedBox(height: 19),
      ],
    );
  }
}

// Custom painter for semi-circular arc (like Oura)
class _SemiCircularArcPainter extends CustomPainter {
  final double progress;
  final Color color;

  _SemiCircularArcPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    // Background arc (subtle)
    final bgPaint = Paint()
      ..color = Colors.white.withOpacity(0.08)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round;

    // Progress arc (with gradient effect)
    final progressPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round;

    final center = Offset(size.width / 2, size.height);
    final radius = size.width / 2 - 20;
    
    // Calculate the y position where the arc ends (bottom of the arc)
    final arcBottomY = size.height;

    // Draw background arc (full semi-circle)
    final backgroundRect = Rect.fromCircle(center: center, radius: radius);
    canvas.drawArc(
      backgroundRect,
      math.pi, // Start from left (180 degrees)
      math.pi, // Draw half circle (180 degrees)
      false,
      bgPaint,
    );

    // Draw progress arc with glow effect
    final progressRect = Rect.fromCircle(center: center, radius: radius);
    
    // Main progress arc
    canvas.drawArc(
      progressRect,
      math.pi, // Start from left (180 degrees)
      math.pi * progress, // Draw based on progress
      false,
      progressPaint,
    );

    // Glow effect (lighter arc behind)
    final glowPaint = Paint()
      ..color = color.withOpacity(0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..strokeCap = StrokeCap.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);

    canvas.drawArc(
      progressRect,
      math.pi,
      math.pi * progress,
      false,
      glowPaint,
    );
  }

  @override
  bool shouldRepaint(_SemiCircularArcPainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.color != color;
  }
}