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
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/pages/conversation_detail/page.dart';
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

  const DailySummaryDetailPage({super.key, required this.summaryId, this.summary});

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
    super.dispose();
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
        child: CustomScrollView(
          slivers: [
            _buildHeader(summary),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 100),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  _buildOverviewCard(summary),
                  const SizedBox(height: 24),
                  _buildStatsRow(summary),
                  if (summary.highlights.isNotEmpty) ...[const SizedBox(height: 32), _buildHighlightsSection(summary)],
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
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(DailySummary summary) {
    return SliverAppBar(
      expandedHeight: 150,
      pinned: true,
      backgroundColor: OmiColors.surface0,
      leading: Center(child: OmiBackButton.circled(fillColor: Colors.black.withValues(alpha: 0.3))),
      actions: [
        OmiIconButton.filled(
          icon: _isSharing ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.share_outlined),
          label: context.l10n.share,
          fillColor: Colors.black.withValues(alpha: 0.3),
          onPressed: _isSharing ? null : _shareSummary,
        ),
        OmiIconButton.filled(
          icon: _isDeleting ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.more_horiz),
          label: context.l10n.moreOptions,
          fillColor: Colors.black.withValues(alpha: 0.3),
          onPressed: _isDeleting ? null : _showActionsSheet,
        ),
        const SizedBox(width: 8),
      ],
      flexibleSpace: FlexibleSpaceBar(
        background: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              // Neutral header wash (INV-UI-1: no purple).
              colors: [OmiColors.surface2, OmiColors.surface0],
            ),
          ),
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  const Spacer(),
                  // Date above emoji and title
                  Text(
                    summary.formattedDate,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.6),
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 8),
                  // Emoji and title row
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(summary.dayEmoji, style: const TextStyle(fontSize: 32)),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          summary.headline,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            height: 1.2,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
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
    );
  }

  Widget _buildOverviewCard(DailySummary summary) {
    return Text(summary.overview, style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.5));
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
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = items.length > 3 ? 3 : items.length;
        final itemWidth = (constraints.maxWidth - (columns - 1) * 8) / columns;
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [for (final item in items) SizedBox(width: itemWidth, child: item)],
        );
      },
    );
  }

  Widget _buildStatItem(FaIconData icon, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
      decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          FaIcon(icon, color: Colors.grey.shade400, size: 14),
          const SizedBox(width: 8),
          Text(
            value,
            style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
          ),
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
              decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
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
                          style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          highlight.summary,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.3),
                        ),
                      ],
                    ),
                  ),
                  if (highlight.conversationIds.isNotEmpty)
                    Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 18),
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
                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
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
        decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            // Checkbox indicator
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: item.completed ? Colors.green.withValues(alpha: 0.2) : Colors.transparent,
                border: Border.all(color: item.completed ? Colors.green : Colors.grey.shade600, width: 1.5),
              ),
              child: item.completed ? const Icon(Icons.check, color: Colors.green, size: 14) : null,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                item.description,
                style: TextStyle(
                  color: item.completed ? Colors.grey.shade500 : Colors.white,
                  fontSize: 15,
                  height: 1.4,
                  decoration: item.completed ? TextDecoration.lineThrough : null,
                ),
              ),
            ),
            if (item.sourceConversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
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
              decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(q.question, style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4)),
                  ),
                  if (q.conversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
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
              decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(d.decision, style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4)),
                  ),
                  if (d.conversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
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
              decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
              child: Row(
                children: [
                  Expanded(
                    child: Text(k.insight, style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4)),
                  ),
                  if (k.conversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
    );
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
          decoration: BoxDecoration(color: const Color(0xFF1A1A1F), borderRadius: BorderRadius.circular(16)),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      location.shortName,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        height: 1.3,
                      ),
                    ),
                    if (timeText.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          FaIcon(FontAwesomeIcons.clock, color: Colors.grey.shade500, size: 12),
                          const SizedBox(width: 4),
                          Text(timeText, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
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
