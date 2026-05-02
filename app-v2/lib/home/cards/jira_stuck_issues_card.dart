import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:nooto_v2/home/cards/card_entrance.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';
import 'package:nooto_v2/widgets/jira_chip.dart';

/// Atlassian/Jira blue. Mirrors the dot color in [JiraChip] so the card and
/// chips read as one visual family.
const Color _jiraBlue = Color(0xFF2684FF);

/// Surface card the companion stream emits when Jira items pile up. Two
/// triggers (either is sufficient):
///   * 3 or more "stuck" issues — incomplete with createdAt or dueAt older
///     than 3 days from now.
///   * 1 or more "due soon" — incomplete with dueAt inside the next 24h.
///
/// Idempotent per local-tz day: id is `jira-stuck-YYYY-MM-DD` so the user
/// doesn't see two of these in a single day. Tapping the card jumps to the
/// Plan tab; tapping a row opens the issue in Jira.
final class JiraStuckIssuesCard extends CompanionCard {
  JiraStuckIssuesCard({
    required this.dateKey,
    required this.stuckIssues,
    required this.totalStuck,
    required this.dueSoon,
    required this.generatedAt,
  });

  /// Local-timezone YYYY-MM-DD; identical encoding to the morning brief.
  final String dateKey;

  /// At most 3 issues — the rest stay summarized via [totalStuck].
  final List<ActionItem> stuckIssues;

  /// Total number of stuck issues (>3 days old, incomplete). May exceed
  /// `stuckIssues.length` (which is capped at 3 for display).
  final int totalStuck;

  /// Number of incomplete issues with a due date inside the next 24 hours.
  final int dueSoon;

  @override
  final DateTime generatedAt;

  @override
  String get id => '$_idPrefix$dateKey';

  @override
  CardKind get kind => CardKind.jiraStuckIssues;

  /// Above the morning brief (750) but below welcome (1000). Stuck issues are
  /// urgent enough to surface above the day's brief — that's the whole point
  /// of the proactive emission — but the brief should still be visible.
  @override
  int get priority => 800;

  /// Refreshed every Home foreground; 12h TTL keeps a stale card from
  /// shadowing a freshly recalculated state if the user backgrounds the app.
  @override
  Duration get ttl => const Duration(hours: 12);

  @override
  Map<String, dynamic> toJson() => {
    'kind': kind.code,
    'dateKey': dateKey,
    'stuckIssues': stuckIssues.map(_actionItemToJson).toList(),
    'totalStuck': totalStuck,
    'dueSoon': dueSoon,
    'generatedAt': generatedAt.toIso8601String(),
  };

  factory JiraStuckIssuesCard.fromJson(Map<String, dynamic> json) {
    final raw = json['stuckIssues'] as List<dynamic>? ?? const [];
    final issues = raw.map((e) => _actionItemFromJson(Map<String, dynamic>.from(e as Map))).toList(growable: false);
    return JiraStuckIssuesCard(
      dateKey: json['dateKey'] as String,
      stuckIssues: issues,
      totalStuck: (json['totalStuck'] as int?) ?? issues.length,
      dueSoon: (json['dueSoon'] as int?) ?? 0,
      generatedAt: DateTime.parse(json['generatedAt'] as String),
    );
  }

  @override
  void onAction(BuildContext context, CardAction action) {
    if (action == CardAction.tapThrough || action == CardAction.open) {
      context.read<HomeNav>().switchToTab(HomeNav.planTabIndex);
    }
  }

  @override
  Widget render(BuildContext context) => _JiraStuckIssuesView(card: this);

  static const String _idPrefix = 'jira-stuck-';
}

/// Local-tz YYYY-MM-DD — same encoding the brief card uses.
String jiraStuckDateKeyFor(DateTime now) {
  final y = now.year.toString().padLeft(4, '0');
  final m = now.month.toString().padLeft(2, '0');
  final d = now.day.toString().padLeft(2, '0');
  return '$y-$m-$d';
}

/// Generator. Returns null when:
///   * Provider hasn't completed its first fetch (avoid emitting on stale
///     "no items" state — would feel like the card disappeared).
///   * Neither trigger fires (3+ stuck OR 1+ due-soon).
///
/// "Stuck" = incomplete + has Jira external_source + (createdAt OR dueAt)
/// older than 3 days from `now`. Items with neither timestamp are skipped
/// (we can't decide if they're stale).
///
/// "Due soon" = incomplete + has Jira external_source + dueAt within the
/// next 24 hours. An item can be both stuck (overdue → dueAt > 3d ago) AND
/// due-soon if its dueAt is somehow within 24h of now while createdAt is
/// far in the past — but the `else if` ordering below makes due-soon win
/// the count since urgency trumps staleness.
JiraStuckIssuesCard? jiraStuckIssuesCardFor(ActionItemsProvider provider, {DateTime? now}) {
  if (!provider.ready) return null;
  final clock = now ?? DateTime.now();
  final stuckThreshold = clock.subtract(const Duration(days: 3));
  final dueSoonCutoff = clock.add(const Duration(hours: 24));

  final stuck = <ActionItem>[];
  var dueSoonCount = 0;

  for (final item in provider.items) {
    if (item.completed) continue;
    final ext = item.externalSource;
    if (ext == null || ext.source != 'jira') continue;

    final due = item.dueAt;
    if (due != null && !due.isBefore(clock) && due.isBefore(dueSoonCutoff)) {
      // Within the next 24h (inclusive of "now"). These are "due soon" — we
      // surface them on the card body with bold prefix when count > 0.
      dueSoonCount += 1;
      continue;
    }

    final reference = item.createdAt ?? item.dueAt;
    if (reference == null) continue;
    if (reference.isBefore(stuckThreshold)) {
      stuck.add(item);
    }
  }

  if (stuck.length < 3 && dueSoonCount < 1) return null;

  // Sort stuck oldest-first so the card surfaces the most-stale items first
  // (the user's actual problem). Falls back to dueAt if createdAt is null.
  stuck.sort((a, b) {
    final ar = a.createdAt ?? a.dueAt!;
    final br = b.createdAt ?? b.dueAt!;
    return ar.compareTo(br);
  });

  return JiraStuckIssuesCard(
    dateKey: jiraStuckDateKeyFor(clock),
    stuckIssues: stuck.take(3).toList(growable: false),
    totalStuck: stuck.length,
    dueSoon: dueSoonCount,
    generatedAt: clock,
  );
}

Map<String, dynamic> _actionItemToJson(ActionItem item) {
  final ext = item.externalSource;
  return {
    'id': item.id,
    'description': item.description,
    'completed': item.completed,
    if (item.createdAt != null) 'created_at': item.createdAt!.toIso8601String(),
    if (item.dueAt != null) 'due_at': item.dueAt!.toIso8601String(),
    if (item.conversationId != null) 'conversation_id': item.conversationId,
    if (ext != null) 'external_source': {'source': ext.source, 'external_id': ext.externalId, 'url': ext.url},
  };
}

ActionItem _actionItemFromJson(Map<String, dynamic> json) {
  return ActionItem.fromJson(json);
}

class _JiraStuckIssuesView extends StatelessWidget {
  const _JiraStuckIssuesView({required this.card});

  final JiraStuckIssuesCard card;

  @override
  Widget build(BuildContext context) {
    return CardEntrance(
      child: Semantics(
        button: true,
        label: 'Jira issues need attention. Opens Plan tab.',
        child: InkWell(
          onTap: () => card.onAction(context, CardAction.tapThrough),
          borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
          child: Container(
            decoration: BoxDecoration(
              color: AppColors.backgroundSecondary,
              borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
              border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
            ),
            padding: const EdgeInsets.all(AppStyles.spacingL),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _Header(card: card),
                if (card.dueSoon > 0) ...[
                  const SizedBox(height: AppStyles.spacingM),
                  _DueSoonLine(count: card.dueSoon),
                ],
                if (card.stuckIssues.isNotEmpty) ...[
                  const SizedBox(height: AppStyles.spacingM),
                  for (var i = 0; i < card.stuckIssues.length; i++) ...[
                    _IssueRow(item: card.stuckIssues[i]),
                    if (i < card.stuckIssues.length - 1) const SizedBox(height: AppStyles.spacingS),
                  ],
                ],
                if (card.totalStuck > card.stuckIssues.length) ...[
                  const SizedBox(height: AppStyles.spacingM),
                  Text(
                    '+${card.totalStuck - card.stuckIssues.length} more stuck',
                    style: const TextStyle(fontSize: 12, color: AppColors.textTertiary, fontWeight: FontWeight.w500),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.card});
  final JiraStuckIssuesCard card;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(color: _jiraBlue, shape: BoxShape.circle),
          ),
        ),
        const SizedBox(width: AppStyles.spacingM),
        const Expanded(
          child: Text(
            'Jira issues need attention',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          ),
        ),
      ],
    );
  }
}

class _DueSoonLine extends StatelessWidget {
  const _DueSoonLine({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) {
    final label = count == 1 ? '1 due in the next 24h' : '$count due in the next 24h';
    return Text(
      label,
      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary, height: 1.4),
    );
  }
}

class _IssueRow extends StatelessWidget {
  const _IssueRow({required this.item});
  final ActionItem item;

  @override
  Widget build(BuildContext context) {
    final ext = item.externalSource;
    if (ext == null) return const SizedBox.shrink();
    return Semantics(
      button: true,
      label: 'Open ${ext.externalId} in Jira',
      child: InkWell(
        onTap: () async {
          try {
            await launchUrl(Uri.parse(ext.url), mode: LaunchMode.externalApplication);
          } catch (_) {
            // Best-effort — same swallow as the chip. If the URL is broken
            // (rare; backend gates this) the row stays static.
          }
        },
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
        child: Padding(
          // 12pt vertical padding × 2 + 18-22pt content height keeps the row
          // hit area at or above 44pt across a single-line truncated row.
          padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: AppStyles.spacingM),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              JiraChip.forSource(ext),
              const SizedBox(width: AppStyles.spacingM),
              Expanded(
                child: Text(
                  item.description,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.4),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
