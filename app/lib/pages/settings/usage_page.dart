import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

class UsagePage extends StatefulWidget {
  const UsagePage({super.key});

  @override
  State<UsagePage> createState() => _UsagePageState();
}

class _UsagePageState extends State<UsagePage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final List<GlobalKey> _screenshotKeys = List.generate(4, (_) => GlobalKey());

  Future<void> _shareUsage() async {
    final RenderRepaintBoundary boundary =
        _screenshotKeys[_tabController.index].currentContext!.findRenderObject() as RenderRepaintBoundary;
    final ui.Image image = await boundary.toImage(pixelRatio: 3.0);

    // Load logo
    final ByteData logoData = await rootBundle.load('assets/images/herologo.png');
    final ui.Codec codec = await ui.instantiateImageCodec(logoData.buffer.asUint8List());
    final ui.FrameInfo fi = await codec.getNextFrame();
    final ui.Image logoImage = fi.image;

    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);

    // Draw the original image
    canvas.drawImage(image, Offset.zero, Paint());

    // Prepare the watermark text
    final textPainter = TextPainter(
      text: TextSpan(
        text: 'omi.me',
        style: TextStyle(
          color: Colors.white.withOpacity(0.8),
          fontSize: 14 * 3.0, // Scale font size with pixelRatio
          fontWeight: FontWeight.w600,
        ),
      ),
      textDirection: ui.TextDirection.ltr,
    );
    textPainter.layout();

    // Define sizes and padding
    final double logoHeight = 20 * 3.0; // Scaled logo height
    final double logoWidth = (logoImage.width / logoImage.height) * logoHeight;
    final double padding = 4 * 3.0;
    final double totalWatermarkWidth = logoWidth + padding + textPainter.width;
    final double totalWatermarkHeight = logoHeight > textPainter.height ? logoHeight : textPainter.height;

    // Position and draw the watermark at the bottom right
    final double xPos = image.width - totalWatermarkWidth - (16 * 3.0);
    final double yPos = image.height - totalWatermarkHeight - (16 * 3.0);

    // Draw logo
    final logoRect = Rect.fromLTWH(xPos, yPos + (totalWatermarkHeight - logoHeight) / 2, logoWidth, logoHeight);
    canvas.drawImageRect(
        logoImage, Rect.fromLTWH(0, 0, logoImage.width.toDouble(), logoImage.height.toDouble()), logoRect, Paint());

    // Draw text
    textPainter.paint(
        canvas, Offset(xPos + logoWidth + padding, yPos + (totalWatermarkHeight - textPainter.height) / 2));

    // Convert the canvas to a new image and then to bytes
    final watermarkedImage = await recorder.endRecording().toImage(image.width, image.height);
    final ByteData? byteData = await watermarkedImage.toByteData(format: ui.ImageByteFormat.png);
    final Uint8List pngBytes = byteData!.buffer.asUint8List();

    final tempDir = await getTemporaryDirectory();
    final file = await File('${tempDir.path}/omi_usage.png').create();
    await file.writeAsBytes(pngBytes);

    final provider = context.read<UsageProvider>();
    final period = _getPeriodForIndex(_tabController.index);
    UsageStats? stats;
    String periodTitle = 'Today';
    switch (period) {
      case 'today':
        stats = provider.todayUsage;
        periodTitle = 'Today';
        break;
      case 'monthly':
        stats = provider.monthlyUsage;
        periodTitle = 'This Month';
        break;
      case 'yearly':
        stats = provider.yearlyUsage;
        periodTitle = 'This Year';
        break;
      case 'all_time':
        stats = provider.allTimeUsage;
        periodTitle = 'All Time';
        break;
    }

    final userName = SharedPreferencesUtil().fullName;
    final numberFormatter = NumberFormat.compact(locale: 'en_US');

    String shareText;
    final baseText =
        '${userName.isNotEmpty ? '$userName has' : 'I have'} a good omi - omi.me - your always-on assistant.';

    if (stats != null) {
      final transcriptionMinutes = (stats.transcriptionSeconds / 60).round();
      final List<String> funStats = [];

      if (transcriptionMinutes > 0) {
        funStats.add('🎧 Listened for ${numberFormatter.format(transcriptionMinutes)} minutes');
      }
      if (stats.wordsTranscribed > 0) {
        funStats.add('🧠 Understood ${numberFormatter.format(stats.wordsTranscribed)} words');
      }
      if (stats.insightsGained > 0) {
        funStats.add('✨ Provided ${numberFormatter.format(stats.insightsGained)} insights');
      }
      if (stats.memoriesCreated > 0) {
        funStats.add('📚 Remembered ${numberFormatter.format(stats.memoriesCreated)} memories');
      }

      if (funStats.isNotEmpty) {
        String periodText;
        switch (periodTitle) {
          case 'Today':
            periodText = 'Today, my Omi has:';
            break;
          case 'This Month':
            periodText = 'This month, my Omi has:';
            break;
          case 'This Year':
            periodText = 'This year, my Omi has:';
            break;
          case 'All Time':
            periodText = 'So far, my Omi has:';
            break;
          default:
            periodText = 'My Omi has:';
        }
        shareText = '$baseText\n\n$periodText\n${funStats.join('\n')}';
      } else {
        shareText = baseText;
      }
    } else {
      shareText = baseText;
    }

    await Share.shareXFiles(
      [XFile(file.path)],
      text: shareText,
    );
  }

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
        actions: [
          IconButton(
            icon: const FaIcon(FontAwesomeIcons.solidShareFromSquare),
            onPressed: _shareUsage,
          ),
        ],
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
              _buildUsageListView(provider.todayUsage, provider.todayHistory, 'today', _screenshotKeys[0]),
              _buildUsageListView(provider.monthlyUsage, provider.monthlyHistory, 'monthly', _screenshotKeys[1]),
              _buildUsageListView(provider.yearlyUsage, provider.yearlyHistory, 'yearly', _screenshotKeys[2]),
              _buildUsageListView(provider.allTimeUsage, provider.allTimeHistory, 'all_time', _screenshotKeys[3]),
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

  Widget _buildUsageListView(UsageStats? stats, List<UsageHistoryPoint>? history, String period, GlobalKey key) {
    final onRefresh = () => context.read<UsageProvider>().fetchUsageStats(period: period);

    if (stats == null) {
      return const Center(child: CircularProgressIndicator(color: Colors.deepPurple));
    }

    if (stats.transcriptionSeconds == 0 &&
        stats.wordsTranscribed == 0 &&
        stats.insightsGained == 0 &&
        stats.memoriesCreated == 0) {
      return RefreshIndicator(
        onRefresh: onRefresh,
        color: Colors.deepPurple,
        child: RepaintBoundary(
          key: key,
          child: Container(
            color: Colors.black,
            child: LayoutBuilder(builder: (context, constraints) {
              return SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                child: SizedBox(
                  height: constraints.maxHeight,
                  child: _buildEmptyState(),
                ),
              );
            }),
          ),
        ),
      );
    }
    final numberFormatter = NumberFormat.compact(locale: 'en_US');
    final transcriptionMinutes = (stats.transcriptionSeconds / 60).round();
    final transcriptionValue = '${numberFormatter.format(transcriptionMinutes)} minutes';

    return RefreshIndicator(
      onRefresh: onRefresh,
      color: Colors.deepPurple,
      child: RepaintBoundary(
        key: key,
        child: Container(
          color: Colors.black,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
            children: [
              if (history != null && history.isNotEmpty) ...[
                _buildChart(history, period),
                const SizedBox(height: 24),
              ],
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.microphone,
                title: 'Listening',
                value: transcriptionValue,
                subtitle: 'Total time Omi has actively listened.',
                color: Colors.blue.shade300,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.comments,
                title: 'Understanding',
                value: '${numberFormatter.format(stats.wordsTranscribed)} words',
                subtitle: 'Words understood from your conversations.',
                color: Colors.green.shade300,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.wandMagicSparkles,
                title: 'Providing',
                value: '${numberFormatter.format(stats.insightsGained)} insights',
                subtitle: 'Action items, and notes automatically captured.',
                color: Colors.orange.shade300,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.brain,
                title: 'Remembering',
                value: '${numberFormatter.format(stats.memoriesCreated)} memories',
                subtitle: 'Facts and details remembered for you.',
                color: Colors.purple.shade300,
              ),
            ],
          ),
        ),
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
      if (point.insightsGained > maxY) maxY = point.insightsGained.toDouble();
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
                    final metricNames = [
                      'Listening (mins)',
                      'Understanding (words)',
                      'Insights Gained',
                      'Memories Created'
                    ];
                    return BarTooltipItem(
                      '${metricNames[rodIndex]}\n',
                      TextStyle(color: metricColors[rodIndex], fontWeight: FontWeight.bold),
                      children: [
                        TextSpan(
                          text: NumberFormat.compact(locale: 'en_US').format(rod.toY.round()),
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
                                toY: data.insightsGained.toDouble(), color: metricColors[2], width: barWidth),
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
        _buildLegendItem(Colors.blue.shade300, 'Listening (mins)'),
        _buildLegendItem(Colors.green.shade300, 'Understanding (words)'),
        _buildLegendItem(Colors.orange.shade300, 'Insights'),
        _buildLegendItem(Colors.purple.shade300, 'Memories'),
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
            Text(
              value,
              style: TextStyle(fontSize: 36, fontWeight: FontWeight.bold, color: color, height: 1.1),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                FaIcon(icon, color: color, size: 16),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                ),
              ],
            ),
            const SizedBox(height: 8),
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
