import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A Home section heading (v2 Main): the title in 20pt semibold and, trailing, a 15pt semibold
/// link ("See All", "All Tasks") that switches to the section's tab.
class HomeSectionHeader extends StatelessWidget {
  const HomeSectionHeader({super.key, required this.title, this.actionLabel, this.onAction});

  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, 0, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(child: Semantics(header: true, child: Text(title, style: OmiType.title3))),
          if (actionLabel != null && onAction != null)
            Semantics(
              button: true,
              label: actionLabel,
              excludeSemantics: true,
              onTap: onAction,
              child: OmiPressable(
                onTap: () {
                  OmiHaptics.selection();
                  onAction!();
                },
                // The label is 20pt tall; the touch target is 44pt.
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: OmiSize.minTap, minWidth: OmiSize.minTap),
                  child: Padding(
                    padding: const EdgeInsets.only(left: OmiSpacing.xs, right: OmiSpacing.xxs),
                    child: Center(
                      widthFactor: 1,
                      child: Text(actionLabel!, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Home's sync card (v2 Main): shown only while recordings come off the pendant. The bar fills with
/// the real upload progress; once uploaded it reads "Pendant recordings synced · Done" while the
/// new conversations are fetched, then folds away.
class HomeSyncCard extends StatefulWidget {
  const HomeSyncCard({super.key, this.onTap});

  /// Opens Offline recordings.
  final VoidCallback? onTap;

  @override
  State<HomeSyncCard> createState() => _HomeSyncCardState();
}

class _HomeSyncCardState extends State<HomeSyncCard> {
  /// The most audio seen waiting on the pendant during this sync: the total does not shrink as
  /// files finish, so the line keeps saying how much was recorded while the phone was away.
  int _awaySeconds = 0;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<SyncProvider>(
      builder: (context, sync, _) {
        final active = sync.isSyncing || sync.isFetchingConversations;
        if (!active) {
          _awaySeconds = 0;
        } else {
          _awaySeconds = math.max(_awaySeconds, sync.missingWalsInSeconds);
        }
        final progress = sync.walsSyncedProgress.clamp(0.0, 1.0);
        final done = sync.isFetchingConversations || progress >= 1;
        return AnimatedSize(
          duration: OmiMotion.of(context).emphasized,
          curve: OmiMotion.springCurve,
          alignment: Alignment.topCenter,
          child: !active
              ? const SizedBox(width: double.infinity)
              : Padding(
                  padding: const EdgeInsets.only(top: 22),
                  child: OmiCard(
                    key: const Key('home_sync_card'),
                    radius: OmiRadius.row,
                    padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 13, OmiSpacing.md, 13),
                    onTap: widget.onTap,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            OmiGlyph(OmiGlyphs.sdcard, size: 18, color: OmiColors.textSecondary),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                done ? l10n.pendantRecordingsSynced : l10n.syncingFromPendant,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                              ),
                            ),
                            const SizedBox(width: OmiSpacing.xs),
                            Text(
                              done ? l10n.done : '${(progress * 100).round()}%',
                              style: OmiType.subhead.copyWith(
                                color: OmiColors.textSecondary,
                                fontFeatures: const [FontFeature.tabularFigures()],
                              ),
                            ),
                            const SizedBox(width: OmiSpacing.xs),
                            OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
                          ],
                        ),
                        const SizedBox(height: 9),
                        OmiProgressBar(value: done ? 1 : progress),
                        if (_awaySeconds > 0) ...[
                          const SizedBox(height: 9),
                          Text(
                            l10n.recordedOnPendantWhileAway(OmiDuration.compact(_awaySeconds, l10n)),
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
        );
      },
    );
  }
}

/// The latest daily recap as one card (v2 Main): "Daily recap · Wednesday", the headline in serif,
/// and the day in numbers.
class HomeRecapCard extends StatelessWidget {
  const HomeRecapCard({super.key, required this.summary, required this.onTap});

  final DailySummary summary;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final date = DateTime.tryParse(summary.date);
    final weekday =
        date == null ? summary.date : DateFormat.EEEE(Localizations.localeOf(context).toString()).format(date);
    final stats = summary.stats;
    final parts = [
      l10n.conversationCount(stats.totalConversations),
      if (stats.totalDurationMinutes > 0) OmiDuration.compact(stats.totalDurationMinutes * 60, l10n),
      if (stats.actionItemsCount > 0) l10n.taskCount(stats.actionItemsCount),
    ];
    return OmiCard(
      key: const Key('home_recap_card'),
      padding: const EdgeInsets.all(18),
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  l10n.dailyRecapOn(weekday),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary),
                ),
              ),
              OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            summary.headline,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: OmiType.serifCard,
          ),
          const SizedBox(height: 10),
          Text(
            parts.join(' · '),
            style: OmiType.footnote.copyWith(
              color: OmiColors.textSecondary,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

/// "Up next" on Home (v2 Main): the next tasks with a round check, their due time (amber when it is
/// today) or the conversation they came from, and "All Tasks" into the Tasks tab. What is due comes
/// first; open tasks without a date fill the rest, so the short list shows whenever there is one.
class HomeUpNext extends StatefulWidget {
  const HomeUpNext({super.key, required this.onAllTasks});

  final VoidCallback onAllTasks;

  /// Today's tasks first, then the other open ones soonest due first (undated last), so what is
  /// coming shows ahead of its day (#5080).
  static List<ActionItemWithMetadata> pick(
    List<ActionItemWithMetadata> today,
    List<ActionItemWithMetadata> open, {
    int limit = 3,
  }) {
    final rest = open.where((task) => today.every((d) => d.id != task.id)).toList();
    // Stable: tasks without a due date keep the order the list gave them.
    final dated = rest.where((task) => task.dueAt != null).toList()..sort((a, b) => a.dueAt!.compareTo(b.dueAt!));
    return [...today, ...dated, ...rest.where((task) => task.dueAt == null)].take(limit).toList();
  }

  @override
  State<HomeUpNext> createState() => _HomeUpNextState();
}

class _HomeUpNextState extends State<HomeUpNext> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final provider = context.read<ActionItemsProvider>();
      unawaited(provider.ensureHomeTodayTasksLoaded());
      unawaited(provider.ensureLoaded());
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, _) {
        final tasks = HomeUpNext.pick(provider.todayPreviewTasks(), provider.incompleteItems);
        if (tasks.isEmpty) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(top: 22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              HomeSectionHeader(title: l10n.upNext, actionLabel: l10n.allTasks, onAction: widget.onAllTasks),
              OmiCard(
                clip: true,
                child: Column(
                  children: [
                    for (final (i, task) in tasks.indexed) ...[
                      if (i > 0) Divider(height: 0.5, thickness: 0.5, indent: 52, color: OmiColors.border),
                      _UpNextRow(task: task, provider: provider),
                    ],
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _UpNextRow extends StatelessWidget {
  const _UpNextRow({required this.task, required this.provider});

  final ActionItemWithMetadata task;
  final ActionItemsProvider provider;

  /// "Today, 5:00 PM" in amber when due today or earlier; "From …" when it came from a conversation.
  (String, Color)? _subline(BuildContext context) {
    final due = task.dueAt?.toLocal();
    if (due != null) {
      final dates = OmiDateFormat.of(context);
      final now = DateTime.now();
      final endOfToday = DateTime(now.year, now.month, now.day + 1);
      final label = context.l10n.taskDueDayTime(dates.dayHeader(due), dates.time(due));
      return (label, due.isBefore(endOfToday) ? OmiColors.warning : OmiColors.textSecondary);
    }
    final conversationId = task.conversationId;
    if (conversationId == null) return null;
    final conversations = context.read<ConversationProvider>().conversations;
    for (final c in conversations) {
      if (c.id == conversationId) {
        final title = c.structured.title.trim();
        if (title.isEmpty) return null;
        return (context.l10n.fromConversation(title), OmiColors.textSecondary);
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final sub = _subline(context);
    final done = task.completed;
    return InkWell(
      splashFactory: NoSplash.splashFactory,
      highlightColor: OmiColors.cellPressed,
      onTap: () => showActionItemFormSheet(context, actionItem: task),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(6, 3, OmiSpacing.md, 3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // The 24pt circle sits in a 44pt target; its visual left edge lands at 16.
            OmiCheckCircle(
              done: done,
              semanticLabel: done ? context.l10n.markIncomplete : context.l10n.markComplete,
              onChanged: (value) async {
                OmiHaptics.light();
                final saved = await provider.updateActionItemState(task, value);
                // The provider puts a rejected change back; tell the reader rather than fail silently.
                if (!saved && context.mounted) OmiFeedback.error(context, context.l10n.failedToUpdateActionItem);
              },
            ),
            const SizedBox(width: 2),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AnimatedDefaultTextStyle(
                      duration: const Duration(milliseconds: 300),
                      style: OmiType.body.copyWith(
                        color: done ? OmiColors.textTertiary : OmiColors.textPrimary,
                        decoration: done ? TextDecoration.lineThrough : null,
                      ),
                      child: Text(task.description, maxLines: 2, overflow: TextOverflow.ellipsis),
                    ),
                    if (sub != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        sub.$1,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.footnote.copyWith(color: sub.$2),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "This week" (v2 Main): minutes captured per day, Monday to Sunday. Past days with audio are
/// strong-fill bars scaled to the busiest day, today is white, days still to come are a stub.
///
/// Built from the conversations already loaded; shown only when they reach back to the start of
/// the week, so the totals are never partial.
class HomeThisWeek extends StatelessWidget {
  const HomeThisWeek({super.key});

  /// The last week counted from the whole list. The loaded list follows the Conversations tab's
  /// filters (Starred, a folder, a device, a date, a search) — counting it then showed a filtered
  /// sliver as the week (39 s instead of 3 h 18 m) until the filter was cleared.
  static ({DateTime weekStart, List<int> seconds})? _lastWeek;

  @visibleForTesting
  static void resetForTest() => _lastWeek = null;

  /// Seconds captured each day of the week starting [weekStart], or null when the loaded list cannot
  /// say: it is filtered, or does not reach back to Monday yet.
  static List<int>? countWeek(ConversationProvider provider, DateTime weekStart) {
    final filtered = provider.showStarredOnly ||
        provider.selectedFolderId != null ||
        provider.sourceFilter != ConversationSourceFilter.all ||
        provider.selectedStartDate != null ||
        provider.hasActiveSearch;
    if (filtered) return null;
    final conversations = provider.conversations.where((c) => !c.discarded).toList();
    if (conversations.isEmpty) return null;
    final oldest =
        conversations.map((c) => (c.startedAt ?? c.createdAt).toLocal()).reduce((a, b) => a.isBefore(b) ? a : b);
    final complete = oldest.isBefore(weekStart) || !provider.hasMoreConversations;
    if (!complete) return null;
    final seconds = List<int>.filled(7, 0);
    for (final c in conversations) {
      final start = (c.startedAt ?? c.createdAt).toLocal();
      if (start.isBefore(weekStart)) continue;
      final day = DateTime(start.year, start.month, start.day).difference(weekStart).inDays;
      if (day < 0 || day > 6) continue;
      seconds[day] += c.getDurationInSeconds();
    }
    return seconds;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, provider, _) {
        final now = DateTime.now();
        final today = DateTime(now.year, now.month, now.day);
        final weekStart = today.subtract(Duration(days: today.weekday - DateTime.monday));
        final counted = countWeek(provider, weekStart);
        if (counted != null) _lastWeek = (weekStart: weekStart, seconds: counted);
        final last = _lastWeek;
        // While the list is filtered, the week last counted from the whole list (this week's only).
        final seconds = counted ?? (last != null && last.weekStart == weekStart ? last.seconds : null);
        if (seconds == null) return const SizedBox.shrink();
        final total = seconds.fold<int>(0, (a, b) => a + b);
        if (total == 0) return const SizedBox.shrink();
        final peak = seconds.reduce(math.max);
        final todayIndex = today.difference(weekStart).inDays;
        final locale = Localizations.localeOf(context).toString();
        final l10n = context.l10n;

        return Padding(
          padding: const EdgeInsets.only(top: 22),
          child: OmiCard(
            key: const Key('home_this_week'),
            padding: const EdgeInsets.fromLTRB(18, OmiSpacing.md, 18, OmiSpacing.md),
            child: Semantics(
              container: true,
              label: '${l10n.thisWeek}, ${l10n.capturedDuration(OmiDuration.long(total, l10n))}',
              excludeSemantics: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Expanded(child: Text(l10n.thisWeek, style: OmiType.headline)),
                      Text(
                        l10n.capturedDuration(OmiDuration.compact(total, l10n)),
                        style: OmiType.footnote.copyWith(
                          color: OmiColors.textSecondary,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  SizedBox(
                    height: 74,
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        for (var i = 0; i < 7; i++) ...[
                          if (i > 0) const SizedBox(width: 10),
                          Expanded(
                            child: _DayBar(
                              letter: DateFormat.EEEEE(locale).format(weekStart.add(Duration(days: i))),
                              fraction: peak == 0 ? 0 : seconds[i] / peak,
                              isToday: i == todayIndex,
                              isFuture: i > todayIndex,
                              index: i,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _DayBar extends StatelessWidget {
  const _DayBar({
    required this.letter,
    required this.fraction,
    required this.isToday,
    required this.isFuture,
    required this.index,
  });

  final String letter;
  final double fraction;
  final bool isToday;
  final bool isFuture;
  final int index;

  @override
  Widget build(BuildContext context) {
    final height = isFuture ? 4.0 : math.max(4.0, 52 * fraction);
    final color = isToday
        ? OmiColors.textPrimary
        : isFuture || fraction == 0
            ? OmiColors.surface2
            : OmiColors.surface4;
    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        // Bars rise in one after another (v2 `rise`, 50 ms apart).
        TweenAnimationBuilder<double>(
          tween: Tween(begin: MediaQuery.disableAnimationsOf(context) ? 1 : 0, end: 1),
          duration: Duration(milliseconds: 550 + index * 50),
          curve: Interval(index * 50 / (550 + index * 50), 1, curve: OmiMotion.springCurve),
          builder: (context, t, _) => Opacity(
            opacity: t,
            child: Transform.translate(
              offset: Offset(0, 14 * (1 - t)),
              child: Container(
                height: height,
                constraints: const BoxConstraints(maxWidth: 26),
                decoration: BoxDecoration(color: color, borderRadius: OmiRadius.smAll),
              ),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          letter,
          style: OmiType.caption1.copyWith(
            fontWeight: FontWeight.w600,
            color: isToday ? OmiColors.textPrimary : OmiColors.textTertiary,
          ),
        ),
      ],
    );
  }
}

/// "3 new memories" (v2 Main): what Omi learned in the last day, opening Memories.
class HomeNewMemories extends StatelessWidget {
  const HomeNewMemories({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        final since = DateTime.now().subtract(const Duration(days: 1));
        final fresh = provider.memories.where((m) => m.createdAt.toLocal().isAfter(since)).toList()
          ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
        if (fresh.isEmpty) return const SizedBox.shrink();
        final l10n = context.l10n;
        final preview = fresh.take(3).map((m) => m.content.trim()).where((t) => t.isNotEmpty).join(', ');
        return Padding(
          padding: const EdgeInsets.only(top: 22),
          child: OmiCard(
            key: const Key('home_new_memories'),
            radius: OmiRadius.row,
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 14, OmiSpacing.md, 14),
            onTap: onTap,
            child: Row(
              children: [
                const OmiIconTile(size: 40, child: OmiGlyph(OmiGlyphs.graph, size: 20)),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.newMemoriesCount(fresh.length), style: OmiType.headline),
                      if (preview.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          preview,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: OmiSpacing.xs),
                OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
              ],
            ),
          ),
        );
      },
    );
  }
}
