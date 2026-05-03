import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/library/widgets/app_result_markdown.dart';
import 'package:nooto_v2/library/widgets/summarized_apps_sheet.dart';
import 'package:nooto_v2/theme/app_theme.dart';

final _detailDateFormat = DateFormat('EEEE, MMM d · h:mm a');

/// Conversation detail screen — title, when, overview, action items, and
/// transcript segments. Pushed by the Meetings list and by the "View
/// conversation" affordance on a memory row.
///
/// The OVERVIEW slot renders the active app's markdown via
/// [AppResultMarkdown]. Falls back to plain `Structured.overview` when no
/// app summary exists. Tap the attribution row to swap apps via
/// [SummarizedAppsBottomSheet]; the screen rebuilds when
/// [ConversationsProvider] reprocess completes.
class ConversationDetailScreen extends StatelessWidget {
  const ConversationDetailScreen({super.key, required this.item});

  final ConversationItem item;

  @override
  Widget build(BuildContext context) {
    // Read the latest conversation from the provider when one is in scope —
    // `reprocessWithApp` splices a fresh ConversationItem into the cache,
    // so reading from the provider lets the screen rebuild with new
    // apps_results without a re-push. Falls back to the constructor item
    // when hosted outside a ConversationsProvider (e.g. widget tests).
    final ConversationsProvider? convs = context.watch<ConversationsProvider?>();
    final ConversationItem item = convs?.byId(this.item.id) ?? this.item;
    final reprocessing = convs?.isReprocessing(item.id) ?? false;
    final raw = item.raw;
    final structured = raw['structured'] is Map
        ? Map<String, dynamic>.from(raw['structured'] as Map)
        : const <String, dynamic>{};
    final actionItems = structured['action_items'] is List
        ? List<Map<String, dynamic>>.from(
            (structured['action_items'] as List).whereType<Map>().map(
                  (e) => Map<String, dynamic>.from(e),
                ),
          )
        : const <Map<String, dynamic>>[];
    final segments = raw['transcript_segments'] is List
        ? List<Map<String, dynamic>>.from(
            (raw['transcript_segments'] as List).whereType<Map>().map(
                  (e) => Map<String, dynamic>.from(e),
                ),
          )
        : const <Map<String, dynamic>>[];

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
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          0,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        children: [
          if (item.createdAt != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppStyles.spacingM),
              child: Text(
                _detailDateFormat.format(item.createdAt!),
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textTertiary,
                ),
              ),
            ),
          if (item.overview.trim().isNotEmpty || item.summarizedApp != null || reprocessing) ...[
            const _SectionHeader(label: 'OVERVIEW'),
            const SizedBox(height: AppStyles.spacingS),
            AppResultMarkdown(
              item: item,
              reprocessing: reprocessing,
              onPickApp: () => SummarizedAppsBottomSheet.show(
                context,
                conversationId: item.id,
                currentAppId: item.summarizedApp?.appId,
              ),
            ),
            const SizedBox(height: AppStyles.spacingXL),
          ],
          if (actionItems.isNotEmpty) ...[
            _SectionHeader(label: 'ACTION ITEMS'),
            const SizedBox(height: AppStyles.spacingS),
            for (final a in actionItems) _ActionItemRow(action: a),
            const SizedBox(height: AppStyles.spacingXL),
          ],
          if (segments.isNotEmpty) ...[
            _SectionHeader(label: 'TRANSCRIPT'),
            const SizedBox(height: AppStyles.spacingS),
            for (final s in segments) _SegmentRow(segment: s),
          ] else
            const Padding(
              padding: EdgeInsets.symmetric(vertical: AppStyles.spacingL),
              child: Text(
                'No transcript captured for this conversation.',
                style: TextStyle(
                  fontSize: 13,
                  color: AppColors.textTertiary,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: AppColors.textTertiary,
        letterSpacing: 0.8,
      ),
    );
  }
}

class _ActionItemRow extends StatelessWidget {
  const _ActionItemRow({required this.action});
  final Map<String, dynamic> action;

  @override
  Widget build(BuildContext context) {
    final desc = (action['description'] as String?) ?? (action['content'] as String?) ?? '';
    final completed = action['completed'] == true;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
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
          Text(
            text,
            style: const TextStyle(
              fontSize: 14,
              color: AppColors.textSecondary,
              height: 1.4,
            ),
          ),
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
