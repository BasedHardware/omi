import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/dream.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/dream_report.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef DreamReportLoader = Future<ApiResult<DreamReport>> Function();
typedef DreamRunner = Future<ApiResult<DreamRun>> Function();

/// What the background agent looked at and what it would change, newest pass first, with a Run
/// Now for dogfooding. Reached from Review only for accounts in the dream cohort.
class DreamReportPage extends StatefulWidget {
  const DreamReportPage({super.key, this.loadReport, this.runNow});

  final DreamReportLoader? loadReport;
  final DreamRunner? runNow;

  @override
  State<DreamReportPage> createState() => _DreamReportPageState();
}

class _DreamReportPageState extends State<DreamReportPage> {
  DreamReport? _report;
  bool _loading = true;
  bool _failed = false;
  bool _running = false;
  String? _expandedRunId;

  DreamReportLoader get _load => widget.loadReport ?? api.getDreamReport;
  DreamRunner get _run => widget.runNow ?? api.runDreamNow;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = _report == null;
      _failed = false;
    });
    final result = await _load();
    if (!mounted) return;
    setState(() {
      _loading = false;
      switch (result) {
        case ApiSuccess(:final data):
          _report = data;
          _expandedRunId ??= data.runs.isEmpty ? null : data.runs.first.runId;
        case ApiFailure():
          _failed = _report == null;
      }
    });
  }

  Future<void> _runNow() async {
    final l10n = context.l10n;
    setState(() => _running = true);
    final result = await _run();
    if (!mounted) return;
    setState(() => _running = false);
    switch (result) {
      case ApiSuccess(:final data):
        if (data.status == DreamRunStatus.idle) {
          OmiFeedback.info(context, l10n.dreamReportIdle);
        } else {
          _expandedRunId = data.runId;
        }
        await _refresh();
      case ApiFailure(:final problem):
        final message = switch (api.dreamRunNowRefusal(problem)) {
          DreamRunNowRefusal.inProgress => l10n.dreamReportRunInProgress,
          DreamRunNowRefusal.limit => l10n.dreamReportRunLimit,
          null => l10n.dreamReportRunFailed,
        };
        OmiFeedback.error(context, message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final report = _report;
    final Widget body;
    if (_loading) {
      body = const OmiLoadingState();
    } else if (_failed || report == null) {
      body = OmiErrorState(message: l10n.dreamReportLoadFailed, onRetry: _refresh);
    } else {
      body = RefreshIndicator(
        onRefresh: _refresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
          children: [
            _StatusCard(report: report, running: _running, onRunNow: _runNow),
            if (report.runs.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xl),
                child: OmiEmptyState(
                  icon: Icons.nightlight_outlined,
                  title: l10n.dreamReportEmptyTitle,
                  message: l10n.dreamReportEmptyBody,
                ),
              )
            else
              for (final run in report.runs)
                _RunCard(
                  key: ValueKey('dream_run_${run.runId}'),
                  run: run,
                  live: report.live,
                  expanded: run.runId == _expandedRunId,
                  onToggle: () => setState(() => _expandedRunId = run.runId == _expandedRunId ? null : run.runId),
                ),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.dreamReportTitle)),
      body: body,
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.report, required this.running, required this.onRunNow});

  final DreamReport report;
  final bool running;
  final VoidCallback onRunNow;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final canRun = report.manualRunsLeft > 0 && !running;
    return Container(
      margin: const EdgeInsets.only(bottom: OmiSpacing.md),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(report.live ? Icons.auto_fix_high : Icons.visibility_outlined,
                  size: 18, color: OmiColors.textSecondary),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Text(
                  report.live ? l10n.dreamReportLiveBanner : l10n.dreamReportShadowBanner,
                  style: OmiType.subhead,
                ),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.sm),
          Text(
            [
              l10n.dreamReportPasses(report.passesToday, report.passesLimit),
              l10n.dreamReportQueued(report.queuedChanges),
            ].join(' · '),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.sm),
          Row(
            children: [
              OmiButton.secondary(
                key: const Key('dream_run_now'),
                label: l10n.dreamReportRunNow,
                icon: Icons.play_arrow_rounded,
                isLoading: running,
                onPressed: canRun ? onRunNow : null,
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Text(
                  report.manualRunsLeft > 0
                      ? l10n.dreamReportRunsLeft(report.manualRunsLeft)
                      : l10n.dreamReportRunLimit,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RunCard extends StatelessWidget {
  const _RunCard({super.key, required this.run, required this.live, required this.expanded, required this.onToggle});

  final DreamRun run;
  final bool live;
  final bool expanded;
  final VoidCallback onToggle;

  String _summary(BuildContext context) {
    final l10n = context.l10n;
    return switch (run.status) {
      DreamRunStatus.failed => l10n.dreamReportFailed(run.errorType ?? '—'),
      DreamRunStatus.deadline => l10n.dreamReportTimedOut,
      _ when run.isEmpty => l10n.dreamReportNothingFound,
      _ => l10n.dreamReportFound(run.edits.length, run.questions.length + run.slowTasks.length),
    };
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final failed = run.status == DreamRunStatus.failed || run.status == DreamRunStatus.deadline;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            borderRadius: OmiRadius.lgAll,
            onTap: onToggle,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 14, OmiSpacing.sm, 14),
              child: Row(
                children: [
                  Icon(
                    failed ? Icons.error_outline : Icons.nightlight_outlined,
                    size: 18,
                    color: failed ? OmiColors.danger : OmiColors.textSecondary,
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${dates.dayHeader(run.createdAt)} ${dates.time(run.createdAt)} · '
                          '${run.manual ? l10n.dreamReportManual : l10n.dreamReportScheduled}',
                          style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 2),
                        Text(_summary(context), style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                      ],
                    ),
                  ),
                  Icon(expanded ? Icons.expand_less : Icons.expand_more, color: OmiColors.textSecondary),
                ],
              ),
            ),
          ),
          if (expanded) _RunDetail(run: run, live: live),
        ],
      ),
    );
  }
}

IconData _editIcon(String kind) => switch (kind) {
      'spelling' => Icons.spellcheck,
      'merge_people' => Icons.people_outline,
      'merge_memories' => Icons.call_merge,
      'memory' => Icons.lightbulb_outline,
      'entity_summary' => Icons.badge_outlined,
      'close_task' => Icons.task_alt,
      'retire_task' => Icons.remove_done,
      _ => Icons.auto_fix_high_outlined,
    };

class _RunDetail extends StatelessWidget {
  const _RunDetail({required this.run, required this.live});

  final DreamRun run;
  final bool live;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final secondary = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
    final children = <Widget>[
      Text(
        [
          l10n.dreamReportStats(run.recordsRead, run.tokens),
          '\$${run.costUsd.toStringAsFixed(3)}',
          if (run.dirtyDropped > 0) l10n.dreamReportDropped(run.dirtyDropped),
        ].join(' · '),
        style: secondary,
      ),
    ];
    if (run.edits.isNotEmpty) {
      children.add(ReviewSectionLabel(label: live ? l10n.dreamReportFixed : l10n.dreamReportWouldFix));
      for (final edit in run.edits) {
        children.add(_EditRow(edit: edit));
      }
    }
    if (run.questions.isNotEmpty) {
      children.add(ReviewSectionLabel(label: l10n.dreamReportWouldAsk));
      for (final question in run.questions) {
        children.add(_Line(icon: Icons.help_outline, text: question));
      }
    }
    if (run.slowTasks.isNotEmpty) {
      children.add(ReviewSectionLabel(label: l10n.dreamReportWouldSuggestTasks));
      for (final task in run.slowTasks) {
        children.add(_Line(icon: Icons.add_task, text: task));
      }
    }
    if (run.vocabulary.isNotEmpty) {
      children.add(ReviewSectionLabel(label: l10n.dreamReportLearnedWords));
      children.add(Wrap(
        spacing: OmiSpacing.xs,
        runSpacing: OmiSpacing.xs,
        children: [
          for (final term in run.vocabulary)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
              child: Text(term.spelling, style: OmiType.footnote),
            ),
        ],
      ));
    }
    if (run.feedback.isNotEmpty || run.privacyRejected > 0) {
      children.add(ReviewSectionLabel(label: l10n.dreamReportFeedback));
      for (final item in run.feedback) {
        children.add(_Line(
          icon: Icons.outbox_outlined,
          text: '${item.component} · ${item.failureClass} · ${item.count}',
        ));
      }
      if (run.privacyRejected > 0) {
        children.add(_Line(icon: Icons.shield_outlined, text: l10n.dreamReportPrivacyHeld(run.privacyRejected)));
      }
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );
  }
}

class _EditRow extends StatelessWidget {
  const _EditRow({required this.edit});

  final DreamEdit edit;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final change = edit.before.isNotEmpty && edit.after.isNotEmpty ? '${edit.before} → ${edit.after}' : edit.after;
    return Container(
      margin: const EdgeInsets.only(bottom: OmiSpacing.xs),
      padding: const EdgeInsets.all(OmiSpacing.sm),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(_editIcon(edit.kind), size: 16, color: OmiColors.textSecondary),
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(edit.targetLabel.isEmpty ? l10n.dreamReportDeletedItem : edit.targetLabel,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                if (change.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(change, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
                  ),
                if (edit.reason.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(edit.reason, style: OmiType.footnote),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(icon, size: 16, color: OmiColors.textSecondary),
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(child: Text(text, style: OmiType.subhead)),
        ],
      ),
    );
  }
}
