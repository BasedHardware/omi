import 'package:omi/services/app_review_service.dart';
import 'package:omi/widgets/app_review_prompt.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/conversations.dart' as conversations_api;
import 'package:omi/backend/http/api/users.dart'
    show deleteDailySummary, getDailySummary, regenerateDailySummary, setDailySummaryVisibility;
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/utils/daily_summary_journey.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/utils/share_sheet.dart';
import 'package:omi/widgets/components/memory_review_card.dart';
import 'package:omi/widgets/omi_map_preview.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';

class DailySummaryDetailPage extends StatefulWidget {
  final String summaryId;
  final DailySummary? summary; // Can pass directly if already loaded

  /// The recaps around this one, newest first (the list it was opened from). Rev 3 Recap: arrows at
  /// the end step to the day before and the day after without leaving the page.
  final List<DailySummary> days;

  const DailySummaryDetailPage({super.key, required this.summaryId, this.summary, this.days = const []});

  @override
  State<DailySummaryDetailPage> createState() => _DailySummaryDetailPageState();
}

class _DailySummaryDetailPageState extends State<DailySummaryDetailPage> with SingleTickerProviderStateMixin {
  DailySummary? _summary;
  bool _isLoading = true;
  bool _isSharing = false;
  bool _isDeleting = false;
  bool _isRegenerating = false;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(duration: const Duration(milliseconds: 800), vsync: this);
    _fadeAnimation = CurvedAnimation(parent: _animationController, curve: Curves.easeOut);
    _loadSummary();
  }

  @override
  void dispose() {
    _animationController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  /// Shows [day] in place of the current recap, from the top.
  void _showDay(DailySummary day, {String source = 'day_arrow'}) {
    OmiHaptics.selection();
    setState(() => _summary = day);
    if (_scrollController.hasClients) _scrollController.jumpTo(0);
    _animationController
      ..reset()
      ..forward();
    PlatformManager.instance.analytics.dailySummaryDetailViewed(summaryId: day.id, date: day.date, source: source);
  }

  /// The recap one day older ([step] 1) or newer (-1) than the one shown, from [DailySummaryDetailPage.days].
  DailySummary? _neighbour(int step) {
    final days = widget.days;
    final i = days.indexWhere((d) => d.id == _summary?.id);
    if (i < 0) return null;
    final j = i + step;
    return j >= 0 && j < days.length ? days[j] : null;
  }

  /// A sideways swipe turns the day like the arrows do: towards the older day's arrow shows it.
  void _onSwipe(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    if (velocity.abs() < 300) return;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final day = _neighbour((velocity > 0) != rtl ? 1 : -1);
    if (day != null) _showDay(day, source: 'day_swipe');
  }

  Future<void> _loadSummary() async {
    if (widget.summary != null) {
      setState(() {
        _summary = widget.summary;
        _isLoading = false;
      });
      _animationController.forward();
      // Track page view
      PlatformManager.instance.analytics.dailySummaryDetailViewed(
        summaryId: widget.summaryId,
        date: widget.summary!.date,
        source: 'direct',
      );
      return;
    }

    final summary = await getDailySummary(widget.summaryId);
    if (mounted) {
      setState(() {
        _summary = summary;
        _isLoading = false;
      });
      _animationController.forward();
      // Track page view
      if (summary != null) {
        PlatformManager.instance.analytics.dailySummaryDetailViewed(
          summaryId: widget.summaryId,
          date: summary.date,
          source: 'api_fetch',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      body: _isLoading
          ? const OmiLoadingState()
          : _summary == null
              ? _buildNotFound()
              : _buildContent(),
    );
  }

  Future<void> _shareSummary() async {
    final summary = _summary;
    if (summary == null || _isSharing) return;
    setState(() => _isSharing = true);
    try {
      final shared = await setDailySummaryVisibility(widget.summaryId);
      if (!shared) {
        if (mounted) OmiFeedback.error(context, context.l10n.failedToShareRecap);
        return;
      }
      PlatformManager.instance.analytics.dailySummaryShared(summaryId: widget.summaryId, date: summary.date);
      final url = recapShareUrl(widget.summaryId);
      await SharePlus.instance.share(
        ShareParams(uri: Uri.parse(url), subject: summary.headline, sharePositionOrigin: shareSheetOrigin()),
      );
    } finally {
      if (mounted) setState(() => _isSharing = false);
    }
  }

  Future<void> _openConversation(String? conversationId) async {
    if (conversationId == null || conversationId.isEmpty) return;

    // Track conversation click
    if (_summary != null) {
      PlatformManager.instance.analytics.dailySummaryConversationClicked(
        summaryId: widget.summaryId,
        conversationId: conversationId,
        source: 'daily_summary_detail',
      );
    }

    // Show loading indicator
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
    );

    try {
      final conversation = await conversations_api.getConversationById(conversationId);
      if (!mounted) return;
      Navigator.pop(context); // Dismiss loading

      if (conversation != null) {
        routeToPage(context, ConversationDetailPage(conversation: conversation));
      }
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context); // Dismiss loading
      OmiFeedback.error(context, context.l10n.somethingWentWrong);
    }
  }

  /// Pops the page with ``{deleted: true, summaryId}`` so the caller list
  /// can optimistically remove the card without re-fetching.
  Future<void> _deleteRecap() async {
    if (_isDeleting) return;
    setState(() => _isDeleting = true);

    final success = await deleteDailySummary(widget.summaryId);
    if (!mounted) return;

    final summary = _summary;
    const analyticsSource = 'daily_summary_detail';
    if (success) {
      PlatformManager.instance.analytics.dailySummaryDeleted(
        summaryId: widget.summaryId,
        date: summary?.date ?? '',
        source: analyticsSource,
      );
      OmiFeedback.confirm(context, context.l10n.recapDeletedSnackbar);
      Navigator.pop(context, {'deleted': true, 'summaryId': widget.summaryId});
    } else {
      PlatformManager.instance.analytics.dailySummaryDeleteFailed(
        summaryId: widget.summaryId,
        date: summary?.date ?? '',
        source: analyticsSource,
      );
      setState(() => _isDeleting = false);
      OmiFeedback.error(context, context.l10n.recapDeleteFailed);
    }
  }

  /// Bottom sheet menu opened by the SliverAppBar's 3-dot icon.
  Future<void> _showActionsSheet() async {
    if (_summary == null) return;
    await showOmiSheet<void>(
      context: context,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
      builder: (sheetCtx) => OmiSettingsGroup(
        children: [
          OmiSettingsRow(
            leading: const Icon(Icons.refresh),
            title: context.l10n.regenerateRecap,
            showChevron: false,
            onTap: () {
              Navigator.pop(sheetCtx);
              _regenerateRecap();
            },
          ),
          OmiSettingsRow(
            leading: const Icon(Icons.delete_outline),
            title: context.l10n.deleteRecap,
            isDestructive: true,
            showChevron: false,
            onTap: () {
              Navigator.pop(sheetCtx);
              _confirmDelete();
            },
          ),
        ],
      ),
    );
  }

  /// Re-runs LLM generation server-side and overwrites the same doc in place.
  /// Shows a blocking spinner because the call can take several seconds and
  /// the user is staring at stale content until it returns.
  Future<void> _regenerateRecap() async {
    if (_isRegenerating || _summary == null) return;
    setState(() => _isRegenerating = true);

    // Capture the navigator BEFORE the await so we can dismiss the spinner
    // unconditionally — even if the widget unmounts mid-flight (route
    // popped from outside, OS kills the activity), the navigator is still
    // alive and pop() works without needing a valid widget context.
    final rootNavigator = Navigator.of(context, rootNavigator: true);

    // Fullscreen blocking spinner — barrierDismissible=false so the user
    // can't half-cancel and get into a torn state.
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
    );

    final result = await regenerateDailySummary(widget.summaryId);

    // Dismiss spinner first, then bail if widget is gone. Order matters:
    // mounted check before pop would orphan the dialog on dispose.
    if (rootNavigator.canPop()) {
      rootNavigator.pop();
    }
    if (!mounted) return;

    if (result.success && result.summary != null) {
      setState(() {
        _summary = result.summary;
        _isRegenerating = false;
      });
      OmiFeedback.confirm(context, context.l10n.recapRegeneratedSnackbar);
    } else {
      setState(() => _isRegenerating = false);
      final message = result.statusCode == 429
          ? (result.errorDetail ?? context.l10n.recapRegenerateCooldown)
          : result.statusCode == 400
              ? (result.errorDetail ?? context.l10n.recapRegenerateNoConversations)
              : context.l10n.recapRegenerateFailed;
      OmiFeedback.error(context, message);
    }
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showDeleteRecapConfirmDialog(context);
    if (confirmed == true) {
      await _deleteRecap();
    }
  }

  Widget _buildNotFound() {
    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const OmiBackButton(),
          Expanded(
            child: OmiEmptyState(
              icon: Icons.inbox_outlined,
              title: context.l10n.summaryNotFound,
              action: OmiButton.secondary(
                label: context.l10n.goBack,
                size: OmiButtonSize.compact,
                onPressed: () => Navigator.pop(context),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    final summary = _summary!;
    return AppReviewPrompt(
      contentId: summary.id,
      moment: AppReviewMoment.dailySummaryRead,
      enabled: !_isLoading && !_isSharing && !_isDeleting && !_isRegenerating && summary.overview.trim().isNotEmpty,
      child: FadeTransition(
        opacity: _fadeAnimation,
        // Swipe between days (#5057); vertical scrolling and the page's own controls are unaffected.
        child: GestureDetector(
          key: const Key('recap_day_swipe'),
          behavior: HitTestBehavior.translucent,
          onHorizontalDragEnd: widget.days.length > 1 ? _onSwipe : null,
          child: CustomScrollView(
            controller: _scrollController,
            slivers: [
              _buildHeader(summary),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(OmiSize.screenMargin, OmiSpacing.xs, OmiSize.screenMargin, 100),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    _buildTitleBlock(summary),
                    const SizedBox(height: OmiSpacing.md),
                    _buildOverviewCard(summary),
                    const SizedBox(height: 24),
                    _buildStatsRow(summary),
                    if (summary.highlights.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildHighlightsSection(summary)
                    ],
                    if (summary.actionItems.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildActionItemsSection(summary)
                    ],
                    if (summary.unresolvedQuestions.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildUnresolvedQuestionsSection(summary),
                    ],
                    if (summary.decisionsMade.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildDecisionsMadeSection(summary),
                    ],
                    if (summary.memoriesLearned.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildMemoriesLearnedSection(summary),
                    ],
                    if (summary.knowledgeNuggets.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildKnowledgeNuggetsSection(summary),
                    ],
                    if (summary.locations.isNotEmpty) ...[const SizedBox(height: 32), _buildLocationsMap(summary)],
                    _buildDayArrows(summary),
                    _buildAllRecapsLink(),
                  ]),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// v2 Recap: a plain toolbar (circled back, share, more); the date and serif headline sit in
  /// the page under it.
  Widget _buildHeader(DailySummary summary) {
    return SliverAppBar(
      pinned: true,
      backgroundColor: OmiColors.surface0,
      surfaceTintColor: Colors.transparent,
      leading: const Center(child: OmiBackButton()),
      actions: [
        OmiIconButton.filled(
          icon: _isSharing ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.ios_share_rounded),
          label: context.l10n.share,
          onPressed: _isSharing ? null : _shareSummary,
        ),
        OmiIconButton.filled(
          icon: _isDeleting ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.more_horiz),
          label: context.l10n.moreOptions,
          onPressed: _isDeleting ? null : _showActionsSheet,
        ),
        const SizedBox(width: OmiSpacing.xs),
      ],
    );
  }

  Widget _buildTitleBlock(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          summary.formattedDate,
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: OmiSpacing.xs),
        Semantics(header: true, child: Text(summary.headline, style: OmiType.serifTitle)),
      ],
    );
  }

  Widget _buildOverviewCard(DailySummary summary) {
    return Text(summary.overview, style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.45));
  }

  Widget _buildStatsRow(DailySummary summary) {
    final items = <Widget>[
      _buildStatItem(FontAwesomeIcons.message, '${summary.stats.totalConversations}'),
      _buildStatItem(FontAwesomeIcons.clock, summary.stats.formattedDuration),
      _buildStatItem(FontAwesomeIcons.circleCheck, '${summary.stats.actionItemsCount}'),
    ];
    if ((summary.stats.watchingMinutes ?? 0) > 0) {
      items.add(_buildStatItem(FontAwesomeIcons.eye, summary.stats.formattedWatchingDuration!));
    }
    if ((summary.stats.proactiveMoments ?? 0) > 0) {
      items.add(_buildStatItem(FontAwesomeIcons.bell, '${summary.stats.proactiveMoments}'));
    }
    // v2: the stats share one card, split by hairlines.
    return Container(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.rowAll),
      child: IntrinsicHeight(
        child: Row(
          children: [
            for (var i = 0; i < items.length; i++) ...[
              if (i > 0) VerticalDivider(width: 0.5, thickness: 0.5, color: OmiColors.border),
              Expanded(child: items[i]),
            ],
          ],
        ),
      ),
    );
  }

  /// One stat: the number large, its icon (the stat's name) under it.
  Widget _buildStatItem(FaIconData icon, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm, horizontal: OmiSpacing.xs),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(value, style: OmiType.title3.copyWith(fontWeight: FontWeight.w700), maxLines: 1),
          const SizedBox(height: 4),
          ExcludeSemantics(child: FaIcon(icon, color: OmiColors.textTertiary, size: 13)),
        ],
      ),
    );
  }

  // Format time from "17:00" to "5PM" format
  String _formatTimeTo12Hour(String? timeStr) {
    if (timeStr == null || timeStr.isEmpty) return '';
    final parts = timeStr.split(':');
    if (parts.length != 2) return timeStr;
    final hours = int.tryParse(parts[0]) ?? 0;
    final minutes = int.tryParse(parts[1]) ?? 0;
    final period = hours >= 12 ? 'PM' : 'AM';
    final hour12 = hours == 0 ? 12 : (hours > 12 ? hours - 12 : hours);
    if (minutes == 0) {
      return '$hour12$period';
    } else {
      return '$hour12:${minutes.toString().padLeft(2, '0')}$period';
    }
  }

  Widget _buildLocationsMap(DailySummary summary) {
    final timelineLocations = buildTimelineLocations(summary.locations, unknownLabel: context.l10n.unknown);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(context.l10n.yourDaysJourney),
        const SizedBox(height: 16),
        ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: GestureDetector(
            onTap: () {
              if (summary.locations.isNotEmpty) {
                // Apple Maps cannot take waypoints via map_launcher, so the
                // preview opens the day's first stop; each timeline row below
                // opens its own stop.
                MapsUtil.launchMap(summary.locations.first.latitude, summary.locations.first.longitude);
              }
            },
            child: SizedBox(
              width: double.infinity,
              height: 200,
              child: OmiMapPreview(
                key: const ValueKey('daily_summary_journey_preview'),
                pins: [
                  for (final location in summary.locations)
                    OmiMapPin(latitude: location.latitude, longitude: location.longitude),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Timeline list
        ...timelineLocations.asMap().entries.map((entry) {
          final index = entry.key;
          final location = entry.value;

          return _buildTimelineItem(location, index);
        }),
      ],
    );
  }

  Widget _buildHighlightsSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(context.l10n.highlights),
        const SizedBox(height: 12),
        ...summary.highlights.map((highlight) {
          return GestureDetector(
            onTap: () {
              if (highlight.conversationIds.isNotEmpty) {
                _openConversation(highlight.conversationIds.first);
              }
            },
            child: Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(highlight.emoji, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          highlight.topic,
                          style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          highlight.summary,
                          style: TextStyle(color: OmiColors.textSecondary, fontSize: 13, height: 1.3),
                        ),
                      ],
                    ),
                  ),
                  if (highlight.conversationIds.isNotEmpty)
                    Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 18),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildActionItemsSection(DailySummary summary) {
    // Separate completed and incomplete items
    final incompleteItems = summary.actionItems.where((i) => !i.completed).toList();
    final completedItems = summary.actionItems.where((i) => i.completed).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            _buildSectionTitle(context.l10n.tasks),
            const Spacer(),
            if (completedItems.isNotEmpty)
              Text(
                '${completedItems.length}/${summary.actionItems.length}',
                style: TextStyle(color: OmiColors.textTertiary, fontSize: 13),
              ),
          ],
        ),
        const SizedBox(height: 12),
        // Show incomplete items first, then completed
        ...[...incompleteItems, ...completedItems].map((item) {
          return _buildActionItemRow(item);
        }),
      ],
    );
  }

  Widget _buildActionItemRow(ActionItemSummary item) {
    return GestureDetector(
      onTap: () => _openConversation(item.sourceConversationId),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            TaskCompletionMark(completed: item.completed),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                item.description,
                style: TextStyle(
                  color: item.completed ? OmiColors.textTertiary : OmiColors.textPrimary,
                  fontSize: 15,
                  height: 1.4,
                  decoration: item.completed ? TextDecoration.lineThrough : null,
                ),
              ),
            ),
            if (item.sourceConversationId != null) Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildUnresolvedQuestionsSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(context.l10n.unresolvedQuestions),
        const SizedBox(height: 12),
        ...summary.unresolvedQuestions.map((q) {
          return GestureDetector(
            onTap: () => _openConversation(q.conversationId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(q.question, style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, height: 1.4)),
                  ),
                  if (q.conversationId != null) Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildDecisionsMadeSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(context.l10n.decisions),
        const SizedBox(height: 12),
        ...summary.decisionsMade.map((d) {
          return GestureDetector(
            onTap: () => _openConversation(d.conversationId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(d.decision, style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, height: 1.4)),
                  ),
                  if (d.conversationId != null) Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  /// The same review rows the day-summary chat card shows, so a verdict cast
  /// in either place lands on the same memory. Placed before the LLM-prose
  /// learnings, which stay exactly as they were.
  Widget _buildMemoriesLearnedSection(DailySummary summary) {
    return MemoryReviewCard(
      items: summary.memoriesLearned,
      source: MemoryReviewSource.dailySummaryDetail,
      impressionKey: summary.id.isNotEmpty ? summary.id : widget.summaryId,
    );
  }

  Widget _buildKnowledgeNuggetsSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle(context.l10n.learnings),
        const SizedBox(height: 12),
        ...summary.knowledgeNuggets.map((k) {
          return GestureDetector(
            onTap: () => _openConversation(k.conversationId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(k.insight, style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, height: 1.4)),
                  ),
                  if (k.conversationId != null) Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  /// Every recap, newest first ([DailyRecapsPage]): the way to the days before the ones Home loaded.
  Widget _buildAllRecapsLink() {
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.lg),
      child: Center(
        child: OmiButton.tertiary(
          key: const Key('recap_all_recaps'),
          label: context.l10n.dailyRecaps,
          icon: Icons.calendar_view_day_rounded,
          onPressed: () => routeToPage(context, const DailyRecapsPage()),
        ),
      ),
    );
  }

  /// "‹ Tuesday · Thursday ›" (Rev 3 Recap): the neighbouring days in [DailySummaryDetailPage.days].
  Widget _buildDayArrows(DailySummary summary) {
    final days = widget.days;
    final i = days.indexWhere((d) => d.id == summary.id);
    if (i < 0) return const SizedBox.shrink();
    final older = i + 1 < days.length ? days[i + 1] : null;
    final newer = i > 0 ? days[i - 1] : null;
    if (older == null && newer == null) return const SizedBox.shrink();
    final dates = OmiDateFormat.of(context);
    String label(DailySummary day) {
      final date = DateTime.tryParse(day.date);
      return date == null ? day.formattedDate : dates.dayHeader(date);
    }

    return Padding(
      padding: const EdgeInsets.only(top: 40),
      child: Row(
        children: [
          if (older != null)
            Flexible(
              child: _DayArrow(
                key: const Key('recap_previous_day'),
                label: label(older),
                semanticsLabel: context.l10n.recapPreviousDay(label(older)),
                forward: false,
                onTap: () => _showDay(older),
              ),
            ),
          const Spacer(),
          if (newer != null)
            Flexible(
              child: _DayArrow(
                key: const Key('recap_next_day'),
                label: label(newer),
                semanticsLabel: context.l10n.recapNextDay(label(newer)),
                forward: true,
                onTap: () => _showDay(newer),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    // Canvas Recap: section headers at 20/25 semibold, like every grouped list.
    return Text(title, style: OmiType.title3);
  }

  Widget _buildTimelineItem(TimelineLocation location, int index) {
    final startFormatted = _formatTimeTo12Hour(location.startTime);
    final endFormatted = _formatTimeTo12Hour(location.endTime);
    final timeText = startFormatted.isNotEmpty
        ? (endFormatted.isNotEmpty && startFormatted != endFormatted
            ? '$startFormatted - $endFormatted'
            : startFormatted)
        : '';

    final semanticsLabel = timeText.isEmpty ? location.shortName : '${location.shortName}, $timeText';

    return Semantics(
      container: true,
      button: true,
      excludeSemantics: true,
      label: semanticsLabel,
      onTap: () => MapsUtil.launchMap(location.latitude, location.longitude),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => MapsUtil.launchMap(location.latitude, location.longitude),
        child: Container(
          key: ValueKey('daily_summary_location_row_$index'),
          margin: const EdgeInsets.only(bottom: 6),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      location.shortName,
                      style: TextStyle(
                        color: OmiColors.textPrimary,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        height: 1.3,
                      ),
                    ),
                    if (timeText.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          FaIcon(FontAwesomeIcons.clock, color: OmiColors.textTertiary, size: 12),
                          const SizedBox(width: 4),
                          Text(timeText, style: TextStyle(color: OmiColors.textTertiary, fontSize: 13)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

/// Platform-aware "Delete this recap?" confirm. Returns ``true`` when the
/// user taps the destructive action. Lifted to a free function so the list
/// page's swipe handler can fire the same dialog without instantiating the
/// detail page state.
/// Confirms deleting a daily recap. A recap cannot be restored, so this always asks.
Future<bool?> showDeleteRecapConfirmDialog(BuildContext context) {
  final l10n = context.l10n;
  return showOmiConfirm(
    context,
    title: l10n.deleteRecapConfirmTitle,
    message: l10n.deleteRecapConfirmBody,
    confirmLabel: l10n.deleteRecapAction,
    destructive: true,
  );
}

/// One of the recap's day arrows: a capsule with the neighbouring day's name and a chevron.
class _DayArrow extends StatelessWidget {
  const _DayArrow({
    super.key,
    required this.label,
    required this.semanticsLabel,
    required this.forward,
    required this.onTap,
  });

  final String label;
  final String semanticsLabel;
  final bool forward;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final chevron = Icon(
      forward ? Icons.chevron_right_rounded : Icons.chevron_left_rounded,
      size: 20,
      color: OmiColors.textSecondary,
    );
    return Semantics(
      button: true,
      label: semanticsLabel,
      excludeSemantics: true,
      onTap: onTap,
      child: OmiPressable(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          padding: EdgeInsets.fromLTRB(
              forward ? OmiSpacing.md : OmiSpacing.xs, 0, forward ? OmiSpacing.xs : OmiSpacing.md, 0),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.pillAll),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!forward) chevron,
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              if (forward) chevron,
            ],
          ),
        ),
      ),
    );
  }
}
