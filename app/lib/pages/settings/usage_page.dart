import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:provider/provider.dart';

class UsagePage extends StatefulWidget {
  const UsagePage({super.key});

  @override
  State<UsagePage> createState() => _UsagePageState();
}

class _UsagePageState extends State<UsagePage> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  String _getPeriodForIndex(int index) {
    switch (index) {
      case 0:
        return 'today';
      case 1:
        return 'monthly';
      case 2:
        return 'yearly';
      case 3:
        return 'all_time';
      default:
        return 'today';
    }
  }

  void _handleTabSelection() {
    if (_tabController.indexIsChanging) {
      return;
    }
    String period = _getPeriodForIndex(_tabController.index);

    final provider = context.read<UsageProvider>();
    bool shouldFetch = false;
    switch (period) {
      case 'today':
        if (provider.todayUsage == null) shouldFetch = true;
        break;
      case 'monthly':
        if (provider.monthlyUsage == null) shouldFetch = true;
        break;
      case 'yearly':
        if (provider.yearlyUsage == null) shouldFetch = true;
        break;
      case 'all_time':
        if (provider.allTimeUsage == null) shouldFetch = true;
        break;
    }

    if (shouldFetch) {
      provider.fetchUsageStats(period: period);
    }
  }

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _tabController.addListener(_handleTabSelection);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<UsageProvider>().fetchUsageStats(period: 'today');
    });
  }

  @override
  void dispose() {
    _tabController.removeListener(_handleTabSelection);
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        title: const Text('Your Omi Insights'),
        centerTitle: true,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new),
          onPressed: () => Navigator.of(context).pop(),
        ),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: Colors.deepPurple,
          isScrollable: true,
          indicatorWeight: 3,
          labelStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          unselectedLabelStyle: const TextStyle(fontSize: 16),
          tabs: const [
            Tab(text: 'Today'),
            Tab(text: 'This Month'),
            Tab(text: 'This Year'),
            Tab(text: 'All Time'),
          ],
        ),
      ),
      body: Consumer<UsageProvider>(
        builder: (context, provider, child) {
          final hasAnyData = provider.todayUsage != null ||
              provider.monthlyUsage != null ||
              provider.yearlyUsage != null ||
              provider.allTimeUsage != null;

          if (provider.isLoading && !hasAnyData) {
            return const Center(child: CircularProgressIndicator(color: Colors.deepPurple));
          }

          if (provider.error != null && !hasAnyData) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Text(
                  provider.error!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 16),
                ),
              ),
            );
          }

          if (!provider.isLoading && !hasAnyData && provider.error == null) {
            return _buildEmptyState();
          }

          return TabBarView(
            controller: _tabController,
            children: [
              _buildUsageListView(provider.todayUsage, provider.todayHistory, 'today'),
              _buildUsageListView(provider.monthlyUsage, provider.monthlyHistory, 'monthly'),
              _buildUsageListView(provider.yearlyUsage, provider.yearlyHistory, 'yearly'),
              _buildUsageListView(provider.allTimeUsage, provider.allTimeHistory, 'all_time'),
            ],
          );
        },
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const FaIcon(FontAwesomeIcons.kiwiBird, color: Colors.grey, size: 60),
          const SizedBox(height: 20),
          const Text(
            'No Activity Yet',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            'Start a conversation with Omi\nto see your usage insights here.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 16, color: Colors.grey.shade400),
          ),
        ],
      ),
    );
  }

  Widget _buildUsageListView(UsageStats? stats, List<UsageHistoryPoint>? history, String period) {
    final onRefresh = () => context.read<UsageProvider>().fetchUsageStats(period: period);

    if (stats == null) {
      return const Center(child: CircularProgressIndicator(color: Colors.deepPurple));
    }

    if (stats.transcriptionSeconds == 0 &&
        stats.wordsTranscribed == 0 &&
        stats.wordsSummarized == 0 &&
        stats.memoriesCreated == 0) {
      return RefreshIndicator(
        onRefresh: onRefresh,
        color: Colors.deepPurple,
        child: LayoutBuilder(builder: (context, constraints) {
          return SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: SizedBox(
              height: constraints.maxHeight,
              child: _buildEmptyState(),
            ),
          );
        }),
      );
    }
    final numberFormatter = NumberFormat.decimalPattern('en_US');
    final transcriptionMinutes = (stats.transcriptionSeconds / 60);
    String transcriptionValue;
    if (transcriptionMinutes >= 60) {
      transcriptionValue = '${(transcriptionMinutes / 60).toStringAsFixed(1)} hours';
    } else {
      transcriptionValue = '${transcriptionMinutes.round()} minutes';
    }

    return RefreshIndicator(
      onRefresh: onRefresh,
      color: Colors.deepPurple,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
        children: [
          if (history != null && history.isNotEmpty) ...[
            _buildChart(history, period),
            const SizedBox(height: 24),
          ],
          _buildUsageCard(
            context,
            icon: FontAwesomeIcons.earListen,
            title: 'Listening Time',
            value: transcriptionValue,
            subtitle: 'The total time Omi has been actively listening to your world.',
            color: Colors.blue.shade300,
          ),
          const SizedBox(height: 16),
          _buildUsageCard(
            context,
            icon: FontAwesomeIcons.fileWord,
            title: 'Words Captured',
            value: numberFormatter.format(stats.wordsTranscribed),
            subtitle: 'The number of words Omi has transcribed from your conversations.',
            color: Colors.green.shade300,
          ),
          const SizedBox(height: 16),
          _buildUsageCard(
            context,
            icon: FontAwesomeIcons.lightbulb,
            title: 'Insights Gained',
            value: numberFormatter.format(stats.wordsSummarized),
            subtitle: 'Words in summaries, action items, and other insights generated for you.',
            color: Colors.orange.shade300,
          ),
          const SizedBox(height: 16),
          _buildUsageCard(
            context,
            icon: FontAwesomeIcons.brain,
            title: 'Memories Created',
            value: numberFormatter.format(stats.memoriesCreated),
            subtitle: 'Important facts, events, and ideas Omi has remembered for you.',
            color: Colors.purple.shade300,
          ),
        ],
      ),
    );
  }

  Widget _buildChart(List<UsageHistoryPoint> history, String period) {
    const barWidth = 4.0;
    final metricColors = [
      Colors.blue.shade300,
      Colors.green.shade300,
      Colors.orange.shade300,
      Colors.purple.shade300,
    ];

    double maxY = 0;
    for (var point in history) {
      final secondsInMinutes = point.transcriptionSeconds / 60.0;
      if (secondsInMinutes > maxY) maxY = secondsInMinutes;
      if (point.wordsTranscribed > maxY) maxY = point.wordsTranscribed.toDouble();
      if (point.wordsSummarized > maxY) maxY = point.wordsSummarized.toDouble();
      if (point.memoriesCreated > maxY) maxY = point.memoriesCreated.toDouble();
    }
    maxY = maxY * 1.2;
    if (maxY == 0) maxY = 1;

    return Column(
      children: [
        Container(
          height: 200,
          padding: const EdgeInsets.only(top: 16, right: 16),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withOpacity(0.1)),
          ),
          child: BarChart(
            BarChartData(
              alignment: BarChartAlignment.spaceAround,
              maxY: maxY,
              barTouchData: BarTouchData(
                touchTooltipData: BarTouchTooltipData(
                  getTooltipColor: (_) => Colors.grey.shade800,
                  getTooltipItem: (group, groupIndex, rod, rodIndex) {
                    final metricNames = ['Mins Listened', 'Words Captured', 'Insights Gained', 'Memories Created'];
                    return BarTooltipItem(
                      '${metricNames[rodIndex]}\n',
                      TextStyle(color: metricColors[rodIndex], fontWeight: FontWeight.bold),
                      children: [
                        TextSpan(
                          text: NumberFormat.decimalPattern('en_US').format(rod.toY.round()),
                          style: const TextStyle(color: Colors.white, fontSize: 12),
                        ),
                      ],
                    );
                  },
                ),
              ),
              titlesData: FlTitlesData(
                leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    getTitlesWidget: (double value, TitleMeta meta) {
                      final index = value.toInt();
                      if (index >= history.length) return const SizedBox();
                      final point = history[index];
                      final dateTime = DateTime.parse(point.date).toLocal();
                      String text;

                      switch (period) {
                        case 'today':
                          int interval = 1;
                          if (history.length > 12) {
                            interval = 4;
                          } else if (history.length > 6) {
                            interval = 2;
                          }
                          if (index % interval == 0) {
                            text = DateFormat.Hm().format(dateTime);
                          } else {
                            return const SizedBox();
                          }
                          break;
                        case 'monthly':
                          if (index % 7 == 0) {
                            text = DateFormat('d').format(dateTime);
                          } else {
                            return const SizedBox();
                          }
                          break;
                        case 'yearly':
                          text = DateFormat('MMM').format(dateTime);
                          break;
                        case 'all_time':
                          text = DateFormat.y().format(dateTime).substring(2);
                          break;
                        default:
                          return const SizedBox();
                      }

                      return SideTitleWidget(
                        axisSide: meta.axisSide,
                        child: Text(text, style: const TextStyle(color: Colors.grey, fontSize: 10)),
                      );
                    },
                    reservedSize: 20,
                  ),
                ),
              ),
              borderData: FlBorderData(show: false),
              gridData: const FlGridData(show: false),
              barGroups: history
                  .asMap()
                  .map((index, data) => MapEntry(
                        index,
                        BarChartGroupData(
                          x: index,
                          barRods: [
                            BarChartRodData(
                                toY: data.transcriptionSeconds / 60.0, color: metricColors[0], width: barWidth),
                            BarChartRodData(
                                toY: data.wordsTranscribed.toDouble(), color: metricColors[1], width: barWidth),
                            BarChartRodData(
                                toY: data.wordsSummarized.toDouble(), color: metricColors[2], width: barWidth),
                            BarChartRodData(
                                toY: data.memoriesCreated.toDouble(), color: metricColors[3], width: barWidth),
                          ],
                        ),
                      ))
                  .values
                  .toList(),
            ),
          ),
        ),
        const SizedBox(height: 16),
        _buildLegend(),
      ],
    );
  }

  Widget _buildLegend() {
    return Wrap(
      spacing: 16,
      runSpacing: 8,
      alignment: WrapAlignment.center,
      children: [
        _buildLegendItem(Colors.blue.shade300, 'Listening Time'),
        _buildLegendItem(Colors.green.shade300, 'Words Captured'),
        _buildLegendItem(Colors.orange.shade300, 'Insights Gained'),
        _buildLegendItem(Colors.purple.shade300, 'Memories Created'),
      ],
    );
  }

  Widget _buildLegendItem(Color color, String text) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 10, color: color),
        const SizedBox(width: 6),
        Text(text, style: TextStyle(fontSize: 12, color: Colors.grey.shade400)),
      ],
    );
  }

  Widget _buildUsageCard(BuildContext context,
      {required IconData icon,
      required String title,
      required String value,
      required String subtitle,
      required Color color}) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            const Color(0xFF2A2A2E),
            const Color(0xFF1F1F25),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.1)),
        boxShadow: [
          BoxShadow(
            color: color.withOpacity(0.1),
            blurRadius: 10,
            spreadRadius: 1,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                FaIcon(icon, color: color, size: 22),
                const SizedBox(width: 12),
                Text(
                  title,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              value,
              style: TextStyle(fontSize: 36, fontWeight: FontWeight.bold, color: color, height: 1.1),
            ),
            const SizedBox(height: 12),
            Text(
              subtitle,
              style: TextStyle(fontSize: 14, color: Colors.grey.shade400, height: 1.4),
            ),
          ],
        ),
      ),
    );
  }
}
