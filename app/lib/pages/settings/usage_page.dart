import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

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
import 'package:omi/pages/settings/widgets/usage/usage_chart.dart';
import 'package:omi/pages/settings/widgets/usage/usage_stat_tile.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class UsagePage extends StatefulWidget {
  final bool showUpgradeDialog;
  @visibleForTesting
  final bool debugSkipFetch;
  @visibleForTesting
  final DateTime? debugNow;
  @visibleForTesting
  final int? debugTooltipIndex;
  const UsagePage(
      {super.key, this.showUpgradeDialog = false, this.debugSkipFetch = false, this.debugNow, this.debugTooltipIndex});

  @override
  State<UsagePage> createState() => _UsagePageState();
}

class _UsagePageState extends State<UsagePage> with TickerProviderStateMixin {
  late TabController _tabController;
  final List<GlobalKey> _screenshotKeys = List.generate(4, (_) => GlobalKey());
  final GlobalKey _shareButtonKey = GlobalKey();
  UsageMetric _selectedMetric = UsageMetric.words;
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
    if (mounted) setState(() {});
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
      if (widget.debugSkipFetch) return;
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

  Widget _periodSegment(String label) => SizedBox(
        height: 44,
        child: Center(child: Text(label, maxLines: 1, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600))),
      );

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
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(60),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 2, OmiSpacing.md, 8),
            child: SizedBox(
              width: double.infinity,
              child: CupertinoSlidingSegmentedControl<int>(
                groupValue: _tabController.index,
                backgroundColor: OmiColors.surface1,
                thumbColor: OmiColors.surface3,
                onValueChanged: (index) {
                  if (index != null) _tabController.animateTo(index);
                },
                children: {
                  0: _periodSegment(context.l10n.today),
                  1: _periodSegment(context.l10n.usageMonth),
                  2: _periodSegment(context.l10n.usageYear),
                  3: _periodSegment(context.l10n.usageAll),
                },
              ),
            ),
          ),
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

          return TabBarView(
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
      margin: const EdgeInsets.only(bottom: OmiSpacing.sm),
      padding: EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: isPaid ? OmiSpacing.xs : OmiSpacing.md),
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
              Flexible(
                  child: isPaid
                      ? Container(
                          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xxs),
                          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
                          child: Text(planLabel, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w700)),
                        )
                      : Text(planLabel, style: OmiType.headline)),
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
              labelStyle: OmiType.callout.copyWith(fontFamily: 'Roboto', fontWeight: FontWeight.w600),
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
      await Future.wait([provider.fetchUsageStats(period: period), provider.fetchSubscription(), _loadFairUseStatus()]);
    }

    final l10n = context.l10n;
    final format = NumberFormat.decimalPattern(l10n.localeName);
    final zero = stats == null ||
        (stats.transcriptionSeconds == 0 &&
            stats.wordsTranscribed == 0 &&
            stats.insightsGained == 0 &&
            stats.memoriesCreated == 0);
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: RepaintBoundary(
        key: key,
        child: Container(
          color: OmiColors.surface0,
          child: ListView(
            key: Key('usage_scroll_$period'),
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xl),
            children: [
              _buildSubscriptionInfo(context, provider),
              _buildFairUseBanner(),
              if (stats == null)
                const OmiLoadingState()
              else if (zero)
                _buildEmptyState()
              else ...[
                const SizedBox(height: OmiSpacing.xs),
                GridView.count(
                  key: const Key('usage_stat_grid'),
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisCount: 2,
                  childAspectRatio: 1.7,
                  mainAxisSpacing: OmiSpacing.sm,
                  crossAxisSpacing: OmiSpacing.sm,
                  children: [
                    UsageStatTile(
                        label: l10n.usageListened,
                        value: formatUsageDuration(stats.transcriptionSeconds),
                        exactValue: '${format.format((stats.transcriptionSeconds / 60).round())} ${l10n.minutes}',
                        color: Colors.blue.shade300),
                    UsageStatTile(
                        label: l10n.usageWordsHeard,
                        value: formatUsageCount(stats.wordsTranscribed, l10n.localeName),
                        exactValue: format.format(stats.wordsTranscribed),
                        color: Colors.green.shade300),
                    UsageStatTile(
                        label: l10n.usageTasksNotes,
                        value: formatUsageCount(stats.insightsGained, l10n.localeName),
                        exactValue: format.format(stats.insightsGained),
                        color: Colors.orange.shade300),
                    UsageStatTile(
                        label: l10n.memories,
                        value: formatUsageCount(stats.memoriesCreated, l10n.localeName),
                        exactValue: format.format(stats.memoriesCreated),
                        color: _memoriesColor),
                  ],
                ),
                if (history != null && history.isNotEmpty) ...[
                  const SizedBox(height: OmiSpacing.sm),
                  UsageChart(
                      history: history,
                      period: period,
                      metric: _selectedMetric,
                      now: widget.debugNow,
                      debugTooltipIndex: widget.debugTooltipIndex,
                      onMetricChanged: (value) => setState(() => _selectedMetric = value)),
                ],
              ],
              if (stats != null) ..._buildFreeMeters(provider.subscription),
              if (stats != null && provider.chatQuotaUnit != null && period == 'monthly') ...[
                const SizedBox(height: OmiSpacing.sm),
                _buildChatQuotaLine(context, provider),
              ],
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildFreeMeters(UserSubscriptionResponse? subscription) {
    if (subscription == null || subscription.subscription.plan != PlanType.basic) return [];
    final l10n = context.l10n;
    final format = NumberFormat.decimalPattern(l10n.localeName);
    final rows = <Widget>[];
    if (subscription.transcriptionSecondsLimit > 0) {
      final used = (subscription.transcriptionSecondsUsed / 60).round();
      final limit = (subscription.transcriptionSecondsLimit / 60).round();
      final ratio = (subscription.transcriptionSecondsUsed / subscription.transcriptionSecondsLimit).clamp(0.0, 1.0);
      rows.add(_UsageMeter(
          text: l10n.minsUsedThisMonth(format.format(used), limit),
          percentage: ratio,
          color: Colors.blue.shade300,
          hint: ratio >= 1
              ? _OnDeviceHint(
                  before: '${l10n.premiumMinutesUsed} ',
                  link: l10n.setupOnDevice,
                  after: ' ${l10n.forUnlimitedFreeTranscription}')
              : ratio >= .8
                  ? _OnDeviceHint(
                      before: '${l10n.premiumMinsLeft(limit - used)} ',
                      link: l10n.onDevice,
                      after: ' ${l10n.alwaysAvailable}')
                  : null));
    }
    if (subscription.wordsTranscribedLimit > 0) {
      rows.add(_UsageMeter(
          text: l10n.wordsUsedThisMonth(
              format.format(subscription.wordsTranscribedUsed), format.format(subscription.wordsTranscribedLimit)),
          percentage: (subscription.wordsTranscribedUsed / subscription.wordsTranscribedLimit).clamp(0.0, 1.0),
          color: Colors.green.shade300));
    }
    if (subscription.insightsGainedLimit > 0) {
      rows.add(_UsageMeter(
          text: l10n.insightsUsedThisMonth(
              format.format(subscription.insightsGainedUsed), format.format(subscription.insightsGainedLimit)),
          percentage: (subscription.insightsGainedUsed / subscription.insightsGainedLimit).clamp(0.0, 1.0),
          color: Colors.orange.shade300));
    }
    if (rows.isEmpty) return [];
    return [
      const SizedBox(height: OmiSpacing.sm),
      Container(
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
            color: OmiColors.surface1, borderRadius: OmiRadius.lgAll, border: Border.all(color: OmiColors.border)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (var i = 0; i < rows.length; i++) ...[if (i > 0) const SizedBox(height: OmiSpacing.md), rows[i]],
        ]),
      )
    ];
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
    String? displayText;
    double percentage = 0.0;

    if (sub.chatQuotaUnit == 'cost_usd') {
      value = '\$${used.toStringAsFixed(2)}';
      final limit = limits.chatCostUsdPerMonth;
      if (limit != null && limit > 0) {
        usageText = l10n.chatUsedOfLimitCompute(used.toStringAsFixed(2), limit.toStringAsFixed(0));
        displayText = '$value / \$${limit.toStringAsFixed(0)}';
        percentage = (used / limit).clamp(0.0, 1.0);
      }
    } else {
      value = '${numberFormatter.format(used.toInt())} ${l10n.chatTitle}';
      final limit = limits.chatQuestionsPerMonth;
      if (limit != null && limit > 0) {
        usageText = l10n.chatUsedOfLimitMessages(numberFormatter.format(used.toInt()), numberFormatter.format(limit));
        displayText = '${numberFormatter.format(used.toInt())} / ${numberFormatter.format(limit)}';
        percentage = (used / limit).clamp(0.0, 1.0);
      }
    }

    return Semantics(
      label: '${l10n.usageChatThisMonth}, ${usageText ?? value}',
      child: Container(
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
                child: Text(l10n.usageChatThisMonth, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
            Text(displayText ?? value, maxLines: 1, style: OmiType.footnote),
          ]),
          if (usageText != null) ...[
            const SizedBox(height: OmiSpacing.xs),
            LinearProgressIndicator(
              value: percentage,
              backgroundColor: OmiColors.surface3,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 4,
              borderRadius: OmiRadius.pillAll,
            ),
          ],
        ]),
      ),
    );
  }
}

/// Series colour for memories; pink keeps the chart off the brand-banned hues (INV-UI-1).
final Color _memoriesColor = Colors.pink.shade200;

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
