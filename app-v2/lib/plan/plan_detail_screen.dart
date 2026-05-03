import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:nooto_v2/apps/apps_provider.dart' hide LaunchUrlFn;
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';
import 'package:nooto_v2/widgets/jira_chip.dart' show LaunchUrlFn;

const String _jiraAppId = 'nooto-jira';

/// Read-only detail view for a Plan row. Renders only the data that's
/// already on [ActionItem] — title, status, project, priority, days at
/// status, due/created — plus a primary "Mark as Done" button (Jira) /
/// "Mark complete" button (transcript) that routes through the same
/// provider helpers as the row checkbox.
///
/// Out of scope (deferred): full Jira description, comments, status
/// history, assignee, labels, linked issues. Those need a backend-side
/// per-action-item details endpoint that proxies the Jira API. For now an
/// "Open in Jira" link punts users to the source of truth when they need
/// more than what we can render on-device.
class PlanDetailScreen extends StatefulWidget {
  const PlanDetailScreen({super.key, required this.itemId, LaunchUrlFn? launchUrl}) : _launchUrl = launchUrl;

  /// We resolve the live item from the provider on every build so a
  /// successful "Mark Done" / refresh / sync round-trip reflects without
  /// the screen holding stale data. Callers pass the id; the screen looks
  /// up the rest.
  final String itemId;

  final LaunchUrlFn? _launchUrl;

  @override
  State<PlanDetailScreen> createState() => _PlanDetailScreenState();
}

class _PlanDetailScreenState extends State<PlanDetailScreen> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ActionItemsProvider>();
    final apps = context.watch<AppsProvider>();
    final twoWaySync = apps.isTwoWaySyncEnabled(_jiraAppId);
    // Item may have been completed and removed from the in-memory list
    // (e.g. a successful Mark Done that fired notifyListeners). Fall back
    // to a "completed / dismissed" stub and let the user back out.
    final item = provider.items.firstWhere(
      (i) => i.id == widget.itemId,
      orElse: () => ActionItem(id: widget.itemId, description: '', completed: true),
    );
    final ext = item.externalSource;
    final isJira = ext?.source == 'jira';
    final isCompleted = item.completed || item.description.isEmpty;

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
          isJira ? (ext!.externalId) : 'Task',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          AppStyles.spacingS,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        children: [
          if (isCompleted)
            const _CompletedBanner()
          else ...[
            _Title(text: item.description, completed: item.completed),
            const SizedBox(height: AppStyles.spacingL),
            if (isJira) _JiraStatusPill(status: ext!.jiraStatus, statusType: ext.jiraStatusType),
            if (isJira) const SizedBox(height: AppStyles.spacingL),
            if (isJira && (ext?.jiraDescriptionBody?.isNotEmpty ?? false)) ...[
              _DescriptionBody(text: ext!.jiraDescriptionBody!),
              const SizedBox(height: AppStyles.spacingL),
            ],
            _MetaTable(item: item, isJira: isJira),
            const SizedBox(height: AppStyles.spacingXL),
            _PrimaryAction(
              isJira: isJira,
              twoWaySync: twoWaySync,
              busy: _busy,
              onPressed: _busy ? null : () => _handlePrimaryAction(item, twoWaySync: twoWaySync),
            ),
            if (isJira && ext != null && ext.url.isNotEmpty) ...[
              const SizedBox(height: AppStyles.spacingM),
              _OpenInJiraButton(url: ext.url, onTap: () => _openUrl(ext.url)),
            ],
          ],
        ],
      ),
    );
  }

  Future<void> _handlePrimaryAction(ActionItem item, {required bool twoWaySync}) async {
    final ext = item.externalSource;
    final provider = context.read<ActionItemsProvider>();
    if (ext?.source == 'jira') {
      if (!twoWaySync) {
        _showSnack('Enable Jira write-back in Settings → Apps → Jira');
        return;
      }
      setState(() => _busy = true);
      HapticFeedback.lightImpact();
      final ok = await provider.transition(item.id, toStatus: 'Done', optimisticallyComplete: true);
      if (!mounted) return;
      setState(() => _busy = false);
      if (!ok) {
        _showSnack(
          provider.lastActionError == 'two_way_sync_disabled'
              ? 'Enable Jira write-back in Settings → Apps → Jira'
              : "Couldn't update Jira. Try again.",
        );
        return;
      }
      Navigator.of(context).maybePop();
      return;
    }
    setState(() => _busy = true);
    HapticFeedback.lightImpact();
    await provider.complete(item.id);
    if (!mounted) return;
    setState(() => _busy = false);
    Navigator.of(context).maybePop();
  }

  Future<void> _openUrl(String url) async {
    HapticFeedback.selectionClick();
    final launcher = widget._launchUrl ?? launchUrl;
    try {
      await launcher(Uri.parse(url), mode: LaunchMode.platformDefault);
    } catch (_) {
      if (!mounted) return;
      _showSnack("Couldn't open the linked issue.");
    }
  }

  void _showSnack(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }
}

/// Plain-text Jira issue body. Capped server-side at 2000 chars; if the
/// real description was longer, the cap added a trailing "…" so users see
/// they can tap "Open in Jira" for the full thing.
class _DescriptionBody extends StatelessWidget {
  const _DescriptionBody({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        border: Border.all(color: AppColors.textTertiary.withValues(alpha: 0.15)),
      ),
      padding: const EdgeInsets.all(AppStyles.spacingL),
      child: SelectableText(
        text,
        style: const TextStyle(
          fontSize: 15,
          color: AppColors.textPrimary,
          height: 1.5,
        ),
      ),
    );
  }
}

class _Title extends StatelessWidget {
  const _Title({required this.text, required this.completed});

  final String text;
  final bool completed;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        fontSize: 22,
        fontWeight: FontWeight.w600,
        color: completed ? AppColors.textTertiary : AppColors.textPrimary,
        height: 1.3,
        decoration: completed ? TextDecoration.lineThrough : TextDecoration.none,
      ),
    );
  }
}

/// Status pill — fills in brand blue when the Jira status_type resolves to
/// `done`, neutral grey otherwise. Mirrors the metadata strip's text-only
/// rendering elsewhere; the pill exists here because the detail screen has
/// the vertical space for a more prominent status indicator.
class _JiraStatusPill extends StatelessWidget {
  const _JiraStatusPill({required this.status, required this.statusType});

  final String? status;
  final String? statusType;

  @override
  Widget build(BuildContext context) {
    if (status == null || status!.isEmpty) return const SizedBox.shrink();
    final isDone = statusType == 'done';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingM, vertical: AppStyles.spacingS),
      decoration: BoxDecoration(
        color: isDone ? AppColors.brandPrimary.withValues(alpha: 0.15) : AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusPill),
        border: Border.all(color: isDone ? AppColors.brandPrimary : AppColors.textTertiary.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(
              color: isDone ? AppColors.brandPrimary : AppColors.textTertiary,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: AppStyles.spacingS),
          Text(
            status!,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: isDone ? AppColors.brandPrimary : AppColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}

/// Two-column key/value metadata table. Each row renders only when the
/// underlying value is set — no "—" placeholders.
class _MetaTable extends StatelessWidget {
  const _MetaTable({required this.item, required this.isJira});

  final ActionItem item;
  final bool isJira;

  @override
  Widget build(BuildContext context) {
    final ext = item.externalSource;
    final rows = <_MetaRow>[];
    if (isJira) {
      final project = ext?.jiraProjectKey;
      if (project != null && project.isNotEmpty) {
        rows.add(_MetaRow(label: 'Project', value: project));
      }
      final priority = ext?.jiraPriority;
      if (priority != null && priority.isNotEmpty && priority != 'None') {
        rows.add(_MetaRow(label: 'Priority', value: priority));
      }
      final days = ext?.daysAtStatus;
      if (days != null && days > 0) {
        rows.add(_MetaRow(label: 'In status for', value: '${days}d'));
      }
    } else {
      rows.add(const _MetaRow(label: 'Source', value: 'From conversation'));
    }
    final due = item.dueAt;
    if (due != null) rows.add(_MetaRow(label: 'Due', value: _formatDue(due)));
    final created = item.createdAt;
    if (created != null) rows.add(_MetaRow(label: 'Created', value: _formatRelative(DateTime.now().difference(created))));
    if (rows.isEmpty) return const SizedBox.shrink();
    return Container(
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        border: Border.all(color: AppColors.textTertiary.withValues(alpha: 0.15)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL, vertical: AppStyles.spacingS),
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) ...[
            if (i > 0) const Divider(height: 1, color: AppColors.backgroundTertiary),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      rows[i].label,
                      style: const TextStyle(fontSize: 14, color: AppColors.textTertiary, fontWeight: FontWeight.w500),
                    ),
                  ),
                  Text(
                    rows[i].value,
                    style: const TextStyle(fontSize: 14, color: AppColors.textPrimary, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  static String _formatDue(DateTime due) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final dueDay = DateTime(due.year, due.month, due.day);
    final diff = dueDay.difference(today).inDays;
    if (diff < 0) return 'Overdue ${-diff}d';
    if (diff == 0) return 'Today';
    if (diff == 1) return 'Tomorrow';
    if (diff < 7) return 'In ${diff}d';
    if (diff < 30) return 'In ${(diff / 7).round()}w';
    return 'In ${(diff / 30).round()}mo';
  }

  static String _formatRelative(Duration age) {
    if (age.inDays < 1) return age.inHours <= 0 ? 'Just now' : '${age.inHours}h ago';
    if (age.inDays < 30) return '${age.inDays}d ago';
    if (age.inDays < 365) return '${(age.inDays / 30).round()}mo ago';
    return '${(age.inDays / 365).round()}y ago';
  }
}

class _MetaRow {
  const _MetaRow({required this.label, required this.value});
  final String label;
  final String value;
}

class _PrimaryAction extends StatelessWidget {
  const _PrimaryAction({
    required this.isJira,
    required this.twoWaySync,
    required this.busy,
    required this.onPressed,
  });

  final bool isJira;
  final bool twoWaySync;
  final bool busy;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final disabled = isJira && !twoWaySync;
    return SizedBox(
      width: double.infinity,
      height: AppStyles.touchTargetMinimum,
      child: FilledButton(
        onPressed: disabled ? null : onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.brandPrimary,
          foregroundColor: AppColors.textPrimary,
          disabledBackgroundColor: AppColors.backgroundSecondary,
          disabledForegroundColor: AppColors.textTertiary,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppStyles.radiusLarge)),
        ),
        child: busy
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.textPrimary),
              )
            : Text(
                disabled ? 'Enable Jira write-back to mark Done' : (isJira ? 'Mark as Done' : 'Mark complete'),
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
      ),
    );
  }
}

class _OpenInJiraButton extends StatelessWidget {
  const _OpenInJiraButton({required this.url, required this.onTap});

  final String url;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: AppStyles.touchTargetMinimum,
      child: OutlinedButton.icon(
        onPressed: onTap,
        icon: const Icon(Icons.open_in_new_rounded, size: 16),
        label: const Text('Open in Jira', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textPrimary,
          side: BorderSide(color: AppColors.textTertiary.withValues(alpha: 0.3)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppStyles.radiusLarge)),
        ),
      ),
    );
  }
}

class _CompletedBanner extends StatelessWidget {
  const _CompletedBanner();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppStyles.spacingXXL),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_circle_rounded, size: 40, color: AppColors.brandPrimary),
            const SizedBox(height: AppStyles.spacingM),
            const Text(
              'Done.',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
            ),
            const SizedBox(height: AppStyles.spacingXS),
            const Text(
              "It's no longer in your plan.",
              style: TextStyle(fontSize: 14, color: AppColors.textTertiary),
            ),
            const SizedBox(height: AppStyles.spacingXL),
            FilledButton(
              onPressed: () => Navigator.of(context).maybePop(),
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.backgroundSecondary,
                foregroundColor: AppColors.textPrimary,
              ),
              child: const Text('Back to Plan'),
            ),
          ],
        ),
      ),
    );
  }
}
