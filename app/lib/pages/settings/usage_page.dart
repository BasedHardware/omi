import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

import 'package:fl_chart/fl_chart.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/utils/share_sheet.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/settings/fair_use_page.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class UsagePage extends StatefulWidget {
  final bool showUpgradeDialog;
  const UsagePage({super.key, this.showUpgradeDialog = false});

  @override
  State<UsagePage> createState() => _UsagePageState();
}

class _UsagePageState extends State<UsagePage> with TickerProviderStateMixin {
  late TabController _tabController;
  final List<GlobalKey> _screenshotKeys = List.generate(4, (_) => GlobalKey());
  final GlobalKey _shareButtonKey = GlobalKey();
  final List<bool> _isMetricVisible = [true, true, true, true];
  late AnimationController _waveController;
  late AnimationController _notesController;
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;
  String selectedPlan = 'yearly'; // 'yearly' or 'monthly'
  Map<String, dynamic>? _fairUseStatus;

  Future<void> _loadFairUseStatus() async {
    try {
      final result = await getFairUseStatus();
      // Reconcile the rate-limit cooldown regardless of widget mount state.
      reconcileSyncRateLimitWithFairUseStatus(result);
      if (mounted && result != null) {
        setState(() => _fairUseStatus = result);
      }
    } catch (_) {
      // Silently ignore — banner simply won't appear
    }
  }

  Future<void> _loadAvailablePlans() async {
    final provider = context.read<UsageProvider>();
    await provider.loadAvailablePlans();
  }

  Future<void> _shareUsage() async {
    // Capture context-dependent values before async gaps
    final l10n = context.l10n;
    final provider = context.read<UsageProvider>();
    final localeName = l10n.localeName;

    final captureContext = _screenshotKeys[_tabController.index].currentContext;
    if (captureContext == null || !mounted) return;
    final RenderRepaintBoundary boundary = captureContext.findRenderObject() as RenderRepaintBoundary;
    final ui.Image image = await boundary.toImage(pixelRatio: 3.0);
    if (!mounted) return;

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
          color: Colors.white.withValues(alpha: 0.8),
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
      logoImage,
      Rect.fromLTWH(0, 0, logoImage.width.toDouble(), logoImage.height.toDouble()),
      logoRect,
      Paint(),
    );

    // Draw text
    textPainter.paint(
      canvas,
      Offset(xPos + logoWidth + padding, yPos + (totalWatermarkHeight - textPainter.height) / 2),
    );

    // Convert the canvas to a new image and then to bytes
    final watermarkedImage = await recorder.endRecording().toImage(image.width, image.height);
    final ByteData? byteData = await watermarkedImage.toByteData(format: ui.ImageByteFormat.png);
    if (byteData == null) {
      if (mounted) OmiFeedback.error(context, l10n.wrappedFailedToShare);
      return;
    }
    final Uint8List pngBytes = byteData.buffer.asUint8List();

    final tempDir = await getTemporaryDirectory();
    final file = await File('${tempDir.path}/omi_usage.png').create();
    await file.writeAsBytes(pngBytes);

    final period = _getPeriodForIndex(_tabController.index);
    UsageStats? stats;
    String periodTitle = l10n.today;
    switch (period) {
      case 'today':
        stats = provider.todayUsage;
        periodTitle = l10n.today;
        break;
      case 'monthly':
        stats = provider.monthlyUsage;
        periodTitle = l10n.thisMonth;
        break;
      case 'yearly':
        stats = provider.yearlyUsage;
        periodTitle = l10n.thisYear;
        break;
      case 'all_time':
        stats = provider.allTimeUsage;
        periodTitle = l10n.allTime;
        break;
    }

    final numberFormatter = NumberFormat.decimalPattern(localeName);

    String shareText;
    final baseText = l10n.shareStatsMessage;

    if (stats != null) {
      final transcriptionMinutes = (stats.transcriptionSeconds / 60).round();
      final List<String> funStats = [];

      if (transcriptionMinutes > 0) {
        funStats.add(l10n.shareStatsListened(numberFormatter.format(transcriptionMinutes)));
      }
      if (stats.wordsTranscribed > 0) {
        funStats.add(l10n.shareStatsWords(numberFormatter.format(stats.wordsTranscribed)));
      }
      if (stats.insightsGained > 0) {
        funStats.add(l10n.shareStatsInsights(numberFormatter.format(stats.insightsGained)));
      }
      if (stats.memoriesCreated > 0) {
        funStats.add(l10n.shareStatsMemories(numberFormatter.format(stats.memoriesCreated)));
      }

      if (funStats.isNotEmpty) {
        String periodText;
        if (periodTitle == l10n.today) {
          periodText = l10n.sharePeriodToday;
        } else if (periodTitle == l10n.thisMonth) {
          periodText = l10n.sharePeriodMonth;
        } else if (periodTitle == l10n.thisYear) {
          periodText = l10n.sharePeriodYear;
        } else if (periodTitle == l10n.allTime) {
          periodText = l10n.sharePeriodAllTime;
        } else {
          periodText = l10n.omiHas;
        }
        shareText = '$baseText\n\n$periodText\n${funStats.join('\n')}';
      } else {
        shareText = baseText;
      }
    } else {
      shareText = baseText;
    }

    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(file.path)],
        subject: periodTitle.isEmpty ? null : periodTitle,
        text: shareText.isEmpty ? null : shareText,
        sharePositionOrigin: shareSheetOrigin(_shareButtonKey),
      ),
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
    _waveController = AnimationController(duration: const Duration(milliseconds: 18000), vsync: this)..repeat();
    _notesController = AnimationController(duration: const Duration(milliseconds: 36000), vsync: this)..repeat();

    _arrowController = AnimationController(duration: const Duration(milliseconds: 600), vsync: this)
      ..repeat(reverse: true);

    _arrowAnimation = Tween<double>(
      begin: 0,
      end: 4,
    ).animate(CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut));

    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<UsageProvider>().fetchUsageStats(period: 'today');
      context.read<UsageProvider>().fetchSubscription();
      _loadAvailablePlans();
      _loadFairUseStatus();
      if (widget.showUpgradeDialog && context.read<UsageProvider>().showSubscriptionUI) {
        _showPlansSheet();
      }
    });
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
      appBar: AppBar(
        leading: const OmiBackButton(),
        // Matches the "Plan & Usage" row that opens this page.
        title: Text(context.l10n.planAndUsage),
        actions: [
          OmiIconButton(
            key: _shareButtonKey,
            icon: const FaIcon(FontAwesomeIcons.solidShareFromSquare, size: 20),
            label: context.l10n.share,
            onPressed: _shareUsage,
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: OmiColors.accent,
          isScrollable: true,
          indicatorWeight: 3,
          labelStyle: OmiType.callout.copyWith(fontWeight: FontWeight.bold),
          unselectedLabelStyle: OmiType.callout,
          tabs: [
            Tab(text: context.l10n.today),
            Tab(text: context.l10n.thisMonth),
            Tab(text: context.l10n.thisYear),
            Tab(text: context.l10n.allTime),
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
            return Column(
              children: [
                _buildFairUseBanner(),
                const Expanded(child: OmiLoadingState()),
              ],
            );
          }

          if (provider.error != null && !hasAnyData) {
            return Column(
              children: [
                _buildFairUseBanner(),
                Expanded(
                  child: OmiErrorState(
                    message: provider.error!,
                    onRetry: () => provider.fetchUsageStats(period: _getPeriodForIndex(_tabController.index)),
                  ),
                ),
              ],
            );
          }

          if (!provider.isLoading && !hasAnyData && provider.error == null) {
            return Column(
              children: [
                _buildFairUseBanner(),
                Expanded(child: _buildEmptyState()),
              ],
            );
          }

          return Column(
            children: [
              _buildSubscriptionInfo(context, provider),
              _buildFairUseBanner(),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildUsageListView(
                      provider.todayUsage,
                      provider.todayHistory,
                      'today',
                      _screenshotKeys[0],
                      provider,
                    ),
                    _buildUsageListView(
                      provider.monthlyUsage,
                      provider.monthlyHistory,
                      'monthly',
                      _screenshotKeys[1],
                      provider,
                    ),
                    _buildUsageListView(
                      provider.yearlyUsage,
                      provider.yearlyHistory,
                      'yearly',
                      _screenshotKeys[2],
                      provider,
                    ),
                    _buildUsageListView(
                      provider.allTimeUsage,
                      provider.allTimeHistory,
                      'all_time',
                      _screenshotKeys[3],
                      provider,
                    ),
                  ],
                ),
              ),
            ],
          );
        },
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

    final isPaid = provider.subscription!.subscription.plan.isPaid;
    // The backend's name for the plan ("Plus", "Operator", …); "Free Plan" for the free tier.
    final planLabel = currentPlanDisplayName(context, provider.subscription);

    return Container(
      margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xl, OmiSpacing.md, 0),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(child: Text(planLabel, style: OmiType.headline)),
              if (isPaid)
                Semantics(
                  button: true,
                  child: InkWell(
                    onTap: _showPlansSheet,
                    borderRadius: OmiRadius.smAll,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(minHeight: 44),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(context.l10n.managePlan,
                              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                          const SizedBox(width: OmiSpacing.xxs),
                          const Icon(Icons.chevron_right, color: OmiColors.textSecondary, size: 20),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
          if (!isPaid) ...[
            const SizedBox(height: OmiSpacing.xxs),
            Text(context.l10n.basicPlanDescription, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.md),
            OmiButton(
              label: context.l10n.upgrade,
              expand: true,
              onPressed: _showPlansSheet,
            ),
          ],
        ],
      ),
    );
  }

  void _showPlansSheet() {
    if (!context.read<UsageProvider>().showSubscriptionUI) {
      return;
    }
    showOmiSheet(
      context: context,
      padding: EdgeInsets.zero,
      builder: (context) => PlansSheet(
        waveController: _waveController,
        notesController: _notesController,
        arrowController: _arrowController,
        arrowAnimation: _arrowAnimation,
      ),
    );
  }

  Widget _buildFairUseBanner() {
    if (_fairUseStatus == null) return const SizedBox.shrink();
    final rawStage = _fairUseStatus!['stage'];
    final stage = rawStage is String ? rawStage : 'none';
    if (stage == 'none') return const SizedBox.shrink();

    Color dotColor;
    String stageLabel;
    switch (stage) {
      case 'warning':
        dotColor = OmiColors.warning;
        stageLabel = context.l10n.fairUseStageWarning;
        break;
      case 'throttle':
        dotColor = Colors.orange.shade400;
        stageLabel = context.l10n.fairUseStageThrottle;
        break;
      case 'restrict':
        dotColor = OmiColors.danger;
        stageLabel = context.l10n.fairUseStageRestrict;
        break;
      default:
        return const SizedBox.shrink();
    }

    return GestureDetector(
      key: const Key('fair_use_banner_tap'),
      onTap: () {
        routeToPage(context, const FairUsePage());
      },
      child: Container(
        margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
        constraints: const BoxConstraints(minHeight: 44),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(color: dotColor.withValues(alpha: 0.08), borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            Container(
              key: const Key('fair_use_dot'),
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                context.l10n.fairUseBannerStatus(stageLabel),
                style: OmiType.footnote.copyWith(color: dotColor, fontWeight: FontWeight.w500),
              ),
            ),
            Icon(Icons.chevron_right, color: dotColor, size: 18),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return OmiEmptyState(
      icon: Icons.insights_outlined,
      title: context.l10n.noActivityYet,
      message: context.l10n.startConversationToSeeInsights,
    );
  }

  Widget _buildUsageListView(
    UsageStats? stats,
    List<UsageHistoryPoint>? history,
    String period,
    GlobalKey key,
    UsageProvider provider,
  ) {
    Future<void> onRefresh() async {
      // Using Future.wait to run both fetches concurrently
      await Future.wait([provider.fetchUsageStats(period: period), provider.fetchSubscription(), _loadFairUseStatus()]);
    }

    if (stats == null) {
      return const OmiLoadingState();
    }

    if (stats.transcriptionSeconds == 0 &&
        stats.wordsTranscribed == 0 &&
        stats.insightsGained == 0 &&
        stats.memoriesCreated == 0) {
      return RefreshIndicator(
        onRefresh: onRefresh,
        child: RepaintBoundary(
          key: key,
          child: Container(
            color: OmiColors.surface0,
            child: LayoutBuilder(
              builder: (context, constraints) {
                return SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  child: SizedBox(height: constraints.maxHeight, child: _buildEmptyState()),
                );
              },
            ),
          ),
        ),
      );
    }
    final numberFormatter = NumberFormat.decimalPattern(context.l10n.localeName);
    final transcriptionMinutes = (stats.transcriptionSeconds / 60).round();
    final transcriptionValue = '${numberFormatter.format(transcriptionMinutes)} ${context.l10n.minutes}';

    return RefreshIndicator(
      onRefresh: onRefresh,
      child: RepaintBoundary(
        key: key,
        child: Container(
          color: OmiColors.surface0,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xl, OmiSpacing.md, OmiSpacing.md),
            children: [
              if (history != null && history.isNotEmpty) ...[_buildChart(history, period), const SizedBox(height: 24)],
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.microphone,
                title: context.l10n.listening,
                value: transcriptionValue,
                subtitle: context.l10n.listeningSubtitle,
                color: Colors.blue.shade300,
                subscription: provider.subscription,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.comments,
                title: context.l10n.understanding,
                value:
                    '${numberFormatter.format(stats.wordsTranscribed)} ${context.l10n.understandingWords}', // Use correct key
                subtitle: context.l10n.understandingSubtitle,
                color: Colors.green.shade300,
                subscription: provider.subscription,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.wandMagicSparkles,
                title: context.l10n.providing,
                value: '${numberFormatter.format(stats.insightsGained)} ${context.l10n.insights}',
                subtitle: context.l10n.providingSubtitle,
                color: Colors.orange.shade300,
                subscription: provider.subscription,
              ),
              const SizedBox(height: 16),
              _buildUsageCard(
                context,
                icon: FontAwesomeIcons.brain,
                title: context.l10n.remembering,
                value: '${numberFormatter.format(stats.memoriesCreated)} ${context.l10n.memories}',
                subtitle: context.l10n.rememberingSubtitle,
                color: _memoriesColor,
                subscription: provider.subscription,
              ),
              if (provider.chatQuotaUnit != null && period == 'monthly') ...[
                const SizedBox(height: 12),
                _buildChatQuotaLine(context, provider),
              ],
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
            speechSeconds: 0,
            wordsTranscribed: 0,
            insightsGained: 0,
            memoriesCreated: 0,
          );
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
            speechSeconds: 0,
            wordsTranscribed: 0,
            insightsGained: 0,
            memoriesCreated: 0,
          );
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
            speechSeconds: 0,
            wordsTranscribed: 0,
            insightsGained: 0,
            memoriesCreated: 0,
          );
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
            speechSeconds: 0,
            wordsTranscribed: 0,
            insightsGained: 0,
            memoriesCreated: 0,
          );
        }).toList();
        break;
      default:
        processedHistory = List.from(history);
    }

    final metricColors = [Colors.blue.shade300, Colors.green.shade300, Colors.orange.shade300, _memoriesColor];

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
        lineBarsData.add(
          LineChartBarData(
            spots: allSpots[i],
            isCurved: true,
            color: metricColors[i],
            barWidth: 3,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                colors: [metricColors[i].withValues(alpha: 0.3), metricColors[i].withValues(alpha: 0.0)],
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
              ),
            ),
          ),
        );
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
        border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.2), width: 1)),
      ),
      lineTouchData: LineTouchData(
        handleBuiltInTouches: true,
        touchTooltipData: LineTouchTooltipData(
          getTooltipColor: (touchedSpot) => OmiColors.surface3,
          getTooltipItems: (List<LineBarSpot> touchedBarSpots) {
            return touchedBarSpots
                .map((barSpot) {
                  final flSpot = barSpot;
                  final metricNames = [
                    context.l10n.listeningMins,
                    context.l10n.understandingWords,
                    context.l10n.insights,
                    context.l10n.memories,
                  ];
                  final originalIndex = metricColors.indexOf(flSpot.bar.color!);
                  if (originalIndex == -1) return null;

                  return LineTooltipItem(
                    '${metricNames[originalIndex]}\n',
                    TextStyle(color: metricColors[originalIndex], fontWeight: FontWeight.bold),
                    children: [
                      TextSpan(
                        text: NumberFormat.compact(locale: context.l10n.localeName).format(flSpot.y),
                        style: OmiType.caption.copyWith(color: OmiColors.textPrimary),
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
                  NumberFormat.compact(locale: context.l10n.localeName).format(value),
                  style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
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
              final locale = OmiDateFormat.of(context).localeName;
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
                    text = DateFormat.j(locale).format(dateTime);
                  } else {
                    return const SizedBox();
                  }
                  break;
                case 'monthly':
                  if (index % 7 == 0) {
                    text = DateFormat.d(locale).format(dateTime);
                  } else {
                    return const SizedBox();
                  }
                  break;
                case 'yearly':
                  text = DateFormat.MMM(locale).format(dateTime);
                  break;
                case 'all_time':
                  text = DateFormat.y(locale).format(dateTime).substring(2);
                  break;
                default:
                  return const SizedBox();
              }

              return SideTitleWidget(
                axisSide: meta.axisSide,
                child: Text(text, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
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
          padding: const EdgeInsets.only(top: OmiSpacing.md, right: OmiSpacing.md),
          decoration: BoxDecoration(
            color: OmiColors.surface1,
            borderRadius: OmiRadius.lgAll,
            border: Border.all(color: OmiColors.border),
          ),
          child: LineChart(lineChartData, duration: const Duration(milliseconds: 250)),
        ),
        const SizedBox(height: 16),
        _buildLegend(),
      ],
    );
  }

  Widget _buildLegend() {
    final legendItems = [
      {'color': Colors.blue.shade300, 'text': context.l10n.listeningMins},
      {'color': Colors.green.shade300, 'text': context.l10n.understandingWords},
      {'color': Colors.orange.shade300, 'text': context.l10n.insights},
      {'color': _memoriesColor, 'text': context.l10n.memories},
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
    return Semantics(
      button: true,
      toggled: isVisible,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.smAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Opacity(
            opacity: isVisible ? 1.0 : 0.5,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(width: 10, height: 10, color: color),
                const SizedBox(width: 6),
                Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildChatQuotaLine(BuildContext context, UsageProvider provider) {
    final sub = provider.subscription;
    if (sub == null) return const SizedBox.shrink();

    final l10n = context.l10n;
    final numberFormatter = NumberFormat.decimalPattern(l10n.localeName);
    final used = sub.chatQuotaUsed;
    final limits = sub.subscription.limits;
    final color = Colors.blue.shade300;

    final String value;
    String? usageText;
    double percentage = 0.0;

    if (sub.chatQuotaUnit == 'cost_usd') {
      value = '\$${used.toStringAsFixed(2)}';
      final limit = limits.chatCostUsdPerMonth;
      if (limit != null && limit > 0) {
        usageText = l10n.chatUsedOfLimitCompute(used.toStringAsFixed(2), limit.toStringAsFixed(0));
        percentage = (used / limit).clamp(0.0, 1.0);
      }
    } else {
      value = '${numberFormatter.format(used.toInt())} ${l10n.chatTitle}';
      final limit = limits.chatQuestionsPerMonth;
      if (limit != null && limit > 0) {
        usageText = l10n.chatUsedOfLimitMessages(numberFormatter.format(used.toInt()), numberFormatter.format(limit));
        percentage = (used / limit).clamp(0.0, 1.0);
      }
    }

    return _UsageStatCard(
      icon: FontAwesomeIcons.solidMessage,
      title: l10n.chatTitle,
      value: value,
      subtitle: l10n.chatQuotaSubtitle,
      color: color,
      footer: usageText != null && percentage > 0
          ? _UsageMeter(text: usageText, percentage: percentage, color: color)
          : null,
    );
  }

  Widget _buildUsageCard(
    BuildContext context, {
    required FaIconData icon,
    required String title,
    required String value,
    required String subtitle,
    required Color color,
    UserSubscriptionResponse? subscription,
  }) {
    final l10n = context.l10n;
    final numberFormatter = NumberFormat.decimalPattern(l10n.localeName);
    final onFreePlan = subscription != null && subscription.subscription.plan == PlanType.basic;
    Widget? footer;

    if (onFreePlan && icon == FontAwesomeIcons.microphone && subscription.transcriptionSecondsLimit > 0) {
      final minutesUsed = (subscription.transcriptionSecondsUsed / 60).round();
      final minutesLimit = (subscription.transcriptionSecondsLimit / 60).round();
      final percentage =
          (subscription.transcriptionSecondsUsed / subscription.transcriptionSecondsLimit).clamp(0.0, 1.0);
      footer = _UsageMeter(
        text: l10n.minsUsedThisMonth(numberFormatter.format(minutesUsed), minutesLimit),
        percentage: percentage,
        color: color,
        hint: percentage >= 1.0
            ? _OnDeviceHint(
                before: '${l10n.premiumMinutesUsed} ',
                link: l10n.setupOnDevice,
                after: ' ${l10n.forUnlimitedFreeTranscription}',
              )
            : percentage >= 0.8
                ? _OnDeviceHint(
                    before: '${l10n.premiumMinsLeft(minutesLimit - minutesUsed)} ',
                    link: l10n.onDevice,
                    after: ' ${l10n.alwaysAvailable}',
                  )
                : null,
      );
    } else if (onFreePlan && icon == FontAwesomeIcons.comments && subscription.wordsTranscribedLimit > 0) {
      final used = subscription.wordsTranscribedUsed;
      final limit = subscription.wordsTranscribedLimit;
      footer = _UsageMeter(
        text: l10n.wordsUsedThisMonth(numberFormatter.format(used), numberFormatter.format(limit)),
        percentage: (used / limit).clamp(0.0, 1.0),
        color: color,
      );
    } else if (onFreePlan && icon == FontAwesomeIcons.wandMagicSparkles && subscription.insightsGainedLimit > 0) {
      final used = subscription.insightsGainedUsed;
      final limit = subscription.insightsGainedLimit;
      footer = _UsageMeter(
        text: l10n.insightsUsedThisMonth(numberFormatter.format(used), numberFormatter.format(limit)),
        percentage: (used / limit).clamp(0.0, 1.0),
        color: color,
      );
    }

    return _UsageStatCard(icon: icon, title: title, value: value, subtitle: subtitle, color: color, footer: footer);
  }
}

/// Series colour for memories; pink keeps the chart off the brand-banned hues (INV-UI-1).
final Color _memoriesColor = Colors.pink.shade200;

/// One metric card: the big number, its name and what it means, and an optional meter.
class _UsageStatCard extends StatelessWidget {
  const _UsageStatCard({
    required this.icon,
    required this.title,
    required this.value,
    required this.subtitle,
    required this.color,
    this.footer,
  });

  final FaIconData icon;
  final String title;
  final String value;
  final String subtitle;
  final Color color;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border),
      ),
      padding: const EdgeInsets.all(OmiSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: OmiType.largeTitle.copyWith(color: color, height: 1.1)),
          const SizedBox(height: OmiSpacing.sm),
          Row(
            children: [
              ExcludeSemantics(child: FaIcon(icon, color: color, size: 16)),
              const SizedBox(width: OmiSpacing.xs),
              Expanded(child: Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500))),
            ],
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4)),
          if (footer != null) ...[const SizedBox(height: OmiSpacing.md), footer!],
        ],
      ),
    );
  }
}

/// "12 of 30 min used this month" with a progress bar, and an optional hint under it.
class _UsageMeter extends StatelessWidget {
  const _UsageMeter({required this.text, required this.percentage, required this.color, this.hint});

  final String text;
  final double percentage;
  final Color color;
  final Widget? hint;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        const SizedBox(height: OmiSpacing.xs),
        LinearProgressIndicator(
          value: percentage,
          backgroundColor: OmiColors.surface3,
          valueColor: AlwaysStoppedAnimation<Color>(color),
          minHeight: 4,
          borderRadius: OmiRadius.pillAll,
        ),
        if (hint != null) ...[const SizedBox(height: OmiSpacing.xs), hint!],
      ],
    );
  }
}

/// A sentence with an underlined link to on-device transcription settings.
class _OnDeviceHint extends StatelessWidget {
  const _OnDeviceHint({required this.before, required this.link, required this.after});

  final String before;
  final String link;
  final String after;

  @override
  Widget build(BuildContext context) {
    final style = OmiType.caption.copyWith(color: OmiColors.textTertiary);
    return Semantics(
      link: true,
      child: InkWell(
        onTap: () => routeToPage(context, const TranscriptionSettingsPage()),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: before, style: style),
                  TextSpan(
                    text: link,
                    style: style.copyWith(color: OmiColors.textSecondary, decoration: TextDecoration.underline),
                  ),
                  TextSpan(text: after, style: style),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
