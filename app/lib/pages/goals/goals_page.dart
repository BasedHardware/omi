import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// How long the native progress control waits after its last change before saving it.
@visibleForTesting
const goalProgressSaveDelay = Duration(milliseconds: 300);

/// Goals, opened from Settings. They used to sit at the top of the Conversations tab, which no
/// longer exists: Home shows only recaps and conversations.
class GoalsPage extends StatefulWidget {
  const GoalsPage({super.key});

  @override
  State<GoalsPage> createState() => _GoalsPageState();
}

class _GoalsPageState extends State<GoalsPage> {
  final GoalEmojis _emojis = GoalEmojis();

  /// Native progress waiting for its debounce or its save, by goal id. The projection shows it, so
  /// the control does not jump back while the owner saves.
  final Map<String, double> _pendingProgress = {};
  final Map<String, Timer> _progressTimers = {};
  final Map<String, VoidCallback> _progressSaves = {};

  @override
  void initState() {
    super.initState();
    _emojis.load();
    if (nativePresentationEnabled) _emojis.addListener(_repaint);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<GoalsProvider>().refresh();
    });
  }

  void _repaint() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    // Leaving the page never drops the last change: pending saves run now.
    for (final timer in _progressTimers.values) {
      timer.cancel();
    }
    for (final save in _progressSaves.values.toList()) {
      save();
    }
    _emojis.removeListener(_repaint);
    _emojis.dispose();
    super.dispose();
  }

  /// A level value from Swift, rounded to the goal's grid (whole steps, otherwise one decimal) and
  /// kept within its target.
  static double _roundedProgress(Goal goal, num value, double? step) {
    final rounded = step != null ? value.roundToDouble() : (value * 10).roundToDouble() / 10;
    return rounded.clamp(0.0, goal.targetValue);
  }

  /// Keeps the latest value and saves it once [goalProgressSaveDelay] passes without another change.
  void _changeProgress(GoalsProvider provider, Goal goal, double value) {
    updateGoalProgressUI(goal, value);
    setState(() => _pendingProgress[goal.id] = value);
    final owner = AuthService.instance.captureSessionSnapshot();
    _progressTimers.remove(goal.id)?.cancel();
    void save() {
      _progressTimers.remove(goal.id);
      _progressSaves.remove(goal.id);
      if (owner == null || !AuthService.instance.isSessionSnapshotCurrent(owner)) {
        _pendingProgress.remove(goal.id);
        return;
      }
      PlatformManager.instance.analytics.goalProgressChanged(
        goalId: goal.id,
        oldValue: goal.currentValue,
        newValue: value,
        targetValue: goal.targetValue,
      );
      unawaited(saveGoalProgress(provider, goal, value).whenComplete(() {
        if (_pendingProgress[goal.id] != value) return;
        _pendingProgress.remove(goal.id);
        _repaint();
      }));
    }

    _progressSaves[goal.id] = save;
    _progressTimers[goal.id] = Timer(goalProgressSaveDelay, save);
  }

  List<NativeRow> _goalRows(BuildContext context, GoalsProvider provider, int index, Goal goal) {
    final l10n = context.l10n;
    final target = goal.targetValue;
    final pending = _pendingProgress[goal.id];
    final current = pending ?? goal.currentValue;
    final progress = '${goalValueLabel(current)}/${goalValueLabel(target)}';
    // Degenerate targets keep a label: a level control needs a finite, positive range.
    final adjustable = target.isFinite && target > 0;
    // Small whole targets step by one, as the Flutter slider's divisions do; the control shows the
    // value on that grid while the subtitle keeps the stored progress.
    final step = adjustable && goalSliderDivisions(target) != null ? 1.0 : null;
    final clamped = adjustable && current.isFinite ? current.clamp(0.0, target) : 0.0;
    final value = step == null ? clamped : clamped.roundToDouble();
    return [
      NativeRow(
        'goal:$index',
        '${_emojis.of(goal.id)} ${goal.title}',
        kind: 'navigation',
        subtitle: progress,
        options: {'edit': l10n.edit, 'delete': l10n.delete},
        swipeTrailing: const ['delete'],
        action: (option) {
          if (option == 'delete') {
            PlatformManager.instance.analytics.goalDeleted(goalId: goal.id, source: 'home', method: 'swipe');
            deleteGoalAndEmoji(context, goal, _emojis);
            return;
          }
          editGoal(context, goal, _emojis);
          WidgetsBinding.instance.addPostFrameCallback((_) {
            PlatformManager.instance.analytics.goalItemTappedForEdit(goalId: goal.id, source: 'home');
          });
        },
      ),
      if (adjustable)
        NativeRow(
          'goal_progress:$index',
          l10n.current,
          kind: 'level',
          subtitle: progress,
          value: value,
          maximumValue: target,
          step: step,
          action: (input) => _changeProgress(provider, goal, _roundedProgress(goal, input as num, step)),
        )
      else
        NativeRow('goal_progress:$index', l10n.current, kind: 'label', subtitle: progress),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final goals = context.watch<GoalsProvider>();
    final fallback = Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.goals),
        actions: [
          OmiIconButton(
            key: const Key('goals_add'),
            icon: const Icon(Icons.add),
            label: context.l10n.addGoal,
            onPressed: () => addGoal(context, _emojis),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => context.read<GoalsProvider>().refresh(),
        child: ListView(
          padding: const EdgeInsets.only(bottom: OmiSpacing.xl),
          children: [
            GoalsWidget(showHeader: false, emojis: _emojis),
            if (!goals.isLoading && goals.goals.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 120),
                child: OmiEmptyState(
                  icon: Icons.flag_outlined,
                  title: context.l10n.goals,
                  action: OmiButton.secondary(
                    label: context.l10n.addGoal,
                    onPressed: () => addGoal(context, _emojis),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
    if (!nativePresentationEnabled) return fallback;
    final l10n = context.l10n;
    // Row ids address this list as projected; each command acts on the goal it showed.
    final projected = goals.goals.toList();
    return IosNativeSurface(
      title: l10n.goals,
      fallback: fallback,
      loading: goals.isLoading && projected.isEmpty,
      onRefresh: (_) => goals.refresh(),
      nativeOwner: _GoalsResumeRefresh(goals: goals),
      toolbar: [
        NativeRow('goals_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
        NativeRow('goals_add', l10n.addGoal, symbol: 'plus', action: (_) => addGoal(context, _emojis)),
      ],
      sections: [
        if (projected.isNotEmpty)
          NativeSection('goals', [
            for (final (index, goal) in projected.indexed) ..._goalRows(context, goals, index, goal),
          ])
        else if (!goals.isLoading)
          NativeSection(
              'goals_empty',
              [
                NativeRow('goals_empty_add', l10n.addGoal, symbol: 'plus', action: (_) => addGoal(context, _emojis)),
              ],
              title: l10n.goals),
      ],
    );
  }
}

/// Refreshes goals when the app returns to the foreground, as the Flutter list does; mounted only
/// with the native renderer, which does not mount that list.
class _GoalsResumeRefresh extends StatefulWidget {
  const _GoalsResumeRefresh({required this.goals});

  final GoalsProvider goals;

  @override
  State<_GoalsResumeRefresh> createState() => _GoalsResumeRefreshState();
}

class _GoalsResumeRefreshState extends State<_GoalsResumeRefresh> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) widget.goals.refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
