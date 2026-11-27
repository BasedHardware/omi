import 'dart:async';
import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversation_detail/conversation_live_guard.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/on_device/on_device_provenance_section.dart';
import 'package:omi/pages/paywall/value_moment_paywall.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/held_audio/processing_backlog_view.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
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

  /// Drawn inside a [LockedConversationRun]: the run blurs the card under its one usage action,
  /// so the row draws no padding or lock of its own but keeps its gestures (open, long-press menu,
  /// swipe-to-delete, selection).
  final bool inLockedRun;

  /// Parent supplies outer spacing, while normal lock and row interactions remain intact.
  final bool embedded;

  /// Seconds of audio offline sync is still adding to this conversation (episodes on). The row
  /// says so with a small spinner instead of a separate "catching up" row.
  final int? fillingSeconds;

  /// Closed episode projection, drawn by the same conversation row widget.
  final Episode? homeEpisode;
  final HomeFeedCard? homeCard;
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
    this.inLockedRun = false,
    this.embedded = false,
    this.fillingSeconds,
    this.homeEpisode,
    this.homeCard,
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
        widget.fillingSeconds,
        widget.homeEpisode?.members.length,
        widget.homeCard?.revision,
        widget.homeCard?.preview,
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

  /// "Summary failed · Retry": shown only when the server says a reprocess can succeed. A row the
  /// server said is still awaiting transcription gets a plain waiting status and no retry.
  Widget _buildSummaryRetry(BuildContext context) {
    if (_pendingShown) {
      return Text(
        context.l10n.summaryTranscriptionPendingTitle,
        key: const Key('conversation_transcription_pending_indicator'),
        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      );
    }
    return Row(
      children: [
        Flexible(
          child: Text(
            context.l10n.conversationSummaryFailed,
            key: const Key('conversation_summary_failed_indicator'),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        GestureDetector(
          onTap: () {}, // absorb so the card's open-on-tap does not fire
          child: TextButton(
            key: const Key('conversation_summary_retry_button'),
            onPressed: _reprocessing ? null : _onReprocess,
            style: TextButton.styleFrom(
              foregroundColor: OmiColors.textPrimary,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              minimumSize: const Size(44, 44),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: _reprocessing ? const OmiSpinner(size: OmiSpinnerSize.small) : Text(context.l10n.retry),
          ),
        ),
      ],
    );
  }

  Future<void> _open(BuildContext context, ConversationProvider provider) async {
    if (widget.conversation.isLocked) {
      if (!context.read<UsageProvider>().showSubscriptionUI) return;
      openHeldAudioPlans(context);
      return;
    }
    if (widget.homeCard case final card? when card.kind == 'episode') {
      await routeToPage(context, EpisodePage(episode: card.episodeSeed(), displaySeedOnly: true));
      if (context.mounted) unawaited(context.read<HomeFeedProvider?>()?.refresh());
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
      if (widget.homeCard != null) unawaited(context.read<HomeFeedProvider?>()?.refresh());
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
    var conversation = widget.conversation;
    if (widget.homeCard != null) {
      final result = await getConversationByIdResult(conversation.id, userInitiated: true);
      if (!context.mounted) return;
      if (!result.ok || result.item == null) {
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
        return;
      }
      conversation = result.item!;
    }
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
    bool? linked = widget.homeCard?.hasTasks ?? widget.hasLinkedTasks;
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
              widget.homeCard?.kind != 'episode' &&
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
            onLongPress: isSelectionMode ||
                    isMerging ||
                    _isLive ||
                    (widget.homeEpisode != null || widget.homeCard?.kind == 'episode')
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
                      child: _SwipeDeleteRow(
                        enabled: !isSelectionMode &&
                            !isMerging &&
                            !_isLive &&
                            widget.homeEpisode == null &&
                            widget.homeCard?.kind != 'episode',
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
                                    : (ExperimentalDesign.of(context) ? Colors.transparent : OmiColors.surface1),
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

  /// A row inside a [LockedConversationRun] takes its outer spacing from the run.
  EdgeInsets get _cardPadding {
    if (widget.inLockedRun || widget.embedded) return EdgeInsets.zero;
    final side = widget.isFromOnboarding ? 0.0 : 16.0;
    return EdgeInsets.only(top: 8, left: side, right: side);
  }

  TextStyle get _metaStyle =>
      TextStyle(color: OmiColors.textTertiary, fontSize: ExperimentalDesign.of(context) ? 15 : 14);

  Widget _buildCardContent(BuildContext context, Future<void> Function() onTap) {
    final content = Padding(
      padding: ExperimentalDesign.of(context)
          ? const EdgeInsetsDirectional.symmetric(horizontal: 4, vertical: 6)
          : const EdgeInsetsDirectional.symmetric(horizontal: 14, vertical: 14),
      child: _buildMobileLayout(context),
    );
    // A run frosts its rows together under one action.
    if (!widget.conversation.isLocked || widget.inLockedRun) return content;
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
              if (widget.homeCard == null || widget.homeCard!.startedAt != null)
                Text(
                  OmiDateFormat.of(context).time(widget.conversation.startedAt ?? widget.conversation.createdAt),
                  style: _metaStyle,
                  maxLines: 1,
                ),
              if (_isLive) ...[
                // The conversation in progress shows its speech so far, through the same duration
                // authority as its detail. Counting from its start to now grew it through silence.
                if (duration.isNotEmpty)
                  Text('• $duration', key: const Key('conversation_row_live_length'), style: _metaStyle, maxLines: 1),
              ] else if (duration.isNotEmpty)
                Text('• $duration', style: _metaStyle, maxLines: 1),
              if (widget.homeCard?.memberCount case final count? when count > 1)
                Text(context.l10n.homeRecordingsCount(count), style: _metaStyle),
              if (widget.homeCard?.homeStep == 'transcribing') ...[
                const OmiActivityRing.inline(),
                Text(context.l10n.homeStepTranscribing, style: _metaStyle),
              ],
              if (widget.homeCard?.homeStep == 'writing_notes') ...[
                const OmiActivityRing.inline(),
                Text(context.l10n.episodeWritingNotes, style: _metaStyle),
              ],
              if (_hasLinkedTasks)
                Semantics(
                  key: const ValueKey('conversation_has_tasks'),
                  label: context.l10n.hasLinkedTasksLabel,
                  excludeSemantics: true,
                  child: Icon(Icons.checklist_rounded, size: 16, color: OmiColors.textSecondary),
                ),
              if (widget.fillingSeconds case final seconds?) ...[
                OmiActivityRing.inline(color: _metaStyle.color),
                Text(
                  context.l10n.episodeAddingFromOmi(
                      OmiDuration.compact(seconds < 60 ? seconds : (seconds ~/ 60) * 60, context.l10n)),
                  key: const Key('conversation_row_filling'),
                  style: _metaStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
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
    final discardedSnippet = widget.homeCard?.preview ??
        (discarded || widget.conversation.processingDeferred ? conversationSnippet(widget.conversation) : '');
    return Stack(
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Emoji + Title row
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!discarded) ConversationStateTile(conversation: widget.conversation),
                if (!discarded) const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.homeCard != null &&
                                widget.homeCard!.startedAt == null &&
                                widget.conversation.structured.title.trim().isEmpty
                            ? context.l10n.recording
                            : conversationRowTitle(context, widget.conversation),
                        style: experimentalRowTitleStyle(context),
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
                      SizedBox(height: ExperimentalDesign.of(context) ? 1 : 3),
                      _buildMetaOrStatus(context),
                      if (widget.conversation.processingDeferred &&
                          widget.conversation.homeStep != 'failed' &&
                          !widget.conversation.isTranscriptionAllowanceHeld)
                        const ProcessingDeferredMarker(),
                      OnDeviceProvenanceChip(conversationId: widget.conversation.id),
                      if (!widget.conversation.isTranscriptionAllowanceHeld &&
                          !widget.conversation.isAdmittedForTranscription &&
                          (widget.conversation.showsSummaryRetry || isFailedConversation(widget.conversation)) &&
                          !TranscriptionPendingConversations.replacesTitle(widget.conversation)) ...[
                        const SizedBox(height: 8),
                        _buildSummaryRetry(context),
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
              ],
            ),
          ],
        ),
      ],
    );
  }

  List<String> get _captureSources =>
      widget.homeCard?.sources ?? CaptureGroupPresentation.distinctSources(widget.conversation);

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
    final v3 = context.select<ConversationsV3Provider?, bool>((p) => p?.v3 ?? false);
    final state = v3 ? widget.conversation.v3?.tileState : null;
    final l10n = context.l10n;
    final style =
        (ExperimentalDesign.of(context) ? OmiType.subhead : OmiType.footnote).copyWith(color: OmiColors.textSecondary);
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
      ConversationTileState.transcribing => Text(l10n.homeStepTranscribing,
          key: const ValueKey('conversation_row_status_transcribing'), style: style, maxLines: 1),
      ConversationTileState.writing => Text(l10n.writingSummaryStatus,
          key: const ValueKey('conversation_row_status_writing'), style: style, maxLines: 1),
      _ => KeyedSubtree(key: const ValueKey('conversation_row_meta'), child: _buildMetaRow(context)),
    };
    return OmiCrossFade(child: child);
  }

  String _getConversationDuration(BuildContext context) {
    if (widget.homeCard != null && widget.homeCard!.startedAt == null) return '';
    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';
    return OmiDuration.compact(durationSeconds, context.l10n);
  }
}

/// A conversation card that swipes open to a round red delete button (#20038).
///
/// A short swipe leaves the row open with the button showing; tapping it asks [confirm], whose menu
/// pops from the button. A swipe past [_askAt] of the row's width opens the row and asks straight
/// away, as the old swipe-to-delete did. Tapping the open card, swiping it back or scrolling the list
/// closes it. Once [confirm] says yes, the card slides away and [onDeleted] runs.
class _SwipeDeleteRow extends StatefulWidget {
  const _SwipeDeleteRow({required this.enabled, required this.confirm, required this.onDeleted, required this.child});

  final bool enabled;

  /// Asks to delete; [anchor] is the delete button's rect on screen.
  final Future<bool> Function(Rect anchor) confirm;
  final VoidCallback onDeleted;
  final Widget child;

  @override
  State<_SwipeDeleteRow> createState() => _SwipeDeleteRowState();
}

class _SwipeDeleteRowState extends State<_SwipeDeleteRow> with SingleTickerProviderStateMixin {
  static const double _button = 44;
  static const double _inset = 16;

  /// How far the card rests open: the button and the air on either side of it.
  static const double _open = _button + 2 * _inset;

  /// Past this share of the row's width, letting go asks straight away.
  static const double _askAt = 0.4;

  /// How far the card is pulled aside, in logical pixels.
  AnimationController? _offsetController;
  AnimationController get _offset => _offsetController ??= AnimationController.unbounded(vsync: this);
  final GlobalKey _buttonKey = GlobalKey();
  ValueListenable<bool>? _scrolling;
  double _width = 0;
  bool _asking = false;

  bool get _rtl => Directionality.of(context) == TextDirection.rtl;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final scrolling = Scrollable.maybeOf(context)?.position.isScrollingNotifier;
    if (scrolling != _scrolling) {
      _scrolling?.removeListener(_onScroll);
      _scrolling = scrolling?..addListener(_onScroll);
    }
  }

  @override
  void didUpdateWidget(_SwipeDeleteRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.enabled && _offset.value != 0) _settle(0);
  }

  @override
  void dispose() {
    _scrolling?.removeListener(_onScroll);
    // Never create the controller here: a row that was never swiped has no ticker left to give it.
    _offsetController?.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrolling!.value && !_asking && _offset.value > 0) _settle(0);
  }

  Future<void> _settle(double to) =>
      _offset.animateTo(to, duration: OmiMotion.of(context).standard, curve: Curves.easeOutCubic);

  void _onDragUpdate(DragUpdateDetails details) {
    if (_asking) return;
    final delta = _rtl ? details.primaryDelta! : -details.primaryDelta!;
    _offset.value = (_offset.value + delta).clamp(0.0, _width);
  }

  void _onDragEnd(DragEndDetails details) {
    if (_asking) return;
    final velocity = _rtl ? details.primaryVelocity! : -details.primaryVelocity!;
    if (_offset.value >= _width * _askAt) {
      _settle(_open);
      _ask();
      return;
    }
    final open = velocity > 300 || (velocity > -300 && _offset.value > _open / 2);
    _settle(open ? _open : 0);
  }

  Future<void> _ask() async {
    final box = _buttonKey.currentContext?.findRenderObject() as RenderBox?;
    if (_asking || box == null) return;
    _asking = true;
    final confirmed = await widget.confirm(box.localToGlobal(Offset.zero) & box.size);
    if (!mounted) return;
    _asking = false;
    if (!confirmed) {
      _settle(0);
      return;
    }
    await _offset.animateTo(_width, duration: OmiMotion.of(context).quick, curve: Curves.easeIn);
    if (!mounted) return;
    widget.onDeleted();
    // The list drops the row in the next frame; if it is still here after that, show it closed.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _offset.value = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        _width = constraints.maxWidth;
        return GestureDetector(
          onHorizontalDragUpdate: widget.enabled ? _onDragUpdate : null,
          onHorizontalDragEnd: widget.enabled ? _onDragEnd : null,
          child: Stack(
            children: [
              if (widget.enabled)
                Positioned.fill(
                  child: Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: Padding(
                      padding: const EdgeInsetsDirectional.only(end: _inset),
                      child: AnimatedBuilder(
                        animation: _offset,
                        builder: (context, child) {
                          final t = Curves.easeOut.transform((_offset.value / _open).clamp(0.0, 1.0));
                          return Opacity(
                            opacity: t,
                            child: Transform.scale(scale: 0.6 + 0.4 * t, child: child),
                          );
                        },
                        child: Semantics(
                          button: true,
                          label: context.l10n.delete,
                          child: GestureDetector(
                            key: _buttonKey,
                            behavior: HitTestBehavior.opaque,
                            onTap: _ask,
                            child: Container(
                              key: const ValueKey('conversation_swipe_delete'),
                              width: _button,
                              height: _button,
                              decoration: BoxDecoration(color: OmiColors.danger, shape: BoxShape.circle),
                              child: const FaIcon(FontAwesomeIcons.trashCan, size: 17, color: Colors.white),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              AnimatedBuilder(
                animation: _offset,
                builder: (context, child) => Transform.translate(
                  offset: Offset(_rtl ? _offset.value : -_offset.value, 0),
                  child: Stack(
                    children: [
                      child!,
                      // While open, a tap on the card closes it instead of opening the conversation.
                      if (_offset.value > 0)
                        Positioned.fill(
                          child: GestureDetector(behavior: HitTestBehavior.opaque, onTap: () => _settle(0)),
                        ),
                    ],
                  ),
                ),
                child: widget.child,
              ),
            ],
          ),
        );
      },
    );
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

/// Two or more locked rows in a row on the free plan: one frosted card holding all of them, with a
/// single usage action instead of one per row. A lone locked row stays a
/// [ConversationListItem] with its own [OmiLockedPreview].
class LockedConversationRun extends StatelessWidget {
  const LockedConversationRun({super.key, required this.conversations, required this.date});

  final List<ServerConversation> conversations;
  final DateTime date;

  Future<void> _openUsage(BuildContext context) async {
    // Same as a lone locked row's action: while merging, a locked row can't be picked.
    if (context.read<ConversationProvider>().isSelectionModeActive) {
      HapticFeedback.lightImpact();
      OmiFeedback.info(context, context.l10n.conversationCannotBeMerged);
      return;
    }
    if (!context.read<UsageProvider>().showSubscriptionUI) return;
    openHeldAudioPlans(context);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: OmiLockedPreview(
        key: const Key('locked_conversation_run'),
        // Each row keeps its own long-press menu, swipe-to-delete and selection handling.
        interactive: true,
        label: context.l10n.upgrade,
        onPressed: () => _openUsage(context),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (index, conversation) in conversations.indexed) ...[
              if (index > 0) const SizedBox(height: 8),
              ConversationListItem(
                key: ValueKey('locked_${conversation.id}'),
                conversation: conversation,
                date: date,
                conversationIdx: -1,
                inLockedRun: true,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
