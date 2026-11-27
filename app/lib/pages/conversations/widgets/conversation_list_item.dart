import 'dart:async';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversation_detail/conversation_live_guard.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:clock/clock.dart';
import 'package:omi/pages/conversations/home/home_model.dart' show conversationStepOverdue, homeTileState;
import 'package:omi/pages/conversations/home/home_row_shell.dart';
import 'package:omi/pages/conversations/home/home_swipe_delete.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/on_device/on_device_provenance_section.dart';
import 'package:omi/pages/paywall/value_moment_paywall.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/held_audio/processing_backlog_view.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversation_task_presence_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/registry/events.g.dart' show ConversationUntitledRenderedSurface;
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';

/// The row title for a conversation (hub audit #21): its title, else its transcript text (legacy
/// rows the server left untitled), a recording date/time when neither exists, and
/// "Discarded · 12s" for a discarded one (its words go in [conversationSnippet]).
String conversationRowTitle(BuildContext context, ServerConversation conversation) {
  final l10n = context.l10n;
  if (conversation.isTranscriptionAllowanceHeld &&
      (conversation.structured.title.trim().isEmpty || TranscriptionPendingConversations.replacesTitle(conversation))) {
    return l10n.summaryTranscriptionPendingTitle;
  }
  // A row the server said is not transcribed keeps its own title and the status slot says why,
  // unless the title is only the server's stand-in; then the status is the title.
  if (conversation.homeStep == 'failed' &&
      !conversation.isAdmittedForTranscription &&
      !conversation.isTranscriptionAllowanceHeld) {
    if (!TranscriptionPendingConversations.contains(conversation.id)) {
      return l10n.summaryTemplateFailedTitle(l10n.omiAppName);
    }
    if (TranscriptionPendingConversations.replacesTitle(conversation)) return l10n.summaryTranscriptionPendingTitle;
  }
  // A noise clip revealed from Home's fold reads like any row, not as "Discarded".
  if (conversation.discarded && !conversation.isFoldedNoise) {
    final seconds = conversation.getDurationInSeconds();
    if (seconds <= 0) return l10n.discardedConversation;
    return l10n.discardedConversationTitle(OmiDuration.compact(seconds, l10n));
  }
  if (awaitsLiveTitle(conversation, title: conversation.structured.title.decodeString)) return l10n.listening;
  return conversationDisplayTitle(
    conversation,
    l10n,
    surface: ConversationUntitledRenderedSurface.list,
    dates: OmiDateFormat.of(context),
    title: conversation.structured.title.decodeString,
  );
}

/// A plain-text preview of what was said: the transcript words without timestamps or speaker
/// prefixes, newest last, trimmed to [maxChars] at a word boundary.
String conversationSnippet(ServerConversation conversation, {int maxChars = 160}) {
  // Only collect the visible prefix plus one character to decide whether it
  // needs an ellipsis. Hydrated/retained conversations can have hours of text;
  // joining all of it for each scrolling row makes a short preview O(history).
  final prefix = StringBuffer();
  for (final segment in conversation.transcriptSegments) {
    final words = segment.text.trim();
    if (words.isEmpty) continue;
    if (prefix.isNotEmpty) prefix.write(' ');
    final remaining = maxChars + 1 - prefix.length;
    if (remaining > 0) prefix.write(words.length > remaining ? words.substring(0, remaining) : words);
    if (prefix.length > maxChars) break;
  }
  final text = prefix.toString();
  if (text.length <= maxChars) return text;
  final cut = text.substring(0, maxChars);
  final space = cut.lastIndexOf(' ');
  return '${space > maxChars ~/ 2 ? cut.substring(0, space) : cut}…';
}

class ConversationListItem extends StatefulWidget {
  final bool isFromOnboarding;
  final DateTime date;
  final int conversationIdx;
  final ServerConversation conversation;

  /// Optional reprocess override for tests.
  final Future<ReprocessResult> Function(String conversationId)? reprocess;

  /// Whether the long-press menu offers Select (multi-select). Off where no selection bar is shown
  /// (the Home preview), so selection mode can never start without a way to act on it or leave.
  final bool allowSelection;

  /// Parent supplies outer spacing, while normal lock and row interactions remain intact.
  final bool embedded;

  /// Closed episode projection, drawn by the same conversation row widget.
  final Episode? homeEpisode;
  final bool openEpisodeFromSearch;

  /// A filtered server page already proves canonical membership.
  final bool? hasLinkedTasks;

  const ConversationListItem({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.isFromOnboarding = false,
    this.reprocess,
    this.allowSelection = true,
    this.embedded = false,
    this.homeEpisode,
    this.openEpisodeFromSearch = true,
    this.hasLinkedTasks,
  });

  @override
  State<ConversationListItem> createState() => _ConversationListItemState();
}

class _ConversationListItemState extends State<ConversationListItem> {
  Timer? _conversationNewStatusResetTimer;
  bool isNew = false;
  bool _reprocessing = false;
  bool _hasLinkedTasks = false;

  int _visualSignature(ServerConversation conversation) => Object.hashAll([
        conversation.structured.title,
        conversation.structured.emoji,
        conversation.structured.category,
        conversation.status,
        conversation.homeStep,
        conversation.discarded,
        conversation.starred,
        conversation.folderId,
        conversation.visibility,
        conversation.startedAt,
        conversation.finishedAt,
        conversation.photos.length,
        conversation.transcriptSegments.length,
        conversation.captureGroup?.id,
        conversation.captureGroup?.revision,
        conversation.summaryRetryable,
        conversation.isLocked,
        conversation.processingDeferred,
        conversation.v3?.tileState,
        conversation.v3?.titleLocked,
        widget.homeEpisode?.members.length,
        _hasLinkedTasks,
      ]);

  @override
  void initState() {
    super.initState();
    _offerAtCapIfLocked();
    TranscriptionPendingConversations.ids.addListener(_onPendingChanged);
  }

  bool _pendingShown = false;

  /// Title and retry area follow the not-transcribed set, including marks made on other surfaces.
  void _onPendingChanged() {
    final pending = TranscriptionPendingConversations.contains(widget.conversation.id);
    if (pending != _pendingShown && mounted) setState(() {});
  }

  @override
  void didUpdateWidget(covariant ConversationListItem oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.conversation.isLocked) _offerAtCapIfLocked();
  }

  /// The free allowance locked a conversation the reader can see: the cap offer, once.
  void _offerAtCapIfLocked() {
    if (!widget.conversation.isLocked) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !widget.conversation.isLocked || ModalRoute.of(context)?.isCurrent == false) return;
      ValueMomentPaywall.offer(PaywallMoment.freeCap,
          conversation: widget.conversation, usage: context.read<UsageProvider?>());
    });
  }

  @override
  void dispose() {
    TranscriptionPendingConversations.ids.removeListener(_onPendingChanged);
    _conversationNewStatusResetTimer?.cancel();
    super.dispose();
  }

  Future<void> _onReprocess() async {
    if (_reprocessing || widget.conversation.id == '0') return;
    setState(() => _reprocessing = true);
    try {
      final reprocess = widget.reprocess ?? reProcessConversationServer;
      final result = await reprocess(widget.conversation.id);
      if (!mounted) return;
      switch (result) {
        case ReprocessSuccess(:final conversation):
          context.read<ConversationProvider>().applyConversationReprocessResult(conversation);
        // Not an error: the row shows the server's waiting state, or the not-transcribed status.
        case ReprocessTranscriptionPending(conversation: final waiting?):
          context.read<ConversationProvider>().applyConversationReprocessResult(waiting);
        case ReprocessTranscriptionPending():
          TranscriptionPendingConversations.mark(widget.conversation.id);
        default:
          AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
      }
    } catch (_) {
      if (!mounted) return;
      AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _reprocessing = false);
    }
  }

  /// A row the server said is still awaiting transcription gets a plain waiting status and no retry.
  Widget _buildTranscriptionPending(BuildContext context) => Text(
        context.l10n.summaryTranscriptionPendingTitle,
        key: const Key('conversation_transcription_pending_indicator'),
        style: HomeRowShell.subtitleStyle,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      );

  Future<void> _open(BuildContext context, ConversationProvider provider) async {
    if (widget.conversation.isLocked) {
      if (!context.read<UsageProvider>().showSubscriptionUI) return;
      openHeldAudioPlans(context);
      return;
    }
    if (widget.homeEpisode case final episode?) {
      await routeToPage(context, EpisodePage(episode: episode));
      return;
    }
    final episodes = context.read<EpisodeProvider?>();
    if (widget.openEpisodeFromSearch && provider.previousQuery.isNotEmpty && episodes?.enabled == true) {
      final episode = await episodes!.episodeFor(widget.conversation.id);
      if (!context.mounted) return;
      if (episode != null && !episode.live && episode.members.length >= 2) {
        await routeToPage(context, EpisodePage(episode: episode));
        return;
      }
    }
    HapticFeedback.selectionClick();
    // The detail page seeds its provider from the supplied conversation
    // after its first frame. Notifying that provider before pushing the
    // route delayed visible navigation and rebuilt listeners behind it.
    final startingTitle = widget.conversation.structured.title;

    final searchQuery = provider.previousQuery;
    final hoursSinceConversation = DateTime.now().difference(widget.conversation.createdAt).inHours;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      provider.onConversationTap(widget.conversation.id);
      // Off the navigation frame, but never SchedulerBinding.scheduleTask(Priority.idle): while
      // any ticker runs (Home's live dot, a processing bar) the scheduler skips an idle task and
      // re-arms a zero-delay timer every event-loop turn, spinning the UI isolate until the
      // animation stops.
      Timer.run(() {
        if (!mounted) return;
        if (searchQuery.isNotEmpty) {
          ProductTelemetry.instance.value(
            ProductValue.searchResultOpened,
            surface: ProductSurface.conversations,
            objectId: RecordReference.fromId(widget.conversation.id),
          );
          PlatformManager.instance.analytics.conversationOpenedFromSearch(
            conversation: widget.conversation,
            searchQuery: searchQuery,
            conversationIndexInResults: widget.conversationIdx,
          );
        } else {
          PlatformManager.instance.analytics.conversationListItemClickedWithTimeDifference(
            conversation: widget.conversation,
            conversationIndex: widget.conversationIdx,
            hoursSinceConversation: hoursSinceConversation,
          );
        }
      });
    });

    final seek = searchMomentSeekFromSnippets(snippets: widget.conversation.matchSnippets, searchQuery: searchQuery);

    final resultFuture = routeToPage(
      context,
      ConversationDetailPage(
        conversation: widget.conversation,
        isFromOnboarding: widget.isFromOnboarding,
        // Search matches explicitly open Transcript. Other rows
        // let detail choose Transcript for retained fragments that
        // have no generated summary after hydration.
        initialTab: seek != null ? ConversationTab.transcript : null,
        initialSeekStart: seek?.start,
        initialSeekEnd: seek?.end,
      ),
    );
    var result = await resultFuture;
    if (context.mounted) {
      // Don't upsert if the conversation was deleted while on the detail page
      if (result is Map && result['deleted'] == true) return;
      bool stillExists = provider.conversations.any((c) => c.id == widget.conversation.id);
      if (stillExists) {
        String newTitle = context.read<ConversationDetailProvider>().conversation.structured.title;
        if (startingTitle != newTitle) {
          widget.conversation.structured.title = newTitle;
          provider.upsertConversation(widget.conversation);
        }
      }
    }
  }

  static ConversationActionAction _rowActionAnalytics(ConversationRowAction action, bool starred) => switch (action) {
        ConversationRowAction.open => ConversationActionAction.open,
        ConversationRowAction.star => starred ? ConversationActionAction.unstar : ConversationActionAction.star,
        ConversationRowAction.move => ConversationActionAction.moveFolder,
        ConversationRowAction.share => ConversationActionAction.share,
        ConversationRowAction.recordings => ConversationActionAction.recordingsOpen,
        ConversationRowAction.separate => ConversationActionAction.separate,
        ConversationRowAction.select => ConversationActionAction.select,
        ConversationRowAction.delete => ConversationActionAction.delete,
      };

  /// Long-press: the row's one context menu (hub audit #7). Multi-select is one of its entries.
  Future<void> _showActions(BuildContext context, ConversationProvider provider) async {
    HapticFeedback.mediumImpact();
    final conversation = widget.conversation;
    final action = await showConversationActionsSheet(
      context,
      conversation,
      canSelect: widget.allowSelection && provider.isConversationEligibleForMerge(conversation.id),
    );
    if (action == null || !context.mounted) return;
    trackConversationAction(_rowActionAnalytics(action, conversation.starred), ConversationActionSurface.rowLongPress);
    switch (action) {
      case ConversationRowAction.open:
        await _open(context, provider);
      case ConversationRowAction.star:
        await toggleConversationStarred(context, conversation);
      case ConversationRowAction.move:
        await moveConversationToFolder(context, conversation);
      case ConversationRowAction.share:
        await shareConversation(context, conversation);
      case ConversationRowAction.recordings:
        await showConversationRowRecordings(context, conversation);
      case ConversationRowAction.separate:
        await separateFromConversationRow(context, conversation);
      case ConversationRowAction.select:
        provider.enterSelectionMode();
        provider.toggleConversationSelection(conversation.id);
      case ConversationRowAction.delete:
        if (!await confirmConversationDelete(context) || !context.mounted) return;
        PlatformManager.instance.analytics.conversationSwipedToDelete(conversation);
        await deleteConversationsWithUndo(context, [conversation]);
    }
  }

  @override
  Widget build(BuildContext context) {
    _pendingShown = TranscriptionPendingConversations.contains(widget.conversation.id);
    bool? linked = widget.hasLinkedTasks;
    if (!widget.conversation.isLocked && linked == null) {
      context.read<ConversationTaskPresenceProvider?>()?.request(widget.conversation.id);
      linked = context.select<ConversationTaskPresenceProvider?, bool?>(
        (source) => source?.presence(widget.conversation.id),
      );
    }
    _hasLinkedTasks = !widget.conversation.isLocked && linked == true;
    // Is new conversation
    DateTime memorizedAt = widget.conversation.createdAt;
    if (widget.conversation.finishedAt != null && widget.conversation.finishedAt!.isAfter(memorizedAt)) {
      memorizedAt = widget.conversation.finishedAt!;
    }
    int seconds = (DateTime.now().millisecondsSinceEpoch - memorizedAt.millisecondsSinceEpoch) ~/ 1000;
    isNew = 0 < seconds && seconds < 60; // 1m
    if (isNew) {
      _conversationNewStatusResetTimer?.cancel();
      _conversationNewStatusResetTimer = Timer(const Duration(seconds: 60), () async {
        if (!mounted) return;
        setState(() {
          isNew = false;
        });
      });
    }

    return RepaintBoundary(
      child: Selector<ConversationProvider,
          ({int visualSignature, bool isSelectionMode, bool isSelected, bool isMerging, bool isEligible})>(
        selector: (context, provider) => (
          // ServerConversation is mutable. Select the visible primitive fields
          // instead of object identity so star/title/status updates are not lost.
          visualSignature: _visualSignature(widget.conversation),
          isSelectionMode: provider.isSelectionModeActive,
          isSelected: provider.isConversationSelected(widget.conversation.id),
          // The row already has the conversation. The id-based helpers search
          // the entire history, twice per mounted row on *every* notify, even
          // when the selector correctly decides not to rebuild the content.
          isMerging: provider.mergingConversationIds.contains(widget.conversation.id) ||
              widget.conversation.status == ConversationStatus.merging,
          isEligible: !widget.conversation.isLocked &&
              !_isLive &&
              !provider.mergingConversationIds.contains(widget.conversation.id),
        ),
        builder: (context, rowState, child) {
          final provider = context.read<ConversationProvider>();
          final isSelectionMode = rowState.isSelectionMode;
          final isSelected = rowState.isSelected;
          final isMerging = rowState.isMerging;
          final isEligible = rowState.isEligible;

          Future<void> onTap() async {
            // If in selection mode, toggle selection only if eligible
            if (isSelectionMode) {
              if (!isEligible) {
                // Show feedback that this conversation cannot be selected
                HapticFeedback.lightImpact();
                OmiFeedback.info(context, context.l10n.conversationCannotBeMerged);
                return;
              }
              HapticFeedback.selectionClick();
              provider.toggleConversationSelection(widget.conversation.id);
              return;
            }
            await _open(context, provider);
          }

          return GestureDetector(
            onTap: onTap,
            // The conversation in progress opens; it is not deleted or edited while capture writes it.
            onLongPress: isSelectionMode || isMerging || _isLive || widget.homeEpisode != null
                ? null
                : () => _showActions(context, provider),
            child: Stack(
              children: [
                Padding(
                  padding: _cardPadding,
                  child: AnimatedOpacity(
                    duration: const Duration(milliseconds: 200),
                    opacity: (isSelectionMode && !isEligible) ? 0.6 : 1.0,
                    child: Semantics(
                      selected: isSelectionMode ? isSelected : null,
                      child: HomeSwipeDelete(
                        enabled: !isSelectionMode && !isMerging && !_isLive && widget.homeEpisode == null,
                        // One delete path (D5): confirm unless opted out, then Undo. The confirm
                        // pops from the row's delete button.
                        confirm: (anchor) async {
                          HapticFeedback.mediumImpact();
                          trackConversationAction(
                            ConversationActionAction.delete,
                            ConversationActionSurface.rowSwipe,
                          );
                          return confirmConversationDelete(context, anchor: anchor);
                        },
                        onDeleted: () {
                          final conversation = widget.conversation;
                          PlatformManager.instance.analytics.conversationSwipedToDelete(conversation);
                          unawaited(deleteConversationsWithUndo(context, [conversation]));
                        },
                        child: AnimatedContainer(
                          key: const ValueKey('conversation_card'),
                          duration: const Duration(milliseconds: 200),
                          width: double.maxFinite,
                          decoration: BoxDecoration(
                            color: isSelected
                                ? OmiColors.surface3
                                : (isSelectionMode && !isEligible)
                                    ? OmiColors.surface2
                                    : OmiColors.surface1,
                            borderRadius: OmiRadius.xlAll,
                            border: isSelected
                                ? Border.all(color: OmiColors.accent, width: 2)
                                : (isSelectionMode && !isEligible)
                                    ? Border.all(color: OmiColors.border, width: 1)
                                    : null,
                          ),
                          child: ClipRRect(borderRadius: OmiRadius.xlAll, child: _buildCardContent(context, onTap)),
                        ),
                      ),
                    ),
                  ),
                ),
                // Merging overlay covering the full card
                if (isMerging)
                  Positioned.fill(
                    child: Padding(padding: _cardPadding, child: _buildMergingOverlay()),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  EdgeInsets get _cardPadding {
    if (widget.embedded) return EdgeInsets.zero;
    final side = widget.isFromOnboarding ? 0.0 : 16.0;
    return EdgeInsets.only(top: 8, left: side, right: side);
  }

  static TextStyle get _metaStyle => HomeRowShell.subtitleStyle;

  Widget _buildCardContent(BuildContext context, Future<void> Function() onTap) {
    final content = Padding(
      padding: const EdgeInsetsDirectional.symmetric(horizontal: 14, vertical: 14),
      child: _buildMobileLayout(context),
    );
    if (!widget.conversation.isLocked) return content;
    return OmiLockedPreview(
      label: context.l10n.upgrade,
      onPressed: onTap,
      child: content,
    );
  }

  /// Time and length, with the New badge beside them (hub audit #16) and the star.
  Widget _buildMetaRow(BuildContext context) {
    final duration = _getConversationDuration(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Wrap(
            spacing: OmiSpacing.xs,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              // "9:00 AM · 25m", with the same separator as every other Home subtitle. The conversation
              // in progress shows its speech so far, through the same duration authority as its detail;
              // counting from its start to now grew it through silence.
              Text(
                [
                  OmiDateFormat.of(context).time(widget.conversation.startedAt ?? widget.conversation.createdAt),
                  if (duration.isNotEmpty) duration,
                ].join(' · '),
                key: _isLive && duration.isNotEmpty ? const Key('conversation_row_live_length') : null,
                style: _metaStyle,
                maxLines: 1,
              ),
              if (_hasLinkedTasks)
                Semantics(
                  key: const ValueKey('conversation_has_tasks'),
                  label: context.l10n.hasLinkedTasksLabel,
                  excludeSemantics: true,
                  child: Icon(Icons.checklist_rounded, size: 16, color: OmiColors.textSecondary),
                ),
              if (_captureSources.length > 1) CaptureSourceIcons(sources: _captureSources),
              if (isNew) ConversationNewStatusIndicator(text: context.l10n.conversationNewIndicator),
            ],
          ),
        ),
        if (widget.conversation.starred)
          Padding(
            padding: const EdgeInsetsDirectional.only(start: 4),
            child: Semantics(
              label: context.l10n.starred,
              child: const FaIcon(FontAwesomeIcons.solidStar, size: 12, color: Colors.amber),
            ),
          ),
      ],
    );
  }

  Widget _buildMobileLayout(BuildContext context) {
    final discarded = widget.conversation.discarded && !widget.conversation.isFoldedNoise;
    final discardedSnippet =
        discarded || widget.conversation.processingDeferred ? conversationSnippet(widget.conversation) : '';
    // A failed summary the server can redo: "Summary failed" is the row's status, and Try Again sits
    // where every other Home row puts its action.
    final failedRetry = !_pendingShown &&
        !widget.conversation.isTranscriptionAllowanceHeld &&
        !widget.conversation.isAdmittedForTranscription &&
        (widget.conversation.showsSummaryRetry || isFailedConversation(widget.conversation)) &&
        !TranscriptionPendingConversations.replacesTitle(widget.conversation);
    // A row with only its title and status lines up with every other Home row (HomeRowShell): one
    // tap target tall, centred. Extra lines (a snippet, a waiting note) keep the tile at the top.
    final compact = discardedSnippet.isEmpty &&
        _searchSnippetText() == null &&
        !widget.conversation.processingDeferred &&
        !_pendingShown;
    return Stack(
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Emoji + Title row
            ConstrainedBox(
              constraints: const BoxConstraints(minHeight: HomeRowShell.contentExtent),
              child: Row(
                crossAxisAlignment: compact ? CrossAxisAlignment.center : CrossAxisAlignment.start,
                children: [
                  if (!discarded) ConversationStateTile(conversation: widget.conversation),
                  if (!discarded) const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          conversationRowTitle(context, widget.conversation),
                          style: Theme.of(context).textTheme.titleMedium,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (discardedSnippet.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            discardedSnippet,
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.35),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                        const SizedBox(height: 3),
                        if (failedRetry)
                          Text(
                            context.l10n.conversationSummaryFailed,
                            key: const Key('conversation_summary_failed_indicator'),
                            style: HomeRowShell.subtitleStyle.copyWith(color: OmiColors.danger),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          )
                        else
                          _buildMetaOrStatus(context),
                        if (widget.conversation.processingDeferred &&
                            widget.conversation.homeStep != 'failed' &&
                            !widget.conversation.isTranscriptionAllowanceHeld)
                          const ProcessingDeferredMarker(),
                        OnDeviceProvenanceChip(conversationId: widget.conversation.id),
                        if (_pendingShown &&
                            !widget.conversation.isTranscriptionAllowanceHeld &&
                            !widget.conversation.isAdmittedForTranscription &&
                            (widget.conversation.showsSummaryRetry || isFailedConversation(widget.conversation)) &&
                            !TranscriptionPendingConversations.replacesTitle(widget.conversation)) ...[
                          const SizedBox(height: 8),
                          _buildTranscriptionPending(context),
                        ],
                        if (_searchSnippetText() != null) ...[
                          const SizedBox(height: 10),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(top: 2),
                                child: Icon(Icons.graphic_eq, size: 14, color: OmiColors.textSecondary),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  _searchSnippetText()!,
                                  style: OmiType.footnote.copyWith(
                                    color: OmiColors.textSecondary,
                                    height: 1.35,
                                    fontStyle: FontStyle.italic,
                                  ),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                  if (failedRetry) ...[
                    const SizedBox(width: 8),
                    Align(
                      heightFactor: 1,
                      child: GestureDetector(
                        onTap: () {}, // absorb so the card's open-on-tap does not fire
                        child: HomeRowAction(
                          key: const Key('conversation_summary_retry_button'),
                          label: context.l10n.retry,
                          busy: _reprocessing,
                          onPressed: _reprocessing ? null : _onReprocess,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }

  List<String> get _captureSources => CaptureGroupPresentation.distinctSources(widget.conversation);

  String? _searchSnippetText() {
    if (widget.conversation.matchSnippets.isEmpty) return null;
    final text = widget.conversation.matchSnippets.first.text.trim();
    if (text.isEmpty) return null;
    return text.replaceAll('\n', ' · ');
  }

  Widget _buildMergingOverlay() {
    return Container(
      width: double.infinity,
      height: double.infinity,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.6), borderRadius: OmiRadius.xlAll),
      child: const MergingIndicator(),
    );
  }

  /// The same length the detail page shows (`OmiDuration.compact`, hub audit #15).
  bool get _isLive => conversationIsLiveIn(context, widget.conversation);

  /// A v3 row that is not done shows one quiet line where its time goes: "Listening · 11m",
  /// "Transcribing…" or "Writing summary…". It cross-fades in place as the conversation moves on.
  Widget _buildMetaOrStatus(BuildContext context) {
    final state = homeTileState(widget.conversation);
    final l10n = context.l10n;
    // One subtitle style for every Home row and state, so a row never changes size as it moves on.
    final style = HomeRowShell.subtitleStyle;
    if (widget.conversation.isTranscriptionAllowanceHeld) {
      return Text(l10n.waitingForTranscriptionAllowance, style: style, maxLines: 1);
    }
    final Widget child = switch (state) {
      // Speech so far, through the same duration authority as the meta row and the detail page
      // (#25725): counting from the start to now would grow it through silence.
      ConversationTileState.live => Builder(
          key: const ValueKey('conversation_row_status_live'),
          builder: (context) {
            final duration = _getConversationDuration(context);
            // Keyed like the meta row's live length: the row's one live length, found the same way.
            // An untitled live row already reads "Listening" as its title: the line under it says Live.
            if (awaitsLiveTitle(widget.conversation, title: widget.conversation.structured.title.decodeString)) {
              return Text([l10n.live, if (duration.isNotEmpty) duration].join(' · '),
                  key: const Key('conversation_row_live_length'), style: style, maxLines: 1);
            }
            return Text(duration.isEmpty ? l10n.listening : l10n.listeningWithDuration(duration),
                key: const Key('conversation_row_live_length'), style: style, maxLines: 1);
          }),
      // Past its deadline a step stops claiming all is well (HomeDeadlines).
      ConversationTileState.transcribing ||
      ConversationTileState.writing when conversationStepOverdue(widget.conversation, clock.now()) =>
        Text(l10n.homeTakingLonger,
            key: const ValueKey('conversation_row_status_overdue'),
            style: style.copyWith(color: OmiColors.warning),
            maxLines: 1),
      ConversationTileState.transcribing => Text(l10n.homeStepTranscribing,
          key: const ValueKey('conversation_row_status_transcribing'), style: style, maxLines: 1),
      ConversationTileState.writing => Text(l10n.writingSummaryStatus,
          key: const ValueKey('conversation_row_status_writing'), style: style, maxLines: 1),
      _ => KeyedSubtree(key: const ValueKey('conversation_row_meta'), child: _buildMetaRow(context)),
    };
    return OmiCrossFade(child: child);
  }

  String _getConversationDuration(BuildContext context) {
    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';
    return OmiDuration.compact(durationSeconds, context.l10n);
  }
}

class ConversationNewStatusIndicator extends StatefulWidget {
  final String text;

  const ConversationNewStatusIndicator({super.key, required this.text});

  @override
  State<ConversationNewStatusIndicator> createState() => _ConversationNewStatusIndicatorState();
}

class _ConversationNewStatusIndicatorState extends State<ConversationNewStatusIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(opacity: _opacityAnim, child: Text(widget.text));
  }
}

/// Animated merging indicator that pulses to show conversations are being merged
class MergingIndicator extends StatefulWidget {
  const MergingIndicator({super.key});

  @override
  State<MergingIndicator> createState() => _MergingIndicatorState();
}

class _MergingIndicatorState extends State<MergingIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(duration: const Duration(milliseconds: 1200), vsync: this)..repeat(reverse: true);
    _opacityAnim = Tween<double>(
      begin: 1.0,
      end: 0.4,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.merge_rounded, color: Colors.white, size: 18),
          const SizedBox(width: 8),
          Text(
            context.l10n.mergingStatus,
            style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
