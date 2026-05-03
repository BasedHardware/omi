import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/theme/app_theme.dart';

final _detailDateFormat = DateFormat('EEEE, MMM d · h:mm a');
final _decisionDueDateFormat = DateFormat('EEE MMM d');

/// Conversation detail screen — title, when, overview, decisions (when the
/// backend extracted any), action items, and transcript segments. Pushed by
/// the Meetings list and by the "View conversation" affordance on a memory
/// row.
///
/// Stateful so the Decisions section can light up matched action-item rows
/// briefly after the user taps "View N related actions". The action-items
/// list rendering is lifted into this widget's build so the highlight state
/// can flow down without an extra widget seam.
class ConversationDetailScreen extends StatefulWidget {
  const ConversationDetailScreen({super.key, required this.item});

  final ConversationItem item;

  @override
  State<ConversationDetailScreen> createState() => _ConversationDetailScreenState();
}

class _ConversationDetailScreenState extends State<ConversationDetailScreen> {
  /// Positional indexes into the action_items list that should be visually
  /// tinted right now (post-tap on a "View N related actions" link). Cleared
  /// after ~1500ms; reduced-motion skips it entirely.
  final Set<int> _highlightedActionItemIndexes = <int>{};

  /// Anchor for `Scrollable.ensureVisible` when the user taps "View N related
  /// actions". Attached to the ACTION ITEMS section header.
  final GlobalKey _actionItemsHeaderKey = GlobalKey();

  Future<void> _scrollAndHighlight(List<int> indexes) async {
    final headerCtx = _actionItemsHeaderKey.currentContext;
    if (headerCtx != null) {
      await Scrollable.ensureVisible(
        headerCtx,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
        alignment: 0,
      );
    }
    if (!mounted) return;
    // Reduced motion: scroll only, skip the tint.
    final reducedMotion = MediaQuery.of(context).disableAnimations;
    if (reducedMotion) return;
    setState(() {
      _highlightedActionItemIndexes
        ..clear()
        ..addAll(indexes);
    });
    await Future<void>.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;
    setState(() {
      _highlightedActionItemIndexes.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final raw = item.raw;
    final structured = raw['structured'] is Map
        ? Map<String, dynamic>.from(raw['structured'] as Map)
        : const <String, dynamic>{};
    final actionItems = structured['action_items'] is List
        ? List<Map<String, dynamic>>.from(
            (structured['action_items'] as List).whereType<Map>().map((e) => Map<String, dynamic>.from(e)),
          )
        : const <Map<String, dynamic>>[];
    final segments = raw['transcript_segments'] is List
        ? List<Map<String, dynamic>>.from(
            (raw['transcript_segments'] as List).whereType<Map>().map((e) => Map<String, dynamic>.from(e)),
          )
        : const <Map<String, dynamic>>[];

    final decisions = item.decisions;
    final showDecisionsSection = item.hasDecisionsField;

    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: AppColors.backgroundPrimary,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(
          item.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(AppStyles.spacingL, 0, AppStyles.spacingL, AppStyles.spacingXL),
        children: [
          if (item.createdAt != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppStyles.spacingM),
              child: Text(
                _detailDateFormat.format(item.createdAt!),
                style: const TextStyle(fontSize: 13, color: AppColors.textTertiary),
              ),
            ),
          if (item.overview.trim().isNotEmpty) ...[
            const _SectionHeader(label: 'OVERVIEW'),
            const SizedBox(height: AppStyles.spacingS),
            Text(
              item.overview.trim(),
              style: const TextStyle(fontSize: 15, color: AppColors.textSecondary, height: 1.5),
            ),
            const SizedBox(height: AppStyles.spacingXL),
          ],
          if (showDecisionsSection) ...[
            DecisionsSection(
              decisions: decisions,
              actionItemCount: actionItems.length,
              onViewRelatedActions: _scrollAndHighlight,
            ),
            const SizedBox(height: AppStyles.spacingXL),
          ],
          if (actionItems.isNotEmpty) ...[
            _SectionHeader(label: 'ACTION ITEMS', anchorKey: _actionItemsHeaderKey),
            const SizedBox(height: AppStyles.spacingS),
            for (var i = 0; i < actionItems.length; i++)
              _ActionItemRow(action: actionItems[i], highlighted: _highlightedActionItemIndexes.contains(i)),
            const SizedBox(height: AppStyles.spacingXL),
          ],
          if (segments.isNotEmpty) ...[
            const _SectionHeader(label: 'TRANSCRIPT'),
            const SizedBox(height: AppStyles.spacingS),
            for (final s in segments) _SegmentRow(segment: s),
          ] else
            const Padding(
              padding: EdgeInsets.symmetric(vertical: AppStyles.spacingL),
              child: Text(
                'No transcript captured for this conversation.',
                style: TextStyle(fontSize: 13, color: AppColors.textTertiary),
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label, this.anchorKey});
  final String label;
  final Key? anchorKey;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      key: anchorKey,
      style: const TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: AppColors.textTertiary,
        letterSpacing: 0.8,
      ),
    );
  }
}

/// DECISIONS section. Single chromed surface card per DESIGN.md card grammar
/// — divider-separated decision rows live INSIDE one container, never one
/// surface card per decision (stacking surface cards is a hard rejection).
///
/// Renders one of two states based on `decisions.isEmpty`:
///   * non-empty: eyebrow + per-decision rows separated by 1px dividers
///   * empty: eyebrow + a single muted caption ("No decisions extracted from
///     this meeting") — appears when the backend extraction ran but produced
///     nothing. The parent gates on `hasDecisionsField` so this only shows
///     for allowlisted users.
class DecisionsSection extends StatelessWidget {
  const DecisionsSection({
    super.key,
    required this.decisions,
    required this.actionItemCount,
    required this.onViewRelatedActions,
  });

  final List<DecisionItem> decisions;
  final int actionItemCount;

  /// Called when the user taps "View N related actions" on a decision row.
  /// The parent screen scrolls the Action Items section to the top of the
  /// viewport and briefly tints the matched rows.
  final Future<void> Function(List<int> indexes) onViewRelatedActions;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      padding: const EdgeInsets.all(AppStyles.spacingL),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l.decisionsSection,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: AppColors.textTertiary,
              letterSpacing: 0.8,
            ),
          ),
          if (decisions.isEmpty) ...[
            const SizedBox(height: AppStyles.spacingM),
            Text(
              l.decisionsEmptyForMeeting,
              style: const TextStyle(fontSize: 13, color: AppColors.textTertiary, height: 1.4),
            ),
          ] else ...[
            const SizedBox(height: AppStyles.spacingM),
            for (var i = 0; i < decisions.length; i++) ...[
              _DecisionRow(
                decision: decisions[i],
                actionItemCount: actionItemCount,
                onViewRelatedActions: onViewRelatedActions,
              ),
              if (i < decisions.length - 1)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
                  child: Container(height: 1, color: Colors.white.withValues(alpha: 0.06)),
                ),
            ],
          ],
        ],
      ),
    );
  }
}

class _DecisionRow extends StatelessWidget {
  const _DecisionRow({required this.decision, required this.actionItemCount, required this.onViewRelatedActions});

  final DecisionItem decision;
  final int actionItemCount;
  final Future<void> Function(List<int> indexes) onViewRelatedActions;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final caption = _ownerDueCaption(l, decision);
    final questions = decision.openQuestions;
    final visibleQuestions = questions.length > 3 ? questions.take(3).toList() : questions;
    final overflow = questions.length > 3 ? questions.length - 3 : 0;
    // Filter related ids to ones that are positional-valid given current
    // action_items length. Stops a stale index from causing a no-op flash.
    final relatedIds = decision.relatedActionItemIds.where((i) => i >= 0 && i < actionItemCount).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          decision.statement,
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w400, color: AppColors.textPrimary, height: 1.4),
        ),
        if (caption != null) ...[
          const SizedBox(height: AppStyles.spacingXS),
          Text(
            caption,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w400, color: AppColors.textTertiary),
          ),
        ],
        if (visibleQuestions.isNotEmpty) ...[
          const SizedBox(height: AppStyles.spacingS),
          Wrap(
            spacing: AppStyles.spacingS,
            runSpacing: AppStyles.spacingS,
            children: [
              for (final q in visibleQuestions) _OpenQuestionPill(label: q),
              if (overflow > 0) _OpenQuestionPill(label: l.decisionsOpenQuestionsMore(overflow)),
            ],
          ),
        ],
        if (relatedIds.isNotEmpty) ...[
          const SizedBox(height: AppStyles.spacingS),
          _ViewRelatedActionsLink(count: relatedIds.length, onTap: () => onViewRelatedActions(relatedIds)),
        ],
      ],
    );
  }

  static String? _ownerDueCaption(AppLocalizations l, DecisionItem d) {
    final owner = d.ownerName;
    final due = d.dueAt;
    if (owner == null && due == null) return null;
    if (owner != null && due != null) {
      return l.decisionsOwnerDueFormat(owner, _decisionDueDateFormat.format(due));
    }
    if (owner != null) return owner;
    return 'due ${_decisionDueDateFormat.format(due!)}';
  }
}

class _OpenQuestionPill extends StatelessWidget {
  const _OpenQuestionPill({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: AppStyles.spacingXS),
      decoration: BoxDecoration(
        color: AppColors.backgroundTertiary,
        borderRadius: BorderRadius.circular(AppStyles.radiusPill),
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, fontWeight: FontWeight.w400),
      ),
    );
  }
}

class _ViewRelatedActionsLink extends StatelessWidget {
  const _ViewRelatedActionsLink({required this.count, required this.onTap});

  final int count;
  final Future<void> Function() onTap;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final label = count == 1 ? l.decisionsViewRelatedActionsOne : l.decisionsViewRelatedActionsMany(count);
    return Semantics(
      button: true,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: SizedBox(
          height: AppStyles.touchTargetMinimum,
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              label,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.brandPrimary),
            ),
          ),
        ),
      ),
    );
  }
}

class _ActionItemRow extends StatelessWidget {
  const _ActionItemRow({required this.action, this.highlighted = false});
  final Map<String, dynamic> action;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final desc = (action['description'] as String?) ?? (action['content'] as String?) ?? '';
    final completed = action['completed'] == true;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
      decoration: BoxDecoration(
        color: highlighted ? AppColors.brandPrimary.withValues(alpha: 0.08) : Colors.transparent,
        borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
      ),
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: AppStyles.spacingXS),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(
              completed ? Icons.check_circle_rounded : Icons.radio_button_unchecked,
              size: 18,
              color: completed ? AppColors.brandPrimary : AppColors.textTertiary,
            ),
          ),
          const SizedBox(width: AppStyles.spacingS),
          Expanded(
            child: Text(
              desc,
              style: TextStyle(
                fontSize: 14,
                color: completed ? AppColors.textTertiary : AppColors.textPrimary,
                decoration: completed ? TextDecoration.lineThrough : null,
                decorationColor: AppColors.textTertiary,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SegmentRow extends StatelessWidget {
  const _SegmentRow({required this.segment});
  final Map<String, dynamic> segment;

  @override
  Widget build(BuildContext context) {
    final text = (segment['text'] as String?) ?? '';
    final speaker = (segment['speaker'] as String?) ?? '';
    final isUser = segment['is_user'] == true || speaker == 'SPEAKER_0';
    final label = isUser ? 'You' : _prettifySpeaker(speaker);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: isUser ? AppColors.brandPrimary : AppColors.textTertiary,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 2),
          Text(text, style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.4)),
        ],
      ),
    );
  }

  String _prettifySpeaker(String raw) {
    if (raw.isEmpty) return 'Speaker';
    return raw
        .replaceAll('_', ' ')
        .toLowerCase()
        .split(' ')
        .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
        .join(' ');
  }
}
