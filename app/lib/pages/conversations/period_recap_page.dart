import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/recaps.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Loads a period recap. Injectable so tests need no network.
typedef PeriodRecapLoader = Future<ApiResult<wire.GeneratedPeriodRecapResponse>> Function(RecapPeriod period);

Future<ApiResult<wire.GeneratedPeriodRecapResponse>> _loadPeriodRecap(RecapPeriod period) => getPeriodRecap(period);

/// The weekly and monthly recaps (#4468): totals against the previous period, the busiest day,
/// the people talked to most, and the period's highlights, decisions, open questions and tasks.
/// Rolled up on the server from the daily recaps, so opening it never spends chat quota.
class PeriodRecapPage extends StatefulWidget {
  const PeriodRecapPage({super.key, this.initialPeriod = RecapPeriod.week, PeriodRecapLoader? load})
      : load = load ?? _loadPeriodRecap;

  final RecapPeriod initialPeriod;
  final PeriodRecapLoader load;

  @override
  State<PeriodRecapPage> createState() => _PeriodRecapPageState();
}

class _PeriodRecapPageState extends State<PeriodRecapPage> {
  late RecapPeriod _period = widget.initialPeriod;
  ApiResult<wire.GeneratedPeriodRecapResponse>? _result;

  /// Bumped by every load: only the newest request's answer is shown, so a slow
  /// week answer cannot land after Week → Month → Week was already answered.
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _generation++;
    super.dispose();
  }

  /// Loads the selected period. A pull-to-refresh passes [keepShown] so the recap
  /// stays on screen under the refresh spinner until the new one arrives.
  Future<void> _load({bool keepShown = false}) async {
    final generation = ++_generation;
    final period = _period;
    if (!keepShown) setState(() => _result = null);
    final result = await widget.load(period);
    if (!mounted || generation != _generation) return;
    setState(() => _result = result);
  }

  void _select(RecapPeriod period) {
    if (period == _period) return;
    _period = period;
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.recaps)),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xs),
            child: Wrap(
              spacing: OmiSpacing.xs,
              children: [
                OmiFilterChip(
                  label: context.l10n.thisWeek,
                  selected: _period == RecapPeriod.week,
                  onSelected: () => _select(RecapPeriod.week),
                ),
                OmiFilterChip(
                  label: context.l10n.thisMonth,
                  selected: _period == RecapPeriod.month,
                  onSelected: () => _select(RecapPeriod.month),
                ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              color: OmiColors.onAccent,
              backgroundColor: OmiColors.accent,
              onRefresh: () => _load(keepShown: true),
              child: _buildBody(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    final result = _result;
    return switch (result) {
      null => const OmiLoadingState(),
      ApiFailure() => _scrollable(OmiErrorState(message: context.l10n.somethingWentWrong, onRetry: _load)),
      ApiSuccess(:final data, :final truncated) => _withPartialNotice(
          truncated,
          data.daysRecorded == 0 && (data.topPeople ?? const []).isEmpty && (data.openActionItems ?? const []).isEmpty
              ? _scrollable(OmiEmptyState(icon: Icons.calendar_month_outlined, title: context.l10n.noRecapForPeriod))
              : _RecapContent(recap: data),
        ),
    };
  }

  /// A full-height scrollable around a state, so pull-to-refresh works on it too.
  Widget _scrollable(Widget child) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(child: child),
        ),
      ),
    );
  }

  /// A recap the server had to cut short (its people or task read ran out of
  /// budget) says so above what it has, with Try Again.
  Widget _withPartialNotice(bool truncated, Widget body) {
    if (!truncated) return body;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiPartialNotice(onRetry: _load),
        Expanded(child: body),
      ],
    );
  }
}

class _RecapContent extends StatelessWidget {
  const _RecapContent({required this.recap});

  final wire.GeneratedPeriodRecapResponse recap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final stats = recap.stats;
    final previous = recap.previous;
    final busiest = recap.busiestDay;
    final range = '${dates.date(DateTime.parse(recap.startDate))} – ${dates.date(DateTime.parse(recap.endDate))}';
    final people = recap.topPeople ?? const [];
    final highlights = recap.highlights ?? const [];
    final decisions = recap.decisions ?? const [];
    final questions = recap.openQuestions ?? const [];
    final actions = recap.openActionItems ?? const [];

    // Inset and spaced like the settings pages: a margin on both sides and a gap between groups.
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.fromLTRB(
        OmiSpacing.md,
        OmiSpacing.md,
        OmiSpacing.md,
        MediaQuery.paddingOf(context).bottom + OmiSpacing.md,
      ),
      children: _spaced([
        OmiSettingsGroup(
          header: l10n.overview,
          headerSubtitle: range,
          children: [
            OmiSettingsRow(
              title: l10n.conversations,
              value: '${stats?.totalConversations ?? 0}',
              subtitle: previous == null ? null : l10n.recapPrevious('${previous.totalConversations}'),
            ),
            OmiSettingsRow(
              title: l10n.timeRecorded,
              value: OmiDuration.compact((stats?.totalDurationMinutes ?? 0) * 60, l10n),
              subtitle: previous == null
                  ? null
                  : l10n.recapPrevious(OmiDuration.compact(previous.totalDurationMinutes * 60, l10n)),
            ),
            OmiSettingsRow(title: l10n.tasks, value: '${stats?.actionItemsCreated ?? 0}'),
            OmiSettingsRow(title: l10n.memories, value: '${stats?.memoriesCreated ?? 0}'),
            if (busiest != null)
              OmiSettingsRow(
                title: l10n.busiestDay,
                value: dates.date(DateTime.parse(busiest.date)),
                subtitle: l10n.conversationCount(busiest.totalConversations),
              ),
          ],
        ),
        if (people.isNotEmpty)
          OmiSettingsGroup(
            header: l10n.peopleYouTalkedToMost,
            children: [
              for (final person in people)
                OmiSettingsRow(
                  title: person.name,
                  value: OmiDuration.compact(person.talkMinutes * 60, l10n),
                  subtitle: l10n.conversationCount(person.conversations),
                ),
            ],
          ),
        if (highlights.isNotEmpty)
          OmiSettingsGroup(
            header: l10n.highlights,
            children: [
              for (final highlight in highlights) _highlightRow(highlight),
            ],
          ),
        if (decisions.isNotEmpty)
          OmiSettingsGroup(
            header: l10n.decisions,
            children: [for (final decision in decisions) OmiSettingsRow(title: decision.decision)],
          ),
        if (questions.isNotEmpty)
          OmiSettingsGroup(
            header: l10n.unresolvedQuestions,
            children: [for (final question in questions) OmiSettingsRow(title: question.question)],
          ),
        if (actions.isNotEmpty)
          OmiSettingsGroup(
            header: l10n.openTasks,
            children: [for (final action in actions) OmiSettingsRow(title: action.description)],
          ),
      ]),
    );
  }

  /// The groups with a gap before each one after the first.
  static List<Widget> _spaced(List<Widget> groups) => [
        for (final (index, group) in groups.indexed) ...[
          if (index > 0) const SizedBox(height: OmiSpacing.xxl),
          group,
        ],
      ];

  /// The topic heads the row and the summary explains it; a highlight with no
  /// topic is titled by its summary rather than showing an empty title.
  static Widget _highlightRow(wire.GeneratedPeriodRecapHighlight highlight) {
    final topic = highlight.topic?.trim() ?? '';
    final summary = highlight.summary?.trim() ?? '';
    final heading = topic.isNotEmpty ? topic : summary;
    final emoji = highlight.emoji?.trim() ?? '';
    return OmiSettingsRow(
      title: emoji.isEmpty ? heading : '$emoji $heading',
      subtitle: topic.isNotEmpty && summary.isNotEmpty ? summary : null,
    );
  }
}
