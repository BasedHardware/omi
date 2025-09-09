import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/providers/usage_provider.dart';

import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

class UsagePage extends StatefulWidget {
  final bool showUpgradeDialog;
  const UsagePage({super.key, this.showUpgradeDialog = false});

  @override
  State<UsagePage> createState() => _UsagePageState();
}

class _UsagePageState extends State<UsagePage> with TickerProviderStateMixin {
  late TabController _tabController;
  final List<GlobalKey> _screenshotKeys = List.generate(4, (_) => GlobalKey());
  final List<bool> _isMetricVisible = [true, true, true, true];
  bool _isUpgrading = false;
  bool _isCancelling = false;
  bool _isSubscriptionExpanded = false;
  late AnimationController _waveController;
  late AnimationController _notesController;
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;
  String selectedPlan = 'yearly'; // 'yearly' or 'monthly'

  Future<void> _loadAvailablePlans() async {
    final provider = context.read<UsageProvider>();
    await provider.loadAvailablePlans();
  }

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
    const double logoHeight = 20 * 3.0; // Scaled logo height
    final double logoWidth = (logoImage.width / logoImage.height) * logoHeight;
    const double padding = 4 * 3.0;
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

    final numberFormatter = NumberFormat.decimalPattern('en_US');

    String shareText;
    const baseText = 'Sharing my Omi stats! (omi.me - your always-on AI assistant)';

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
            periodText = 'Today, omi has:';
            break;
          case 'This Month':
            periodText = 'This month, omi has:';
            break;
          case 'This Year':
            periodText = 'This year, omi has:';
            break;
          case 'All Time':
            periodText = 'So far, omi has:';
            break;
          default:
            periodText = 'Omi has:';
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
    _waveController = AnimationController(
      duration: const Duration(milliseconds: 18000),
      vsync: this,
    )..repeat();
    _notesController = AnimationController(
      duration: const Duration(milliseconds: 36000),
      vsync: this,
    )..repeat();

    _arrowController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    _arrowAnimation = Tween<double>(
      begin: 0,
      end: 4,
    ).animate(CurvedAnimation(
      parent: _arrowController,
      curve: Curves.easeInOut,
    ));

    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<UsageProvider>().fetchUsageStats(period: 'today');
      context.read<UsageProvider>().fetchSubscription();
      if (widget.showUpgradeDialog) {
        _showPlansSheet();
      }
    });

    // Load available plans
    _loadAvailablePlans();
  }

  @override
  void dispose() {
    _tabController.removeListener(_handleTabSelection);
    _tabController.dispose();
    _waveController.dispose();
    _notesController.dispose();
    _arrowController.dispose();
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

          return Column(
            children: [
              _buildSubscriptionInfo(context, provider),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildUsageListView(
                        provider.todayUsage, provider.todayHistory, 'today', _screenshotKeys[0], provider),
                    _buildUsageListView(
                        provider.monthlyUsage, provider.monthlyHistory, 'monthly', _screenshotKeys[1], provider),
                    _buildUsageListView(
                        provider.yearlyUsage, provider.yearlyHistory, 'yearly', _screenshotKeys[2], provider),
                    _buildUsageListView(
                        provider.allTimeUsage, provider.allTimeHistory, 'all_time', _screenshotKeys[3], provider),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  IconData _getIconForFeature(String featureText) {
    final text = featureText.toLowerCase();
    if (text.contains('unlimited') || text.contains('infinity')) {
      return FontAwesomeIcons.infinity;
    }
    if (text.contains('ask omi') || text.contains('anything')) {
      return FontAwesomeIcons.solidComments;
    }
    if (text.contains('memory')) {
      return FontAwesomeIcons.brain;
    }
    if (text.contains('share')) {
      return FontAwesomeIcons.solidShareFromSquare;
    }
    return FontAwesomeIcons.check;
  }

  Widget _buildExpandedFeatureItem(String featureText) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2.0),
            child: FaIcon(_getIconForFeature(featureText), color: Colors.deepPurple.shade200, size: 16),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              featureText,
              style: TextStyle(fontSize: 14, color: Colors.grey.shade300, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSubscriptionInfo(BuildContext context, UsageProvider provider) {
    if (provider.isLoading && provider.subscription == null) {
      return const SizedBox.shrink();
    }

    if (provider.subscription?.showSubscriptionUi == false) {
      return const SizedBox.shrink();
    }

    if (provider.subscription == null) {
      return const SizedBox.shrink();
    }

    final isUnlimited = provider.subscription!.subscription.plan == PlanType.unlimited;

    Widget collapsedBody;
    Widget expandedBody;

    if (isUnlimited) {
      final sub = provider.subscription!.subscription;
      final isCancelled = sub.cancelAtPeriodEnd;
      String renewalDate = 'N/A';
      if (sub.currentPeriodEnd != null) {
        final date = DateTime.fromMillisecondsSinceEpoch(sub.currentPeriodEnd! * 1000);
        renewalDate = DateFormat.yMMMd().format(date);
      }
      collapsedBody = Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text('Unlimited Plan', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          FaIcon(_isSubscriptionExpanded ? FontAwesomeIcons.chevronUp : FontAwesomeIcons.chevronDown,
              size: 16, color: Colors.grey),
        ],
      );

      expandedBody = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Unlimited Plan', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ElevatedButton(
                onPressed: _isCancelling || _isUpgrading ? null : _showPlansSheet,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                ),
                child: _isCancelling
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : _isUpgrading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('Manage Plan', style: TextStyle(color: Colors.white)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            isCancelled ? 'Your plan will cancel on $renewalDate.' : 'Your plan renews on $renewalDate.',
            style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
          ),
          if (sub.features.isNotEmpty) ...[
            const SizedBox(height: 16),
            ...sub.features.map((feature) => _buildExpandedFeatureItem(feature)),
          ],
        ],
      );
    } else {
      final sub = provider.subscription!;
      final minutesUsed = (sub.transcriptionSecondsUsed / 60).round();
      final minutesLimit = (sub.transcriptionSecondsLimit / 60).round();
      final percentage = (sub.transcriptionSecondsLimit > 0)
          ? (sub.transcriptionSecondsUsed / sub.transcriptionSecondsLimit).clamp(0.0, 1.0)
          : 0.0;

      collapsedBody = Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Row(
              children: [
                const Text('Basic Plan', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                if (minutesLimit > 0) ...[
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      '${NumberFormat.decimalPattern('en_US').format(minutesUsed)} of $minutesLimit mins used',
                      style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ],
            ),
          ),
          FaIcon(_isSubscriptionExpanded ? FontAwesomeIcons.chevronUp : FontAwesomeIcons.chevronDown,
              size: 16, color: Colors.grey),
        ],
      );

      expandedBody = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Basic Plan', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ElevatedButton(
                onPressed: _isUpgrading ? null : _showPlansSheet,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                ),
                child: _isUpgrading
                    ? const SizedBox(
                        height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Upgrade to Unlimited', style: TextStyle(color: Colors.white)),
              ),
            ],
          ),
          if (minutesLimit > 0) ...[
            const SizedBox(height: 12),
            Text(
              'Your plan includes $minutesLimit free minutes per month. Upgrade to go unlimited.',
              style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
            ),
            const SizedBox(height: 12),
            LinearProgressIndicator(
              value: percentage,
              backgroundColor: Colors.grey.shade700,
              valueColor: const AlwaysStoppedAnimation<Color>(Colors.deepPurple),
              minHeight: 6,
              borderRadius: BorderRadius.circular(3),
            ),
          ],
          if (sub.subscription.features.isNotEmpty) ...[
            const SizedBox(height: 16),
            ...sub.subscription.features.map((feature) => _buildExpandedFeatureItem(feature)),
          ]
        ],
      );
    }

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          setState(() {
            _isSubscriptionExpanded = !_isSubscriptionExpanded;
          });
        },
        borderRadius: BorderRadius.circular(16),
        child: Container(
          margin: const EdgeInsets.fromLTRB(16, 24, 16, 0),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withOpacity(0.1)),
          ),
          child: AnimatedSize(
            duration: const Duration(milliseconds: 300),
            curve: Curves.fastOutSlowIn,
            alignment: Alignment.topCenter,
            child: _isSubscriptionExpanded ? expandedBody : collapsedBody,
          ),
        ),
      ),
    );
  }

  void _showPlansSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      builder: (context) {
        return StatefulBuilder(
          builder: (BuildContext context, StateSetter setModalState) {
            return PlansSheet(waveController: _waveController, notesController: _notesController, arrowController: _arrowController, arrowAnimation: _arrowAnimation);
          },
        );
      },
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

  Widget _buildUsageListView(
      UsageStats? stats, List<UsageHistoryPoint>? history, String period, GlobalKey key, UsageProvider provider) {
    final onRefresh = () async {
      // Using Future.wait to run both fetches concurrently
      await Future.wait([
        provider.fetchUsageStats(period: period),
        provider.fetchSubscription(),
      ]);
    };

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
    final numberFormatter = NumberFormat.decimalPattern('en_US');
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
                subscription: provider.subscription,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.comments,
                title: 'Understanding',
                value: '${numberFormatter.format(stats.wordsTranscribed)} words',
                subtitle: 'Words understood from your conversations.',
                color: Colors.green.shade300,
                subscription: provider.subscription,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.wandMagicSparkles,
                title: 'Providing',
                value: '${numberFormatter.format(stats.insightsGained)} insights',
                subtitle: 'Action items, and notes automatically captured.',
                color: Colors.orange.shade300,
                subscription: provider.subscription,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.brain,
                title: 'Remembering',
                value: '${numberFormatter.format(stats.memoriesCreated)} memories',
                subtitle: 'Facts and details remembered for you.',
                color: Colors.purple.shade300,
                subscription: provider.subscription,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildChart(List<UsageHistoryPoint> history, String period) {
    List<UsageHistoryPoint> processedHistory;
    final now = DateTime.now();

    switch (period) {
      case 'today':
        final hourlyMap = {for (var p in history) DateTime.parse(p.date).toLocal().hour: p};
        processedHistory = List.generate(24, (hour) {
          if (hourlyMap.containsKey(hour)) {
            return hourlyMap[hour]!;
          }
          final date = DateTime(now.year, now.month, now.day, hour);
          return UsageHistoryPoint(
              date: date.toIso8601String(),
              transcriptionSeconds: 0,
              wordsTranscribed: 0,
              insightsGained: 0,
              memoriesCreated: 0);
        });
        break;
      case 'monthly':
        final dailyMap = {for (var p in history) DateTime.parse(p.date).toLocal().day: p};
        final daysInMonth = DateTime(now.year, now.month + 1, 0).day;
        processedHistory = List.generate(daysInMonth, (i) {
          final day = i + 1;
          if (dailyMap.containsKey(day)) {
            return dailyMap[day]!;
          }
          final date = DateTime(now.year, now.month, day);
          return UsageHistoryPoint(
              date: date.toIso8601String(),
              transcriptionSeconds: 0,
              wordsTranscribed: 0,
              insightsGained: 0,
              memoriesCreated: 0);
        });
        break;
      case 'yearly':
        final monthlyMap = {for (var p in history) DateTime.parse(p.date).toLocal().month: p};
        processedHistory = List.generate(12, (i) {
          final month = i + 1;
          if (monthlyMap.containsKey(month)) {
            return monthlyMap[month]!;
          }
          final date = DateTime(now.year, month, 1);
          return UsageHistoryPoint(
              date: date.toIso8601String(),
              transcriptionSeconds: 0,
              wordsTranscribed: 0,
              insightsGained: 0,
              memoriesCreated: 0);
        });
        break;
      case 'all_time':
        final yearlyMap = {for (var p in history) DateTime.parse(p.date).toLocal().year: p};
        var minYear = history.map((p) => DateTime.parse(p.date).toLocal().year).reduce((a, b) => a < b ? a : b);
        var maxYear = history.map((p) => DateTime.parse(p.date).toLocal().year).reduce((a, b) => a > b ? a : b);
        minYear--;
        maxYear++;

        final years = List.generate(maxYear - minYear + 1, (i) => minYear + i);
        processedHistory = years.map((year) {
          if (yearlyMap.containsKey(year)) {
            return yearlyMap[year]!;
          }
          final date = DateTime(year, 1, 1);
          return UsageHistoryPoint(
              date: date.toIso8601String(),
              transcriptionSeconds: 0,
              wordsTranscribed: 0,
              insightsGained: 0,
              memoriesCreated: 0);
        }).toList();
        break;
      default:
        processedHistory = List.from(history);
    }

    final metricColors = [
      Colors.blue.shade300,
      Colors.green.shade300,
      Colors.orange.shade300,
      Colors.purple.shade300,
    ];

    double maxY = 0;
    for (var point in processedHistory) {
      if (_isMetricVisible[0]) {
        final secondsInMinutes = point.transcriptionSeconds / 60.0;
        if (secondsInMinutes > maxY) maxY = secondsInMinutes;
      }
      if (_isMetricVisible[1]) {
        if (point.wordsTranscribed.toDouble() > maxY) maxY = point.wordsTranscribed.toDouble();
      }
      if (_isMetricVisible[2]) {
        if (point.insightsGained.toDouble() > maxY) maxY = point.insightsGained.toDouble();
      }
      if (_isMetricVisible[3]) {
        if (point.memoriesCreated.toDouble() > maxY) maxY = point.memoriesCreated.toDouble();
      }
    }
    maxY = maxY * 1.2;
    if (maxY == 0) maxY = 1;

    final List<List<FlSpot>> allSpots = List.generate(4, (_) => []);
    for (var i = 0; i < processedHistory.length; i++) {
      final point = processedHistory[i];
      allSpots[0].add(FlSpot(i.toDouble(), point.transcriptionSeconds / 60.0));
      allSpots[1].add(FlSpot(i.toDouble(), point.wordsTranscribed.toDouble()));
      allSpots[2].add(FlSpot(i.toDouble(), point.insightsGained.toDouble()));
      allSpots[3].add(FlSpot(i.toDouble(), point.memoriesCreated.toDouble()));
    }

    List<LineChartBarData> lineBarsData = [];
    for (var i = 0; i < allSpots.length; i++) {
      if (_isMetricVisible[i]) {
        lineBarsData.add(LineChartBarData(
          spots: allSpots[i],
          isCurved: true,
          color: metricColors[i],
          barWidth: 3,
          isStrokeCapRound: true,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(
            show: true,
            gradient: LinearGradient(
              colors: [
                metricColors[i].withOpacity(0.3),
                metricColors[i].withOpacity(0.0),
              ],
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
            ),
          ),
        ));
      }
    }

    final lineChartData = LineChartData(
      minX: 0,
      maxX: (processedHistory.length - 1).toDouble(),
      minY: 0,
      maxY: maxY,
      gridData: const FlGridData(show: false),
      borderData: FlBorderData(
        show: true,
        border: Border(
          bottom: BorderSide(color: Colors.white.withOpacity(0.2), width: 1),
        ),
      ),
      lineTouchData: LineTouchData(
        handleBuiltInTouches: true,
        touchTooltipData: LineTouchTooltipData(
          getTooltipColor: (touchedSpot) => Colors.grey.shade800,
          getTooltipItems: (List<LineBarSpot> touchedBarSpots) {
            return touchedBarSpots
                .map((barSpot) {
                  final flSpot = barSpot;
                  final metricNames = ['Listening (mins)', 'Understanding (words)', 'Insights', 'Memories'];
                  final originalIndex = metricColors.indexOf(flSpot.bar.color!);
                  if (originalIndex == -1) return null;

                  return LineTooltipItem(
                    '${metricNames[originalIndex]}\n',
                    TextStyle(
                      color: metricColors[originalIndex],
                      fontWeight: FontWeight.bold,
                    ),
                    children: [
                      TextSpan(
                        text: NumberFormat.compact(locale: 'en_US').format(flSpot.y),
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  );
                })
                .whereType<LineTooltipItem>()
                .toList();
          },
        ),
      ),
      titlesData: FlTitlesData(
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 40,
            interval: maxY > 1 ? ((maxY / 4).roundToDouble() > 0 ? (maxY / 4).roundToDouble() : 1.0) : 0.25,
            getTitlesWidget: (value, meta) {
              if (value == meta.max) return const SizedBox();
              return SideTitleWidget(
                axisSide: meta.axisSide,
                space: 8,
                child: Text(
                  NumberFormat.compact(locale: 'en_US').format(value),
                  style: const TextStyle(color: Colors.grey, fontSize: 10),
                ),
              );
            },
          ),
        ),
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            interval: 1,
            getTitlesWidget: (double value, TitleMeta meta) {
              final index = value.toInt();
              if (index >= processedHistory.length) return const SizedBox();
              final point = processedHistory[index];
              final dateTime = DateTime.parse(point.date).toLocal();
              String text;

              switch (period) {
                case 'today':
                  int interval = 1;
                  if (processedHistory.length > 12) {
                    interval = 4;
                  } else if (processedHistory.length > 6) {
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
      lineBarsData: lineBarsData,
    );

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
          child: LineChart(
            lineChartData,
            duration: const Duration(milliseconds: 250),
          ),
        ),
        const SizedBox(height: 16),
        _buildLegend(),
      ],
    );
  }

  Widget _buildLegend() {
    final legendItems = [
      {'color': Colors.blue.shade300, 'text': 'Listening (mins)'},
      {'color': Colors.green.shade300, 'text': 'Understanding (words)'},
      {'color': Colors.orange.shade300, 'text': 'Insights'},
      {'color': Colors.purple.shade300, 'text': 'Memories'},
    ];

    return Wrap(
      spacing: 16,
      runSpacing: 8,
      alignment: WrapAlignment.center,
      children: List.generate(legendItems.length, (index) {
        return _buildLegendItem(
          legendItems[index]['color'] as Color,
          legendItems[index]['text'] as String,
          _isMetricVisible[index],
          () {
            setState(() {
              _isMetricVisible[index] = !_isMetricVisible[index];
            });
          },
        );
      }),
    );
  }

  Widget _buildLegendItem(Color color, String text, bool isVisible, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Opacity(
        opacity: isVisible ? 1.0 : 0.5,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(width: 10, height: 10, color: color),
            const SizedBox(width: 6),
            Text(text, style: TextStyle(fontSize: 12, color: Colors.grey.shade400)),
          ],
        ),
      ),
    );
  }

  Widget _buildUsageCard(BuildContext context,
      {required IconData icon,
      required String title,
      required String value,
      required String subtitle,
      required Color color,
      UserSubscriptionResponse? subscription}) {
    final numberFormatter = NumberFormat.decimalPattern('en_US');
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [
            Color(0xFF2A2A2E),
            Color(0xFF1F1F25),
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
            if (title == 'Listening' &&
                subscription != null &&
                subscription.subscription.plan == PlanType.basic &&
                subscription.transcriptionSecondsLimit > 0) ...[
              const SizedBox(height: 16),
              Builder(builder: (context) {
                final minutesUsed = (subscription.transcriptionSecondsUsed / 60).round();
                final minutesLimit = (subscription.transcriptionSecondsLimit / 60).round();
                final percentage =
                    (subscription.transcriptionSecondsUsed / subscription.transcriptionSecondsLimit).clamp(0.0, 1.0);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${numberFormatter.format(minutesUsed)} of $minutesLimit min used this month',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade400),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: percentage,
                      backgroundColor: Colors.grey.shade700,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                      minHeight: 4,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ],
                );
              })
            ],
            if (title == 'Understanding' &&
                subscription != null &&
                subscription.subscription.plan == PlanType.basic &&
                subscription.wordsTranscribedLimit > 0) ...[
              const SizedBox(height: 16),
              Builder(builder: (context) {
                final used = subscription.wordsTranscribedUsed;
                final limit = subscription.wordsTranscribedLimit;
                final percentage = (limit > 0) ? (used / limit).clamp(0.0, 1.0) : 0.0;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${numberFormatter.format(used)} of ${numberFormatter.format(limit)} words used this month',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade400),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: percentage,
                      backgroundColor: Colors.grey.shade700,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                      minHeight: 4,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ],
                );
              })
            ],
            if (title == 'Providing' &&
                subscription != null &&
                subscription.subscription.plan == PlanType.basic &&
                subscription.insightsGainedLimit > 0) ...[
              const SizedBox(height: 16),
              Builder(builder: (context) {
                final used = subscription.insightsGainedUsed;
                final limit = subscription.insightsGainedLimit;
                final percentage = (limit > 0) ? (used / limit).clamp(0.0, 1.0) : 0.0;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${numberFormatter.format(used)} of ${numberFormatter.format(limit)} insights gained this month',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade400),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: percentage,
                      backgroundColor: Colors.grey.shade700,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                      minHeight: 4,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ],
                );
              })
            ],
            if (title == 'Remembering' &&
                subscription != null &&
                subscription.subscription.plan == PlanType.basic &&
                subscription.memoriesCreatedLimit > 0) ...[
              const SizedBox(height: 16),
              Builder(builder: (context) {
                final used = subscription.memoriesCreatedUsed;
                final limit = subscription.memoriesCreatedLimit;
                final percentage = (limit > 0) ? (used / limit).clamp(0.0, 1.0) : 0.0;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${numberFormatter.format(used)} of ${numberFormatter.format(limit)} memories created this month',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade400),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: percentage,
                      backgroundColor: Colors.grey.shade700,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                      minHeight: 4,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ],
                );
              })
            ]
          ],
        ),
      ),
    );
  }
}
