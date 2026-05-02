import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/plan/widgets/plan_row.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Tab 3: Plan — full list of open commitments grouped by due window.
/// Reads the same `ActionItemsProvider` that feeds the Home Today card.
class PlanScreen extends StatefulWidget {
  const PlanScreen({super.key});

  @override
  State<PlanScreen> createState() => _PlanScreenState();
}

class _PlanScreenState extends State<PlanScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ActionItemsProvider>().kickOffIfNeeded();
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ActionItemsProvider>();
    final items = provider.items.where((i) => !i.completed).toList();

    if (provider.loading && !provider.ready) return const _Loading();
    if (items.isEmpty) return const _EmptyState();

    final groups = _group(items);
    // See apps_screen.dart — MediaQuery.padding.top already covers the
    // status bar + AppBar when extendBodyBehindAppBar is true.
    final topInset = MediaQuery.of(context).padding.top + AppStyles.spacingM;
    return RefreshIndicator(
      onRefresh: () => provider.fetchAll(),
      color: AppColors.brandPrimary,
      backgroundColor: AppColors.backgroundSecondary,
      child: ListView.builder(
        padding: EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          topInset,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        itemCount: groups.length,
        itemBuilder: (_, i) => _GroupSection(
          title: groups[i].title,
          items: groups[i].items,
          onToggle: (id) async {
            HapticFeedback.lightImpact();
            await provider.complete(id);
          },
        ),
      ),
    );
  }

  /// Bucket open items into Overdue / Today / This week / Later / Anytime.
  /// Empty buckets are dropped so the screen doesn't surface empty headers.
  static List<_Group> _group(List<ActionItem> items) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final tomorrow = today.add(const Duration(days: 1));
    final weekEnd = today.add(const Duration(days: 7));
    final overdue = <ActionItem>[];
    final dueToday = <ActionItem>[];
    final thisWeek = <ActionItem>[];
    final later = <ActionItem>[];
    final anytime = <ActionItem>[];
    for (final item in items) {
      final due = item.dueAt;
      if (due == null) {
        anytime.add(item);
      } else if (due.isBefore(today)) {
        overdue.add(item);
      } else if (due.isBefore(tomorrow)) {
        dueToday.add(item);
      } else if (due.isBefore(weekEnd)) {
        thisWeek.add(item);
      } else {
        later.add(item);
      }
    }
    return [
      if (overdue.isNotEmpty) _Group('OVERDUE', _sortByDue(overdue)),
      if (dueToday.isNotEmpty) _Group('TODAY', _sortByDue(dueToday)),
      if (thisWeek.isNotEmpty) _Group('THIS WEEK', _sortByDue(thisWeek)),
      if (later.isNotEmpty) _Group('LATER', _sortByDue(later)),
      if (anytime.isNotEmpty) _Group('ANYTIME', _sortByCreated(anytime)),
    ];
  }

  static List<ActionItem> _sortByDue(List<ActionItem> list) {
    list.sort((a, b) => (a.dueAt ?? DateTime(2100)).compareTo(b.dueAt ?? DateTime(2100)));
    return list;
  }

  static List<ActionItem> _sortByCreated(List<ActionItem> list) {
    list.sort((a, b) {
      final ac = a.createdAt;
      final bc = b.createdAt;
      if (ac == null && bc == null) return 0;
      if (ac == null) return 1;
      if (bc == null) return -1;
      return bc.compareTo(ac);
    });
    return list;
  }
}

class _Group {
  const _Group(this.title, this.items);
  final String title;
  final List<ActionItem> items;
}

class _GroupSection extends StatelessWidget {
  const _GroupSection({
    required this.title,
    required this.items,
    required this.onToggle,
  });
  final String title;
  final List<ActionItem> items;
  final Future<void> Function(String id) onToggle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingXL),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS),
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary,
                letterSpacing: 0.8,
              ),
            ),
          ),
          const SizedBox(height: AppStyles.spacingS),
          for (final item in items)
            PlanRow(
              key: ValueKey(item.id),
              item: item,
              onToggle: () => onToggle(item.id),
            ),
        ],
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: SizedBox(
        width: 28,
        height: 28,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: AppColors.brandPrimary,
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.check_circle_outline_rounded,
              size: 32,
              color: AppColors.textTertiary,
            ),
            SizedBox(height: AppStyles.spacingM),
            Text(
              'Nothing pending.',
              style: TextStyle(
                fontSize: 17,
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            SizedBox(height: AppStyles.spacingXS),
            Text(
              "I'll surface commitments here as they come up in conversations.",
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 14,
                color: AppColors.textTertiary,
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
