import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/stats_provider.dart';
import 'package:omi/models/user_stats.dart';

class StatsPage extends StatefulWidget {
  const StatsPage({super.key});

  @override
  State<StatsPage> createState() => _StatsPageState();
}

class _StatsPageState extends State<StatsPage> with SingleTickerProviderStateMixin {
  late AnimationController _fireController;
  late Animation<double> _fireAnimation;

  @override
  void initState() {
    super.initState();
    _fireController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    )..repeat(reverse: true);
    _fireAnimation = Tween<double>(begin: 0.9, end: 1.15).animate(
      CurvedAnimation(parent: _fireController, curve: Curves.easeInOut),
    );

    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<StatsProvider>().loadStats();
    });
  }

  @override
  void dispose() {
    _fireController.dispose();
    super.dispose();
  }

  String _formatNumber(int number) {
    return NumberFormat('#,###').format(number);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        title: const Text('Stats', style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
        elevation: 0,
      ),
      body: Consumer<StatsProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return const Center(
              child: CircularProgressIndicator(color: Colors.deepPurple),
            );
          }

          if (provider.error != null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(provider.error!, style: const TextStyle(color: Colors.white70)),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () => provider.loadStats(),
                    style: ElevatedButton.styleFrom(backgroundColor: Colors.deepPurple),
                    child: const Text('Retry', style: TextStyle(color: Colors.white)),
                  ),
                ],
              ),
            );
          }

          final stats = provider.stats;
          if (stats == null) {
            return const Center(
              child: Text('No stats available', style: TextStyle(color: Colors.white70)),
            );
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildStatCards(stats),
                const SizedBox(height: 24),
                _buildStreakCalendar(stats),
                const SizedBox(height: 16),
                Center(
                  child: Text(
                    'Longest streak: ${stats.longestStreak} days',
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(height: 32),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildStatCards(UserStats stats) {
    return Row(
      children: [
        Expanded(child: _buildStatCard('Words Spoken', _formatNumber(stats.totalWords), Icons.chat_bubble_outline)),
        const SizedBox(width: 8),
        Expanded(child: _buildStatCard('Hours Recorded', '${stats.totalHours.toStringAsFixed(1)}h', Icons.access_time)),
        const SizedBox(width: 8),
        Expanded(child: _buildStreakCard(stats.currentStreak)),
      ],
    );
  }

  Widget _buildStatCard(String label, String value, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          Icon(icon, color: Colors.deepPurple, size: 24),
          const SizedBox(height: 8),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white60, fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildStreakCard(int streak) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          streak > 0
              ? AnimatedBuilder(
                  animation: _fireAnimation,
                  builder: (context, child) {
                    return Transform.scale(
                      scale: _fireAnimation.value,
                      child: const Text('🔥', style: TextStyle(fontSize: 22)),
                    );
                  },
                )
              : const Text('🔥', style: TextStyle(fontSize: 22)),
          const SizedBox(height: 8),
          Text(
            '$streak',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Day Streak',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white60, fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildStreakCalendar(UserStats stats) {
    final today = DateTime.now();
    final activeDaysSet = stats.activeDays.toSet();

    // Build 90 days grid (13 weeks)
    // Start from 89 days ago
    final startDate = today.subtract(const Duration(days: 89));

    // Generate all 90 days
    final days = List.generate(90, (i) => startDate.add(Duration(days: i)));

    // Group by week (columns), each week starts on Monday
    // We'll do a simple grid: 7 rows (Mon-Sun) x N columns
    final firstMonday = startDate.subtract(Duration(days: startDate.weekday - 1));
    final totalDays = today.difference(firstMonday).inDays + 1;
    final totalWeeks = (totalDays / 7).ceil();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Activity',
            style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            'Last 90 days',
            style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 13),
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Day labels
              Column(
                children: ['M', '', 'W', '', 'F', '', 'S'].map((label) {
                  return SizedBox(
                    height: 14,
                    child: Text(
                      label,
                      style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 10),
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(width: 6),
              // Calendar grid
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final cellSize = ((constraints.maxWidth - (totalWeeks - 1) * 2) / totalWeeks).clamp(6.0, 14.0);
                    final gap = 2.0;

                    return SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: List.generate(totalWeeks, (weekIndex) {
                          return Padding(
                            padding: EdgeInsets.only(right: weekIndex < totalWeeks - 1 ? gap : 0),
                            child: Column(
                              children: List.generate(7, (dayIndex) {
                                final date = firstMonday.add(Duration(days: weekIndex * 7 + dayIndex));
                                final dateStr = DateFormat('yyyy-MM-dd').format(date);
                                final isInRange = !date.isBefore(startDate) && !date.isAfter(today);
                                final isActive = activeDaysSet.contains(dateStr);

                                return Padding(
                                  padding: EdgeInsets.only(bottom: dayIndex < 6 ? gap : 0),
                                  child: Container(
                                    width: cellSize,
                                    height: cellSize,
                                    decoration: BoxDecoration(
                                      color: !isInRange
                                          ? Colors.transparent
                                          : isActive
                                              ? Colors.deepPurple
                                              : const Color(0xFF2A2A30),
                                      borderRadius: BorderRadius.circular(3),
                                    ),
                                  ),
                                );
                              }),
                            ),
                          );
                        }),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Legend
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Text('Less', style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 10)),
              const SizedBox(width: 4),
              Container(width: 10, height: 10, decoration: BoxDecoration(color: const Color(0xFF2A2A30), borderRadius: BorderRadius.circular(2))),
              const SizedBox(width: 3),
              Container(width: 10, height: 10, decoration: BoxDecoration(color: Colors.deepPurple, borderRadius: BorderRadius.circular(2))),
              const SizedBox(width: 4),
              Text('More', style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 10)),
            ],
          ),
        ],
      ),
    );
  }
}
