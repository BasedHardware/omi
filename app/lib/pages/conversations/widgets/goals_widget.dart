import 'dart:convert';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/pages/action_items/widgets/goal_form_sheet.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Keep integer stepping for small goals without asking RenderSlider to paint
/// one division per unit for arbitrarily large targets.
///
/// A target of one billion previously produced one billion divisions. Flutter
/// walks the divisions during every slider paint even when tick marks are
/// hidden, which can block the UI thread for several seconds. The native progress control steps by
/// one exactly when this is set.
int? goalSliderDivisions(double targetValue) {
  if (!targetValue.isFinite || targetValue <= 0 || targetValue > 100) return null;
  final roundedTarget = targetValue.round();
  return targetValue == roundedTarget ? roundedTarget : null;
}

/// At most this many goals; adding another explains the limit instead.
const int maxGoalCount = 4;

/// The emojis the goal sheet offers when editing.
const List<String> goalEmojiChoices = [
  '🎯',
  '💪',
  '📚',
  '💰',
  '🏃',
  '🧘',
  '💡',
  '🔥',
  '⭐',
  '🚀',
  '💎',
  '🏆',
  '📈',
  '❤️',
  '🎨',
  '🎵',
  '✈️',
  '🏠',
  '🌱',
  '⏰',
];

/// Each goal's emoji (goal id -> emoji), kept on this device only. Listeners repaint on change.
class GoalEmojis extends ChangeNotifier {
  GoalEmojis({this.onSaved});

  static const String _goalsEmojiKey = 'goals_tracker_emojis';

  /// Runs after the emojis were written.
  final VoidCallback? onSaved;

  Map<String, String> _goalEmojis = {};
  bool _disposed = false;

  String of(String goalId) => _goalEmojis[goalId] ?? '🎯';

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final emojisJson = prefs.getString(_goalsEmojiKey);

      if (emojisJson != null && !_disposed) {
        final Map<String, dynamic> decoded = json.decode(emojisJson);
        _goalEmojis = decoded.map((k, v) => MapEntry(k, v.toString()));
        notifyListeners();
      }
    } catch (_) {}
  }

  void set(String goalId, String emoji) {
    _goalEmojis[goalId] = emoji;
    if (!_disposed) notifyListeners();
  }

  void remove(String goalId) {
    _goalEmojis.remove(goalId);
    if (!_disposed) notifyListeners();
  }

  Future<void> save() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final emojisJson = json.encode(_goalEmojis);
      await prefs.setString(_goalsEmojiKey, emojisJson);
      onSaved?.call();
    } catch (_) {}
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

/// The emoji a new goal starts with, picked from keywords in its [title].
String goalSmartEmoji(String title) {
  final lowerTitle = title.toLowerCase();
  // Keyword to emoji mapping - order matters (more specific first)
  final Map<List<String>, String> keywordMap = {
    // Money/Business goals
    ['revenue', 'money', 'income', 'profit', 'sales', '\$', 'dollar', 'earn']: '💰',
    [
      'users',
      'customers',
      'clients',
      'subscribers',
      'followers',
      'growth',
      'million',
      '1m',
      '10k',
      '100k',
      'mrr',
      'arr',
    ]: '🚀',
    ['startup', 'launch', 'business', 'company']: '🏆',
    ['invest', 'stock', 'crypto', 'trading']: '📈',

    // Health/Fitness goals
    ['workout', 'gym', 'exercise', 'lift', 'muscle', 'strength', 'pushup', 'pullup']: '💪',
    ['run', 'marathon', 'jog', 'cardio', 'steps', 'walk', 'mile', 'km']: '🏃',
    ['weight', 'lose', 'fat', 'diet', 'calories', 'kg', 'lbs', 'pounds']: '⚖️',
    ['meditat', 'mindful', 'yoga', 'breath', 'calm', 'peace', 'zen']: '🧘',
    ['sleep', 'rest', 'hours']: '😴',
    ['water', 'hydrat', 'drink']: '💧',
    ['health', 'wellness', 'healthy']: '❤️',

    // Learning/Education goals
    ['read', 'book', 'pages', 'chapter']: '📚',
    ['learn', 'study', 'course', 'class', 'skill', 'certif']: '🎓',
    ['code', 'program', 'develop', 'app', 'software', 'tech']: '💻',
    ['language', 'spanish', 'french', 'chinese', 'english', 'german']: '🗣️',

    // Creative goals
    ['write', 'blog', 'article', 'post', 'content', 'words']: '✍️',
    ['video', 'youtube', 'tiktok', 'film']: '🎬',
    ['music', 'song', 'piano', 'guitar', 'sing']: '🎵',
    ['art', 'draw', 'paint', 'design', 'create']: '🎨',
    ['photo', 'picture', 'camera']: '📸',

    // Productivity goals
    ['task', 'todo', 'complete', 'finish', 'done']: '✅',
    ['habit', 'daily', 'streak', 'consistent', 'routine']: '🔥',
    ['time', 'hour', 'minute', 'focus', 'pomodoro', 'productive']: '⏰',
    ['project', 'ship', 'deliver', 'deadline']: '🎯',

    // Travel/Lifestyle goals
    ['travel', 'trip', 'visit', 'country', 'city', 'vacation']: '✈️',
    ['home', 'house', 'apartment', 'move', 'buy']: '🏠',
    ['save', 'saving', 'budget', 'emergency fund']: '🏦',

    // Social/Relationship goals
    ['friend', 'social', 'network', 'connect', 'meet']: '👥',
    ['family', 'kids', 'parent']: '👨‍👩‍👧',
    ['date', 'relationship', 'love']: '💕',

    // General achievement
    ['goal', 'target', 'achieve', 'accomplish']: '🎯',
    ['win', 'first', 'best', 'top', 'champion']: '🏆',
    ['grow', 'improve', 'better', 'progress']: '🌱',
    ['star', 'success', 'excellent']: '⭐',
  };

  // Check each keyword group
  for (final entry in keywordMap.entries) {
    for (final keyword in entry.key) {
      if (lowerTitle.contains(keyword)) {
        return entry.value;
      }
    }
  }

  // Default emoji if no match
  return '🎯';
}

/// A goal value as the list shows it: whole numbers plainly, others to one decimal.
String goalValueLabel(double v) {
  return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
}

/// "current/target", as the goal list shows progress.
String goalProgressLabel(Goal goal) => '${goalValueLabel(goal.currentValue)}/${goalValueLabel(goal.targetValue)}';

/// Opens the add sheet, or explains the limit once there are [maxGoalCount] goals.
void addGoal(BuildContext context, GoalEmojis emojis) {
  final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
  if (goalsProvider.goals.length >= maxGoalCount) {
    OmiFeedback.info(context, context.l10n.maximumGoalsAllowed(maxGoalCount));
    return;
  }

  PlatformManager.instance.analytics.goalAddButtonTapped(source: 'home');
  OmiHaptics.light();
  showGoalFormSheet(
    context,
    onSave: (title, current, target, _) => saveGoal(goalsProvider, emojis, null, title, current, target, null),
  );
}

/// Opens [goal] in the edit sheet, with its emoji and Delete.
void editGoal(BuildContext context, Goal goal, GoalEmojis emojis) {
  final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
  OmiHaptics.light();
  showGoalFormSheet(
    context,
    goal: goal,
    emojiChoices: goalEmojiChoices,
    initialEmoji: emojis.of(goal.id),
    onSave: (title, current, target, emoji) => saveGoal(goalsProvider, emojis, goal, title, current, target, emoji),
    onDelete: () {
      PlatformManager.instance.analytics.goalDeleted(goalId: goal.id, source: 'home', method: 'button');
      deleteGoalAndEmoji(context, goal, emojis);
    },
  );
}

/// Updates [existingGoal], or creates a goal with a keyword emoji, then stores the emojis.
Future<void> saveGoal(
  GoalsProvider goalsProvider,
  GoalEmojis emojis,
  Goal? existingGoal,
  String title,
  double current,
  double target,
  String? emoji,
) async {
  if (existingGoal != null) {
    await goalsProvider.updateGoal(existingGoal.id, title: title, currentValue: current, targetValue: target);

    PlatformManager.instance.analytics.goalUpdated(goalId: existingGoal.id, source: 'home');
    if (emoji != null) {
      PlatformManager.instance.analytics.goalEmojiSelected(emoji: emoji);
      emojis.set(existingGoal.id, emoji);
    }
  } else {
    final smartEmoji = goalSmartEmoji(title);
    final created = await goalsProvider.createGoal(
      title: title,
      goalType: 'numeric',
      targetValue: target,
      currentValue: current,
    );

    if (created != null) {
      PlatformManager.instance.analytics.goalCreated(
        goalId: created.id,
        titleLength: title.length,
        targetValue: target,
        source: 'home',
      );
      emojis.set(created.id, smartEmoji);
    }
  }

  await emojis.save();
}

/// Immediate with Undo (D5); the emoji is forgotten once the delete commits.
void deleteGoalAndEmoji(BuildContext context, Goal goal, GoalEmojis emojis) {
  final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
  deleteGoalWithUndo(
    context,
    goalsProvider,
    goal,
    onDeleted: () {
      emojis.remove(goal.id);
      emojis.save();
    },
  );
}

/// Feedback while the progress changes; the provider repaints once it is saved.
void updateGoalProgressUI(Goal goal, double newValue) {
  if (newValue == goal.currentValue) return;
  OmiHaptics.light();
}

/// Saves the progress through the existing owner (storage and API).
Future<void> saveGoalProgress(GoalsProvider goalsProvider, Goal goal, double newValue) async {
  await goalsProvider.updateGoalProgress(goal.id, newValue);
}

/// Multi-goal widget supporting up to 3 goals with minimalistic UI
class GoalsWidget extends StatefulWidget {
  const GoalsWidget({super.key, this.onRefresh, this.showHeader = true, this.emojis});

  final VoidCallback? onRefresh;

  /// False when the host page's app bar already carries the "Goals" title and the add action.
  final bool showHeader;

  /// Shared with the host page; null keeps the widget's own, loaded on mount.
  final GoalEmojis? emojis;

  @override
  State<GoalsWidget> createState() => GoalsWidgetState();
}

class GoalsWidgetState extends State<GoalsWidget> with WidgetsBindingObserver {
  GoalEmojis? _ownEmojis;

  GoalEmojis get _emojis => widget.emojis ?? (_ownEmojis ??= GoalEmojis(onSaved: () => widget.onRefresh?.call()));

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _emojis.addListener(_repaint);
    if (widget.emojis == null) _emojis.load();
  }

  @override
  void didUpdateWidget(GoalsWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.emojis ?? _ownEmojis;
    if (!identical(previous, _emojis)) {
      previous?.removeListener(_repaint);
      _emojis.addListener(_repaint);
      if (widget.emojis == null) _emojis.load();
    }
  }

  void _repaint() {
    if (mounted) setState(() {});
  }

  void refresh() {
    Provider.of<GoalsProvider>(context, listen: false).refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _emojis.removeListener(_repaint);
    _ownEmojis?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      Provider.of<GoalsProvider>(context, listen: false).refresh();
    }
  }

  /// Colour carries state only: on track (green), under way (amber), not started (grey).
  Color _getColor(double progress) {
    if (progress >= 0.8) return OmiColors.success;
    if (progress >= 0.2) return OmiColors.warning;
    return OmiColors.textTertiary;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<GoalsProvider>(
      builder: (context, goalsProvider, child) {
        if (goalsProvider.isLoading) {
          return const SizedBox.shrink();
        }

        final goals = goalsProvider.goals;

        // If no goals, hide the widget (the Add Goal entry points live in
        // ActionItemsPage._buildGoalsRow and this widget's own header, shown
        // once at least one goal exists).
        if (goals.isEmpty) {
          return const SizedBox.shrink();
        }

        return Container(
          margin: const EdgeInsets.only(left: 16, right: 16),
          // The header row is as tall as its 44pt add button; the paddings around it
          // give back the 6pt it gained on each side over the 32pt circle it paints.
          padding: const EdgeInsets.only(top: 10, bottom: 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              if (widget.showHeader)
                Padding(
                  padding: const EdgeInsets.only(left: 8, bottom: 6),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Semantics(header: true, child: Text(context.l10n.goals, style: OmiType.title3)),
                      if (goals.length < maxGoalCount)
                        Transform.translate(
                          // Keeps the painted circle on the card's right edge.
                          offset: const Offset((kOmiMinTapTarget - 32) / 2, 0),
                          child: OmiIconButton.filled(
                            label: context.l10n.addGoal,
                            onPressed: () => addGoal(context, _emojis),
                            diameter: 32,
                            fillColor: OmiColors.surface2,
                            color: OmiColors.textSecondary,
                            icon: const Icon(Icons.add),
                          ),
                        ),
                    ],
                  ),
                ),
              // Goals list
              ...goals.asMap().entries.map((entry) {
                final goal = entry.value;
                final isLast = entry.key == goals.length - 1;
                return _buildGoalItem(goal, isLast);
              }),
            ],
          ),
        );
      },
    );
  }

  Widget _buildGoalItem(Goal goal, bool isLast) {
    final progress = goal.progressPercentage;
    final color = _getColor(progress);
    final emoji = _emojis.of(goal.id);

    return Dismissible(
      key: Key(goal.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20.0),
        decoration: BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.xlAll),
        child: Icon(Icons.delete_outline, color: OmiColors.textPrimary),
      ),
      onDismissed: (direction) {
        PlatformManager.instance.analytics.goalDeleted(goalId: goal.id, source: 'home', method: 'swipe');
        deleteGoalAndEmoji(context, goal, _emojis);
      },
      child: GestureDetector(
        onTap: () {
          editGoal(context, goal, _emojis);
          WidgetsBinding.instance.addPostFrameCallback((_) {
            PlatformManager.instance.analytics.goalItemTappedForEdit(goalId: goal.id, source: 'home');
          });
        },
        child: Container(
          margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          child: Row(
            children: [
              // Emoji icon
              Container(
                width: 40,
                height: 40,
                margin: const EdgeInsets.only(right: 12),
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                child: Center(
                  child: ExcludeSemantics(child: Text(emoji, style: OmiType.headline)),
                ),
              ),
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      goal.title,
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    // Progress bar with completion text
                    Row(
                      children: [
                        Expanded(
                          child: Transform.translate(
                            offset: const Offset(-12, 0),
                            child: SliderTheme(
                              data: SliderThemeData(
                                trackHeight: 6,
                                activeTrackColor: color,
                                inactiveTrackColor: OmiColors.surface3,
                                thumbColor: color,
                                thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 0),
                                overlayShape: const RoundSliderOverlayShape(overlayRadius: 12),
                                trackShape: const RoundedRectSliderTrackShape(),
                                tickMarkShape: SliderTickMarkShape.noTickMark,
                              ),
                              child: Slider(
                                value: goal.currentValue.clamp(0.0, goal.targetValue),
                                min: 0,
                                max: goal.targetValue,
                                divisions: goalSliderDivisions(goal.targetValue),
                                onChanged: (value) => updateGoalProgressUI(goal, value),
                                onChangeEnd: (value) {
                                  PlatformManager.instance.analytics.goalProgressChanged(
                                    goalId: goal.id,
                                    oldValue: goal.currentValue,
                                    newValue: value,
                                    targetValue: goal.targetValue,
                                  );
                                  saveGoalProgress(context.read<GoalsProvider>(), goal, value);
                                },
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          goalProgressLabel(goal),
                          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
