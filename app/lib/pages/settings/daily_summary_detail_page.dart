import 'dart:async';

import 'package:omi/services/app_review_service.dart';
import 'package:omi/widgets/app_review_prompt.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/conversations.dart' as conversations_api;
import 'package:omi/backend/http/api/users.dart'
    show
        RegenerateDailySummaryResult,
        deleteDailySummary,
        getDailySummary,
        regenerateDailySummary,
        setDailySummaryVisibility;
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/action_items/day_tasks_page.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart' show parseRecapDate;
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/utils/daily_summary_journey.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/utils/share_sheet.dart';
import 'package:omi/widgets/components/memory_review_card.dart';
import 'package:omi/widgets/native_static_map.dart';
import 'package:omi/widgets/omi_map_preview.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';

class DailySummaryDetailPage extends StatefulWidget {
  final String summaryId;
  final DailySummary? summary; // Can pass directly if already loaded

  final DayConversationsFetcher? dayConversationsFetcher;
  final DayTasksFetcher? dayTasksFetcher;

  /// Loads the summary when none is passed; [getDailySummary] unless a test injects a loader.
  @visibleForTesting
  final Future<DailySummary?> Function(String id)? summaryLoader;

  /// Loads a linked conversation; [conversations_api.getConversationById] unless a test injects one.
  @visibleForTesting
  final Future<ServerConversation?> Function(String id)? conversationFetcher;

  /// Opens a place in the map app; [MapsUtil.launchMap] unless a test injects a launcher.
  @visibleForTesting
  final void Function(double latitude, double longitude)? launchMap;

  /// Fetches the native journey map's file; [resolveNativeStaticMapFile] unless a test injects one.
  @visibleForTesting
  final NativeStaticMapResolver? staticMapResolver;

  const DailySummaryDetailPage({
    super.key,
    required this.summaryId,
    this.summary,
    this.dayConversationsFetcher,
    this.dayTasksFetcher,
    this.summaryLoader,
    this.conversationFetcher,
    this.launchMap,
    this.staticMapResolver,
  });

  @override
  State<DailySummaryDetailPage> createState() => _DailySummaryDetailPageState();
}

class _DailySummaryDetailPageState extends State<DailySummaryDetailPage> {
  DailySummary? _summary;
  bool _isLoading = true;
  bool _isSharing = false;
  bool _isDeleting = false;
  bool _isRegenerating = false;

  @override
  void initState() {
    super.initState();
    _loadSummary();
  }

  Future<void> _loadSummary() async {
    if (widget.summary != null) {
      setState(() {
        _summary = widget.summary;
        _isLoading = false;
      });
      // Track page view
      PlatformManager.instance.analytics.dailySummaryDetailViewed(
        summaryId: widget.summaryId,
        date: widget.summary!.date,
        source: 'direct',
      );
      return;
    }

    final summary = await (widget.summaryLoader ?? getDailySummary)(widget.summaryId);
    if (mounted) {
      setState(() {
        _summary = summary;
        _isLoading = false;
      });
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
          ? _nativeStatus(const OmiLoadingState(), loading: true)
          : _summary == null
              ? _nativeStatus(_buildNotFound(), loading: false)
              : _buildContent(),
    );
  }

  /// The loading and not-found states, projected natively with the same Back and Go Back.
  Widget _nativeStatus(Widget classic, {required bool loading}) {
    final l10n = context.l10n;
    return IosNativeSurface(
      title: l10n.recap,
      fallback: classic,
      loading: loading,
      empty: loading ? '' : l10n.summaryNotFound,
      toolbar: [
        NativeRow('recap_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).pop()),
      ],
      sections: [
        if (!loading)
          NativeSection('recap_not_found', [
            NativeRow('recap_not_found_label', l10n.summaryNotFound, kind: 'label', symbol: 'tray'),
            NativeRow('recap_go_back', l10n.goBack, action: (_) => Navigator.pop(context)),
          ]),
      ],
    );
  }

  void _launchMap(double latitude, double longitude) => (widget.launchMap ?? MapsUtil.launchMap)(latitude, longitude);

  /// Shows the blocking spinner: the native activity when available, otherwise the Flutter spinner
  /// dialog on the root navigator. The returned callback removes it exactly once, also after this
  /// page unmounts. Call it before awaiting any route or sheet.
  Future<VoidCallback> _showBlockingSpinner() async {
    // Captured before any await: the navigator outlives this page if it is popped mid-flight.
    final rootNavigator = Navigator.of(context, rootNavigator: true);
    final activity =
        nativePresentationEnabled ? await showIosNativeActivity(context, label: context.l10n.loading) : null;
    if (activity != null) return () => unawaited(activity.dismiss());
    if (!mounted) return () {};
    var shown = true;
    // Fullscreen blocking spinner — barrierDismissible=false so the user
    // can't half-cancel and get into a torn state.
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
    );
    return () {
      if (!shown) return;
      shown = false;
      if (rootNavigator.canPop()) rootNavigator.pop();
    };
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
      final sid = newShareId();
      final url = recapShareUrl(widget.summaryId, sid: sid);
      final outcome = await SharePlus.instance.share(
        ShareParams(uri: Uri.parse(url), subject: summary.headline, sharePositionOrigin: shareSheetOrigin()),
      );
      final targetApp = outcome.status == ShareResultStatus.success ? shareTargetApp(outcome.raw) : null;
      PlatformManager.instance.analytics.track('Daily Summary Shared', properties: {
        'summary_id': widget.summaryId,
        'date': summary.date,
        'share_id': sid,
        if (targetApp != null) 'target_app': targetApp,
      });
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
    final dismissSpinner = await _showBlockingSpinner();
    ServerConversation? conversation;
    var failed = false;
    try {
      conversation = await (widget.conversationFetcher ?? conversations_api.getConversationById)(conversationId);
    } catch (e) {
      failed = true;
    } finally {
      // Dismissed before any route opens, and even when this page is gone.
      dismissSpinner();
    }
    if (!mounted) return;
    if (failed) {
      OmiFeedback.error(context, context.l10n.somethingWentWrong);
    } else if (conversation != null) {
      routeToPage(context, ConversationDetailPage(conversation: conversation));
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

    // The spinner is dismissed unconditionally — even if the widget unmounts
    // mid-flight (route popped from outside, OS kills the activity).
    final dismissSpinner = await _showBlockingSpinner();
    final RegenerateDailySummaryResult result;
    try {
      result = await regenerateDailySummary(widget.summaryId);
    } finally {
      // Dismiss spinner first, then bail if widget is gone. Order matters:
      // mounted check before dismissal would orphan the spinner on dispose.
      dismissSpinner();
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
      child: _nativeContent(
          summary,
          _FadeIn(
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
                    ]),
                  ),
                ),
              ],
            ),
          )),
    );
  }

  Widget _nativeContent(DailySummary summary, Widget classic) {
    final l10n = context.l10n;
    final busy = _isSharing || _isDeleting || _isRegenerating;
    return IosNativeSurface(title: summary.formattedDate, fallback: classic, toolbar: [
      NativeRow('recap_back', l10n.back,
          symbol: 'chevron.left', enabled: !busy, action: (_) => Navigator.of(context).pop()),
      NativeRow('recap_share', l10n.share,
          symbol: 'square.and.arrow.up', enabled: !busy, action: (_) => _shareSummary()),
      NativeRow('recap_regenerate', l10n.regenerateRecap,
          symbol: 'arrow.clockwise', enabled: !busy, action: (_) => _regenerateRecap()),
      NativeRow('recap_delete', l10n.delete,
          symbol: 'trash', destructive: true, enabled: !busy, action: (_) => _confirmDelete()),
    ], sections: [
      NativeSection('recap_overview', [
        NativeRow('recap_headline', '${summary.dayEmoji} ${summary.headline}', kind: 'label'),
        NativeRow('recap_overview_text', summary.overview, kind: 'label'),
        ..._nativeStats(summary),
      ]),
      NativeSection(
          'recap_highlights',
          [
            for (final (index, item) in summary.highlights.indexed)
              NativeRow('recap_highlight_$index', '${item.emoji} ${item.topic}',
                  subtitle: item.summary,
                  kind: item.conversationIds.isEmpty ? 'label' : 'button',
                  action: item.conversationIds.isEmpty ? null : (_) => _openConversation(item.conversationIds.first))
          ],
          title: l10n.highlights),
      NativeSection(
          'recap_tasks',
          [
            for (final (index, item) in summary.actionItems.indexed)
              NativeRow('recap_task_$index', item.description,
                  subtitle: item.completed ? l10n.completed : '',
                  kind: item.sourceConversationId == null ? 'label' : 'button',
                  action:
                      item.sourceConversationId == null ? null : (_) => _openConversation(item.sourceConversationId))
          ],
          title: l10n.actionItems),
      NativeSection(
          'recap_questions',
          [
            for (final (index, item) in summary.unresolvedQuestions.indexed)
              NativeRow('recap_question_$index', item.question,
                  kind: item.conversationId == null ? 'label' : 'button',
                  action: item.conversationId == null ? null : (_) => _openConversation(item.conversationId))
          ],
          title: l10n.unresolvedQuestions),
      NativeSection(
          'recap_decisions',
          [
            for (final (index, item) in summary.decisionsMade.indexed)
              NativeRow('recap_decision_$index', item.decision,
                  kind: item.conversationId == null ? 'label' : 'button',
                  action: item.conversationId == null ? null : (_) => _openConversation(item.conversationId))
          ],
          title: l10n.decisions),
      NativeSection(
          'recap_knowledge',
          [
            for (final (index, item) in summary.knowledgeNuggets.indexed)
              NativeRow('recap_knowledge_$index', item.insight,
                  kind: item.conversationId == null ? 'label' : 'button',
                  action: item.conversationId == null ? null : (_) => _openConversation(item.conversationId))
          ],
          title: l10n.learnings),
      if (summary.memoriesLearned.isNotEmpty)
        NativeSection('recap_memories', [
          NativeRow('recap_review_memories', l10n.memories,
              action: (_) => showMemoryReviewSheet(context,
                  items: summary.memoriesLearned,
                  source: MemoryReviewSource.dailySummaryDetail,
                  impressionKey: summary.id.isNotEmpty ? summary.id : widget.summaryId,
                  title: l10n.memories)),
        ]),
      if (summary.locations.isNotEmpty)
        NativeSection('recap_locations', [
          NativeRow('recap_locations_map', l10n.yourDaysJourney, action: (_) => _showJourney(summary)),
        ]),
    ]);
  }

  /// The classic stat tiles as rows: conversations and tasks open their day pages when the recap
  /// date parses, and watching minutes and proactive moments show only when positive.
  List<NativeRow> _nativeStats(DailySummary summary) {
    final l10n = context.l10n;
    final stats = summary.stats;
    final recapDay = parseRecapDate(summary.date);
    return [
      NativeRow('recap_conversations_stat', l10n.conversationCount(stats.totalConversations),
          kind: recapDay == null ? 'label' : 'navigation',
          symbol: 'message',
          action: recapDay == null
              ? null
              : (_) => routeToPage(
                  context, DayConversationsPage(date: recapDay, fetchConversations: widget.dayConversationsFetcher))),
      NativeRow('recap_duration_stat', stats.formattedDuration,
          kind: 'label', subtitle: l10n.durationLabel, symbol: 'clock'),
      NativeRow('recap_tasks_stat', l10n.tasksCountLabel(stats.actionItemsCount),
          kind: recapDay == null ? 'label' : 'navigation',
          symbol: 'checkmark.circle',
          action: recapDay == null
              ? null
              : (_) => routeToPage(context, DayTasksPage(date: recapDay, fetchTasks: widget.dayTasksFetcher))),
      if ((stats.watchingMinutes ?? 0) > 0)
        NativeRow('recap_watching_stat', stats.formattedWatchingDuration!, kind: 'label', symbol: 'eye'),
      if ((stats.proactiveMoments ?? 0) > 0)
        NativeRow('recap_proactive_stat', '${stats.proactiveMoments}', kind: 'label', symbol: 'bell'),
    ];
  }

  /// "Your day's journey" in a sheet: natively, a Dart-fetched map image, Open in Maps and the
  /// timeline; otherwise the classic journey section.
  Future<void> _showJourney(DailySummary summary) {
    Widget classic() => SingleChildScrollView(child: _buildLocationsMap(summary));
    return showOmiSheet<void>(
      context: context,
      builder: (_) => classic(),
      nativeBuilder: (_) => RecapJourneySheet(
        locations: summary.locations,
        onLaunch: _launchMap,
        staticMapResolver: widget.staticMapResolver,
        fallback: OmiSheetScaffold(child: classic()),
      ),
    );
  }

  Widget _buildHeader(DailySummary summary) {
    return SliverAppBar(
      expandedHeight: 150,
      pinned: true,
      backgroundColor: OmiColors.surface0,
      leading: Center(child: OmiBackButton.circled(fillColor: OmiColors.surface3)),
      actions: [
        OmiIconButton.filled(
          icon: _isSharing ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.share_outlined),
          label: context.l10n.share,
          fillColor: OmiColors.surface3,
          onPressed: _isSharing ? null : _shareSummary,
        ),
        OmiIconButton.filled(
          icon: _isDeleting ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.more_horiz),
          label: context.l10n.moreOptions,
          fillColor: OmiColors.surface3,
          onPressed: _isDeleting ? null : _showActionsSheet,
        ),
        const SizedBox(width: 8),
      ],
      flexibleSpace: FlexibleSpaceBar(
        background: Container(
          decoration: BoxDecoration(
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
                      color: OmiColors.textPrimary.withValues(alpha: 0.6),
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
                          style: TextStyle(
                            color: OmiColors.textPrimary,
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
    return Text(summary.overview, style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, height: 1.5));
  }

  Widget _buildStatsRow(DailySummary summary) {
    final l10n = context.l10n;
    final recapDay = parseRecapDate(summary.date);
    final items = <Widget>[
      _buildStatItem(
        FontAwesomeIcons.message,
        '${summary.stats.totalConversations}',
        key: const ValueKey('recap_conversations_stat'),
        semanticsLabel: l10n.conversationCount(summary.stats.totalConversations),
        onTap: recapDay == null
            ? null
            : () => routeToPage(
                context, DayConversationsPage(date: recapDay, fetchConversations: widget.dayConversationsFetcher)),
      ),
      _buildStatItem(
        FontAwesomeIcons.clock,
        summary.stats.formattedDuration,
        semanticsLabel: '${l10n.durationLabel}, ${summary.stats.formattedDuration}',
      ),
      _buildStatItem(
        FontAwesomeIcons.circleCheck,
        '${summary.stats.actionItemsCount}',
        key: const ValueKey('recap_tasks_stat'),
        semanticsLabel: l10n.tasksCountLabel(summary.stats.actionItemsCount),
        onTap: recapDay == null
            ? null
            : () => routeToPage(context, DayTasksPage(date: recapDay, fetchTasks: widget.dayTasksFetcher)),
      ),
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

  Widget _buildStatItem(FaIconData icon, String value, {Key? key, VoidCallback? onTap, String? semanticsLabel}) {
    final tile = Container(
      constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          FaIcon(icon, color: OmiColors.textSecondary, size: 14),
          const SizedBox(width: 8),
          Text(
            value,
            style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, fontWeight: FontWeight.w600),
          ),
          if (onTap != null) ...[
            const SizedBox(width: OmiSpacing.xxs),
            Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 14),
          ],
        ],
      ),
    );
    if (onTap == null) {
      return KeyedSubtree(key: key, child: tile);
    }
    return Semantics(
      key: key,
      button: true,
      label: semanticsLabel,
      child: Material(
        color: Colors.transparent,
        borderRadius: OmiRadius.lgAll,
        child: InkWell(borderRadius: OmiRadius.lgAll, onTap: onTap, child: tile),
      ),
    );
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
                _launchMap(summary.locations.first.latitude, summary.locations.first.longitude);
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
            // Checkbox indicator
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: item.completed ? Colors.green.withValues(alpha: 0.2) : Colors.transparent,
                border: Border.all(color: item.completed ? Colors.green : OmiColors.textTertiary, width: 1.5),
              ),
              child: item.completed ? const Icon(Icons.check, color: Colors.green, size: 14) : null,
            ),
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

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: TextStyle(color: OmiColors.textPrimary, fontSize: 18, fontWeight: FontWeight.w600),
    );
  }

  Widget _buildTimelineItem(TimelineLocation location, int index) {
    final timeText = _timelineTime(location);

    final semanticsLabel = timeText.isEmpty ? location.shortName : '${location.shortName}, $timeText';

    return Semantics(
      container: true,
      button: true,
      excludeSemantics: true,
      label: semanticsLabel,
      onTap: () => _launchMap(location.latitude, location.longitude),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _launchMap(location.latitude, location.longitude),
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

/// A stop's 12-hour time range, or its start time, or nothing.
String _timelineTime(TimelineLocation location) {
  final startFormatted = _formatTimeTo12Hour(location.startTime);
  final endFormatted = _formatTimeTo12Hour(location.endTime);
  return startFormatted.isNotEmpty
      ? (endFormatted.isNotEmpty && startFormatted != endFormatted ? '$startFormatted - $endFormatted' : startFormatted)
      : '';
}

/// The native "Your day's journey" sheet: the day's map as a temporary PNG fetched by Dart, Open in
/// Maps for the first stop, and one row per timeline stop. This State owns the map file and deletes
/// it on dispose, on a brightness or session change and when a fetch completes too late. Rows
/// address stops by index; only Dart maps an index back to its coordinates.
/// Fades the classic recap content in once it mounts. Its controller lives here, not on the page,
/// so nothing ticks while the native presentation renders in place of this subtree.
class _FadeIn extends StatefulWidget {
  const _FadeIn({required this.child});

  final Widget child;

  @override
  State<_FadeIn> createState() => _FadeInState();
}

class _FadeInState extends State<_FadeIn> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(duration: const Duration(milliseconds: 800), vsync: this)..forward();
  late final _opacity = CurvedAnimation(parent: _controller, curve: Curves.easeOut);

  @override
  void dispose() {
    _opacity.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(opacity: _opacity, child: widget.child);
}

class RecapJourneySheet extends StatefulWidget {
  const RecapJourneySheet({
    super.key,
    required this.locations,
    required this.onLaunch,
    required this.fallback,
    this.staticMapResolver,
  });

  /// The day's stops.
  final List<LocationPin> locations;

  /// Opens a place in the map app.
  final void Function(double latitude, double longitude) onLaunch;

  /// The complete Flutter journey, already inside its sheet scaffold.
  final Widget fallback;
  final NativeStaticMapResolver? staticMapResolver;

  @override
  State<RecapJourneySheet> createState() => _RecapJourneySheetState();
}

class _RecapJourneySheetState extends State<RecapJourneySheet> {
  late final _map = NativeStaticMap(resolver: widget.staticMapResolver);

  @override
  void dispose() {
    _map.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Rebuilds on a theme change, so a new map in the other style replaces the current file.
    Theme.of(context);
    final width = (MediaQuery.sizeOf(context).width - 32).round();
    if (widget.locations.isNotEmpty && width > 0) {
      _map.show(
        pins: [
          for (final location in widget.locations) OmiMapPin(latitude: location.latitude, longitude: location.longitude)
        ],
        width: width,
        height: 200,
        brightness: OmiColors.active == OmiPalette.light ? Brightness.light : Brightness.dark,
      );
    }
    return ListenableBuilder(listenable: _map, builder: (context, _) => _surface(context));
  }

  Widget _surface(BuildContext context) {
    final l10n = context.l10n;
    final locations = widget.locations;
    final stops = buildTimelineLocations(locations, unknownLabel: l10n.unknown);
    return IosNativeSurface(
      title: l10n.yourDaysJourney,
      fallback: widget.fallback,
      toolbar: [
        NativeRow('recap_journey_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('recap_journey_map', [
          if (_map.uri != null)
            NativeRow('recap_journey_image', l10n.yourDaysJourney, kind: 'image', imageUri: _map.uri, maximumValue: 4),
          if (_map.loading) NativeRow('recap_journey_map_loading', l10n.loading, kind: 'label'),
          if (_map.failed) NativeRow('recap_journey_map_error', l10n.couldNotLoadMap, kind: 'label'),
          // As the classic preview: Apple Maps takes no waypoints, so this opens the day's first stop.
          if (locations.isNotEmpty)
            NativeRow('recap_open_maps', l10n.openInMaps,
                symbol: 'map', action: (_) => widget.onLaunch(locations.first.latitude, locations.first.longitude)),
        ]),
        NativeSection('recap_journey_timeline', [
          for (final (index, stop) in stops.indexed)
            NativeRow('recap_location_$index', stop.shortName,
                subtitle: _timelineTime(stop),
                symbol: 'mappin',
                action: (_) => widget.onLaunch(stop.latitude, stop.longitude)),
        ]),
      ],
    );
  }
}
