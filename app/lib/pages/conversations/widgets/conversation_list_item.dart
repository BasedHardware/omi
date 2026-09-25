import 'dart:async';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/extensions/string.dart';

/// The row title for a conversation (hub audit #21): its title, "Untitled Conversation" when the
/// title is blank, and "Discarded · 12s" for a discarded one (its words go in [conversationSnippet]).
String conversationRowTitle(BuildContext context, ServerConversation conversation) {
  final l10n = context.l10n;
  if (conversation.discarded) {
    final seconds = conversation.getDurationInSeconds();
    if (seconds <= 0) return l10n.discardedConversation;
    return l10n.discardedConversationTitle(OmiDuration.compact(seconds, l10n));
  }
  final title = conversation.structured.title.decodeString.trim();
  return title.isEmpty ? l10n.untitledConversation : title;
}

/// A plain-text preview of what was said: the transcript words without timestamps or speaker
/// prefixes, newest last, trimmed to [maxChars] at a word boundary.
String conversationSnippet(ServerConversation conversation, {int maxChars = 160}) {
  final text = conversation.transcriptSegments.map((s) => s.text.trim()).where((t) => t.isNotEmpty).join(' ');
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
  final Future<ServerConversation?> Function(String conversationId)? reprocess;

  /// Whether the long-press menu offers Select (multi-select). Off where no selection bar is shown
  /// (the Home preview), so selection mode can never start without a way to act on it or leave.
  final bool allowSelection;

  const ConversationListItem({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.isFromOnboarding = false,
    this.reprocess,
    this.allowSelection = true,
  });

  @override
  State<ConversationListItem> createState() => _ConversationListItemState();
}

class _ConversationListItemState extends State<ConversationListItem> {
  Timer? _conversationNewStatusResetTimer;
  bool isNew = false;
  bool _reprocessing = false;

  int _visualSignature(ServerConversation conversation) => Object.hash(
        conversation.structured.title,
        conversation.structured.emoji,
        conversation.structured.category,
        conversation.status,
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
      );

  @override
  void dispose() {
    _conversationNewStatusResetTimer?.cancel();
    super.dispose();
  }

  Future<void> _onReprocess() async {
    if (_reprocessing || widget.conversation.id == '0') return;
    setState(() => _reprocessing = true);
    try {
      final reprocess = widget.reprocess ?? reProcessConversationServer;
      final updated = await reprocess(widget.conversation.id);
      if (!mounted) return;
      final provider = context.read<ConversationProvider>();
      if (updated == null) {
        AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
        return;
      }
      provider.applyConversationReprocessResult(updated);
    } catch (_) {
      if (!mounted) return;
      AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _reprocessing = false);
    }
  }

  Widget _buildFailedTitleRecovery(BuildContext context) {
    return Row(
      children: [
        Flexible(
          child: Text(
            context.l10n.conversationTitleDidntGenerate,
            key: const Key('conversation_failed_title_indicator'),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        GestureDetector(
          onTap: () {}, // absorb so the card's open-on-tap does not fire
          child: TextButton(
            key: const Key('conversation_failed_title_reprocess_button'),
            onPressed: _reprocessing ? null : _onReprocess,
            style: TextButton.styleFrom(
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              minimumSize: const Size(44, 44),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child:
                _reprocessing ? const OmiSpinner(size: OmiSpinnerSize.small) : Text(context.l10n.conversationReprocess),
          ),
        ),
      ],
    );
  }

  Future<void> _open(BuildContext context, ConversationProvider provider) async {
    if (widget.conversation.isLocked) {
      if (!context.read<UsageProvider>().showSubscriptionUI) return;
      PlatformManager.instance.analytics.paywallOpened('Conversation List Item');
      routeToPage(context, const UsagePage(showUpgradeDialog: true));
      return;
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
      unawaited(
        SchedulerBinding.instance.scheduleTask<void>(() {
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
        }, Priority.idle),
      );
    });

    final seek = searchMomentSeekFromSnippets(
      snippets: widget.conversation.matchSnippets,
      searchQuery: searchQuery,
    );

    final resultFuture = routeToPage(
      context,
      ConversationDetailPage(
        conversation: widget.conversation,
        isFromOnboarding: widget.isFromOnboarding,
        // Search matches explicitly open Transcript. Other rows
        // let detail choose Transcript for retained fragments that
        // have no generated summary after hydration.
        initialTabIndex: seek != null ? 0 : null,
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
          isMerging: provider.isConversationMerging(widget.conversation.id),
          isEligible: provider.isConversationEligibleForMerge(widget.conversation.id),
        ),
        builder: (context, rowState, child) {
          final provider = context.read<ConversationProvider>();
          final isSelectionMode = rowState.isSelectionMode;
          final isSelected = rowState.isSelected;
          final isMerging = rowState.isMerging;
          final isEligible = rowState.isEligible;

          return GestureDetector(
            onTap: () async {
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
            },
            onLongPress: isSelectionMode || isMerging ? null : () => _showActions(context, provider),
            child: Stack(
              children: [
                Padding(
                  padding: EdgeInsets.only(
                    top: 12,
                    left: widget.isFromOnboarding ? 0 : 16,
                    right: widget.isFromOnboarding ? 0 : 16,
                  ),
                  child: AnimatedOpacity(
                    duration: const Duration(milliseconds: 200),
                    opacity: (isSelectionMode && !isEligible) ? 0.6 : 1.0,
                    child: Semantics(
                      selected: isSelectionMode ? isSelected : null,
                      child: AnimatedContainer(
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
                        child: ClipRRect(
                          borderRadius: OmiRadius.xlAll,
                          child: Dismissible(
                            // Keep the dismissible state stable when the conversation provider
                            // refreshes. A UniqueKey here recreated every row during unrelated
                            // notifications, forcing extra layout/paint work while scrolling.
                            key: ValueKey('conversation_dismissible_${widget.conversation.id}'),
                            direction:
                                isSelectionMode || isMerging ? DismissDirection.none : DismissDirection.endToStart,
                            background: Container(
                              alignment: Alignment.centerRight,
                              padding: const EdgeInsets.only(right: 20.0),
                              color: OmiColors.danger,
                              child: const Icon(Icons.delete, color: Colors.white),
                            ),
                            // One delete path (D5): confirm unless opted out, then Undo.
                            confirmDismiss: (direction) async {
                              HapticFeedback.mediumImpact();
                              trackConversationAction(
                                  ConversationActionAction.delete, ConversationActionSurface.rowSwipe);
                              return confirmConversationDelete(context);
                            },
                            onDismissed: (direction) {
                              final conversation = widget.conversation;
                              PlatformManager.instance.analytics.conversationSwipedToDelete(conversation);
                              unawaited(deleteConversationsWithUndo(context, [conversation]));
                            },
                            child: Padding(
                              padding: PlatformService.isMobile
                                  ? const EdgeInsetsDirectional.symmetric(horizontal: 16, vertical: 20)
                                  : const EdgeInsetsDirectional.all(16),
                              child: PlatformService.isMobile
                                  ? _buildMobileLayout(context)
                                  : Column(
                                      mainAxisSize: MainAxisSize.max,
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        _getConversationHeader(),
                                        const SizedBox(height: 16),
                                        _buildConversationBody(context),
                                        if (widget.conversation.isFailedTitleRecoverable) ...[
                                          const SizedBox(height: 10),
                                          _buildFailedTitleRecovery(context),
                                        ],
                                      ],
                                    ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                // Merging overlay covering the full card
                if (isMerging)
                  Positioned.fill(
                    child: Padding(
                      padding: EdgeInsets.only(
                        top: 12,
                        left: widget.isFromOnboarding ? 0 : 16,
                        right: widget.isFromOnboarding ? 0 : 16,
                      ),
                      child: _buildMergingOverlay(),
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  static const _metaStyle = TextStyle(color: OmiColors.textTertiary, fontSize: 14);

  /// Time and length, with the New badge beside them (hub audit #16) and the star.
  Widget _buildMetaRow(BuildContext context) {
    final duration = _getConversationDuration(context);
    return Row(
      children: [
        Text(
          OmiDateFormat.of(context).time(widget.conversation.startedAt ?? widget.conversation.createdAt),
          style: _metaStyle,
          maxLines: 1,
        ),
        if (duration.isNotEmpty) ...[
          const Text(' • ', style: _metaStyle),
          Text(duration, style: _metaStyle, maxLines: 1),
        ],
        // One row stands for an event several devices recorded.
        if (_captureSources.length > 1) ...[
          const Text(' • ', style: _metaStyle),
          CaptureSourceIcons(sources: _captureSources),
        ],
        if (isNew) ...[
          const SizedBox(width: OmiSpacing.xs),
          ConversationNewStatusIndicator(text: context.l10n.conversationNewIndicator),
        ],
        const Spacer(),
        if (widget.conversation.starred)
          Padding(
            padding: const EdgeInsets.only(right: 4.0),
            child: Semantics(
              label: context.l10n.starred,
              child: const FaIcon(FontAwesomeIcons.solidStar, size: 12, color: Colors.amber),
            ),
          ),
      ],
    );
  }

  Widget _buildMobileLayout(BuildContext context) {
    final discarded = widget.conversation.discarded;
    final discardedSnippet = discarded ? conversationSnippet(widget.conversation) : '';
    return Stack(
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Emoji + Title row
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!discarded)
                  Container(
                    width: 40,
                    height: 40,
                    decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                    alignment: Alignment.center,
                    child: Text(
                      widget.conversation.structured.getEmoji(),
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w500),
                    ),
                  ),
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
                      const SizedBox(height: 8),
                      _buildMetaRow(context),
                      if (widget.conversation.isFailedTitleRecoverable) ...[
                        const SizedBox(height: 8),
                        _buildFailedTitleRecovery(context),
                      ],
                      if (_searchSnippetText() != null) ...[
                        const SizedBox(height: 10),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Padding(
                              padding: EdgeInsets.only(top: 2),
                              child: Icon(Icons.graphic_eq, size: 14, color: Colors.white70),
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
        if (widget.conversation.isLocked) _buildLockedOverlay(),
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

  Widget _buildConversationBody(BuildContext context) {
    if (widget.conversation.discarded) {
      return Stack(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (widget.conversation.photos.isNotEmpty) ...[
                Row(
                  children: [
                    Icon(Icons.photo_library, color: Colors.grey.shade400, size: 18),
                    const SizedBox(width: 12),
                    Text(
                      context.l10n.conversationPhotosCount(widget.conversation.photos.length),
                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
              ],
              Text(
                conversationSnippet(widget.conversation),
                style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
              ),
            ],
          ),
          if (widget.conversation.isLocked) _buildLockedOverlay(),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(conversationRowTitle(context, widget.conversation), style: Theme.of(context).textTheme.titleLarge),
        if (_searchSnippetText() != null) ...[
          const SizedBox(height: 10),
          Text(
            _searchSnippetText()!,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade400, height: 1.35, fontStyle: FontStyle.italic),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }

  Widget _buildLockedOverlay() {
    return Positioned.fill(
      child: ClipRRect(
        child: Container(
          alignment: Alignment.center,
          decoration: BoxDecoration(
            // Avoid a live backdrop blur for every locked card. The opaque overlay
            // preserves the locked affordance without making the scroll/route paint
            // path sample and blur the entire card behind it.
            color: Colors.black.withValues(alpha: 0.62),
            borderRadius: OmiRadius.smAll,
          ),
          child: Text(
            context.l10n.upgradeToUnlimited,
            style: OmiType.callout.copyWith(fontWeight: FontWeight.bold),
          ),
        ),
      ),
    );
  }

  _getConversationHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // 🧠 Emoji + Tag
          Flexible(
            fit: FlexFit.tight,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!widget.conversation.discarded)
                  Text(
                    widget.conversation.structured.getEmoji(),
                    style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w500),
                  ),
                if (widget.conversation.structured.category.isNotEmpty && !widget.conversation.discarded)
                  const SizedBox(width: 8),
                if (widget.conversation.structured.category.isNotEmpty)
                  Flexible(
                    child: Container(
                      decoration:
                          BoxDecoration(color: widget.conversation.getTagColor(), borderRadius: OmiRadius.lgAll),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: Text(
                        widget.conversation.getTag(),
                        style: Theme.of(
                          context,
                        ).textTheme.bodyMedium!.copyWith(color: widget.conversation.getTagTextColor()),
                        overflow: TextOverflow.ellipsis,
                        maxLines: 1,
                      ),
                    ),
                  ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          // 🕒 Timestamp + Duration, New badge beside them, Starred
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  OmiDateFormat.of(context).time(widget.conversation.startedAt ?? widget.conversation.createdAt),
                  style: _metaStyle,
                  maxLines: 1,
                ),
                if (_getConversationDuration(context).isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                      child: Text(_getConversationDuration(context), style: OmiType.caption, maxLines: 1),
                    ),
                  ),
                if (isNew) ...[
                  const SizedBox(width: 8),
                  ConversationNewStatusIndicator(text: context.l10n.conversationNewIndicator),
                ],
                if (widget.conversation.starred)
                  const Padding(
                    padding: EdgeInsets.only(left: 8.0),
                    child: FaIcon(FontAwesomeIcons.solidStar, size: 12, color: Colors.amber),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// The same length the detail page shows (`OmiDuration.compact`, hub audit #15).
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
