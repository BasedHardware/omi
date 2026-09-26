import 'dart:async';
import 'dart:ui' as ui;

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

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

/// Where a row sits in its day's card (v2 draws one card per day, rows separated by hairlines).
enum ConversationRowPosition {
  only,
  first,
  middle,
  last;

  bool get isFirst => this == only || this == first;
  bool get isLast => this == only || this == last;
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

  /// The row's place in its day card; a lone row is a whole card.
  final ConversationRowPosition position;

  const ConversationListItem({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.isFromOnboarding = false,
    this.reprocess,
    this.allowSelection = true,
    this.position = ConversationRowPosition.only,
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
              foregroundColor: OmiColors.textPrimary,
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
    OmiHaptics.selection();
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
        ConversationRowAction.star => starred ? ConversationActionAction.unstar : ConversationActionAction.star,
        ConversationRowAction.move => ConversationActionAction.moveFolder,
        ConversationRowAction.share => ConversationActionAction.share,
        ConversationRowAction.copySummary => ConversationActionAction.copySummary,
        ConversationRowAction.recordings => ConversationActionAction.recordingsOpen,
        ConversationRowAction.separate => ConversationActionAction.separate,
        ConversationRowAction.select => ConversationActionAction.select,
        ConversationRowAction.delete => ConversationActionAction.delete,
      };

  /// Long-press: the row's one context menu (hub audit #7, v2 ContextMenu), opening under the row.
  /// Merging (multi-select) is one of its entries.
  Future<void> _showActions(BuildContext context, ConversationProvider provider) async {
    final conversation = widget.conversation;
    final box = context.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    final action = await showConversationRowMenu(
      context,
      conversation,
      anchor: box.localToGlobal(Offset.zero) & box.size,
      canSelect: widget.allowSelection && provider.isConversationEligibleForMerge(conversation.id),
    );
    if (action == null || !context.mounted) return;
    trackConversationAction(_rowActionAnalytics(action, conversation.starred), ConversationActionSurface.rowLongPress);
    switch (action) {
      case ConversationRowAction.star:
        await toggleConversationStarred(context, conversation);
      case ConversationRowAction.move:
        await moveConversationToFolder(context, conversation);
      case ConversationRowAction.share:
        await shareConversation(context, conversation);
      case ConversationRowAction.copySummary:
        await copyConversationSummary(context, conversation);
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
                  OmiHaptics.light();
                  OmiFeedback.info(context, context.l10n.conversationCannotBeMerged);
                  return;
                }
                OmiHaptics.selection();
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
                    top: widget.position.isFirst ? OmiSpacing.xs : 0,
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
                          borderRadius: _cardRadius,
                          border: isSelected
                              ? Border.all(color: OmiColors.accent, width: 2)
                              : (isSelectionMode && !isEligible)
                                  ? Border.all(color: OmiColors.border, width: 1)
                                  : null,
                        ),
                        child: ClipRRect(
                          borderRadius: _cardRadius,
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
                              OmiHaptics.medium();
                              trackConversationAction(
                                  ConversationActionAction.delete, ConversationActionSurface.rowSwipe);
                              return confirmConversationDelete(context);
                            },
                            onDismissed: (direction) {
                              final conversation = widget.conversation;
                              PlatformManager.instance.analytics.conversationSwipedToDelete(conversation);
                              unawaited(deleteConversationsWithUndo(context, [conversation]));
                            },
                            child: Container(
                              // v2: hairline between rows of the same day card.
                              decoration: widget.position.isFirst
                                  ? null
                                  : BoxDecoration(
                                      border: Border(top: BorderSide(color: OmiColors.border, width: 0.5)),
                                    ),
                              // The app is mobile-only (PlatformService): one layout.
                              padding: const EdgeInsetsDirectional.symmetric(horizontal: 16, vertical: 14),
                              child: _buildMobileLayout(context),
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
                        top: widget.position.isFirst ? OmiSpacing.xs : 0,
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

  /// Rounded only on the outside of the day card (v2 `card` radius).
  BorderRadius get _cardRadius => BorderRadius.vertical(
        top: widget.position.isFirst ? const Radius.circular(OmiRadius.card) : Radius.zero,
        bottom: widget.position.isLast ? const Radius.circular(OmiRadius.card) : Radius.zero,
      );

  static TextStyle get _metaStyle => OmiType.footnote.copyWith(color: OmiColors.textTertiary);

  /// Time and length, with the New badge beside them (hub audit #16) and the star.
  /// Length, tasks and capture sources, with the New badge and the star (the time is the row's
  /// left column in v2).
  Widget _buildMetaRow(BuildContext context) {
    final duration = _getConversationDuration(context);
    final tasks = widget.conversation.structured.actionItems.length;
    final photos = widget.conversation.photos.length;
    final category = widget.conversation.structured.category.trim();
    Widget part(IconData icon, String text) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ExcludeSemantics(child: Icon(icon, size: 12, color: OmiColors.textTertiary)),
            const SizedBox(width: 3),
            Text(text, style: _metaStyle, maxLines: 1),
          ],
        );
    // Rev 3: every row says which device heard it ("Pendant · 14 s"); an event several devices
    // recorded shows their icons at the end instead.
    final source = _captureSources.length > 1 ? null : widget.conversation.source?.name;
    final parts = <Widget>[
      // The category alone: the source has its own part (getTag names some devices instead).
      if (category.isNotEmpty && !widget.conversation.discarded)
        part(Icons.sell_outlined, category[0].toUpperCase() + category.substring(1)),
      if (source != null) part(CaptureSources.icon(source), CaptureSources.label(context, source)),
      if (duration.isNotEmpty) part(Icons.schedule_rounded, duration),
      if (photos > 0) part(Icons.photo_outlined, context.l10n.conversationPhotosCount(photos)),
      if (tasks > 0) part(Icons.checklist_rounded, context.l10n.tasksCountLabel(tasks)),
      // One row stands for an event several devices recorded.
      if (_captureSources.length > 1) CaptureSourceIcons(sources: _captureSources),
    ];
    // The parts take the whole width (a Spacer beside them would halve it and wrap early); the New
    // badge follows the last part and the star sits at the end.
    return Row(
      children: [
        Expanded(
          child: Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (var i = 0; i < parts.length; i++) ...[
                if (i > 0) Text('  ·  ', style: _metaStyle),
                parts[i],
              ],
              if (isNew) ...[
                const SizedBox(width: OmiSpacing.xs),
                ConversationNewStatusIndicator(text: context.l10n.conversationNewIndicator),
              ],
            ],
          ),
        ),
        if (widget.conversation.starred)
          Padding(
            padding: const EdgeInsets.only(right: 4.0),
            child: Semantics(
              label: context.l10n.starred,
              child: FaIcon(FontAwesomeIcons.solidStar, size: 12, color: OmiColors.warning),
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
            // v2: the start time is the row's left column; title, summary and meta on the right.
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 52,
                  child: _TimeColumn(
                    OmiDateFormat.of(context).time(widget.conversation.startedAt ?? widget.conversation.createdAt),
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Text(
                              conversationRowTitle(context, widget.conversation),
                              style: OmiType.headline.copyWith(
                                color: discarded ? OmiColors.textSecondary : OmiColors.textPrimary,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (!widget.conversation.isLocked)
                            ExcludeSemantics(
                              child: Icon(Icons.chevron_right, size: 18, color: OmiColors.textTertiary),
                            ),
                        ],
                      ),
                      if (widget.conversation.isLocked) ...[
                        const SizedBox(height: 4),
                        _LockedSummary(overview: widget.conversation.structured.overview),
                      ] else if (!discarded && widget.conversation.structured.overview.trim().isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          OmiPlainText.fromMarkdown(widget.conversation.structured.overview),
                          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.3),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
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
      decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.6), borderRadius: _cardRadius),
      child: const MergingIndicator(),
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
          Icon(Icons.merge_rounded, color: OmiColors.textPrimary, size: 18),
          const SizedBox(width: 8),
          Text(
            context.l10n.mergingStatus,
            style: TextStyle(color: OmiColors.textPrimary, fontSize: 14, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

/// v2 time column: the clock digits in bold, with any day-period marker ("PM", "오후") on a small
/// second line, whichever side of the digits the locale puts it. A 24-hour time is one line.
class _TimeColumn extends StatelessWidget {
  const _TimeColumn(this.formatted);

  final String formatted;

  static final RegExp _digits = RegExp(r'\d{1,2}[:.]\d{2}');

  @override
  Widget build(BuildContext context) {
    final match = _digits.firstMatch(formatted);
    final digits = match?.group(0) ?? formatted;
    final period = match == null ? '' : formatted.replaceRange(match.start, match.end, '').trim();
    return Semantics(
      label: formatted,
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(digits, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w700), maxLines: 1),
          if (period.isNotEmpty)
            Text(period, style: OmiType.caption.copyWith(color: OmiColors.textTertiary), maxLines: 1),
        ],
      ),
    );
  }
}

/// A locked conversation's summary (over the plan's minutes): its words blurred, never readable,
/// under a small lock badge naming the plan that opens it. The title, time and length stay as they
/// are, so the row still says what it was. The blur is the text's own layer (no backdrop sampling),
/// so a list full of locked rows scrolls as smoothly as any other.
class _LockedSummary extends StatelessWidget {
  const _LockedSummary({required this.overview});

  final String overview;

  @override
  Widget build(BuildContext context) {
    final text = OmiPlainText.fromMarkdown(overview).trim();
    final Widget words = text.isEmpty
        // Nothing sent for a locked row: two lines' worth of shape to blur instead.
        ? Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final width in const [1.0, 0.62])
                FractionallySizedBox(
                  widthFactor: width,
                  child: Container(
                    height: 10,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    decoration: BoxDecoration(
                        color: OmiColors.textTertiary.withValues(alpha: 0.45), borderRadius: OmiRadius.pillAll),
                  ),
                ),
            ],
          )
        : Text(
            text,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.3),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          );
    return Semantics(
      label: context.l10n.upgradeToUnlimited,
      child: Stack(
        alignment: Alignment.center,
        children: [
          ExcludeSemantics(
            child: ImageFiltered(
              imageFilter: ui.ImageFilter.blur(sigmaX: 5, sigmaY: 5, tileMode: TileMode.decal),
              child: Opacity(opacity: 0.8, child: words),
            ),
          ),
          const _UnlimitedBadge(),
        ],
      ),
    );
  }
}

/// The small lock badge on a locked summary: a frosted capsule with the plan's name.
class _UnlimitedBadge extends StatelessWidget {
  const _UnlimitedBadge();

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        key: const Key('conversation_locked_badge'),
        height: 26,
        padding: const EdgeInsets.fromLTRB(8, 0, 10, 0),
        decoration: BoxDecoration(
          color: OmiColors.surface1.withValues(alpha: 0.92),
          borderRadius: OmiRadius.pillAll,
          border: Border.all(color: OmiColors.border, width: 0.5),
          boxShadow: [BoxShadow(color: OmiColors.shadowSoft, blurRadius: 8, offset: const Offset(0, 2))],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.lock_outline_rounded, size: 13, color: OmiColors.textPrimary),
            const SizedBox(width: 5),
            Text(context.l10n.unlimitedBadge, style: OmiType.caption1.copyWith(fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}
