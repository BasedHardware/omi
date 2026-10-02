import 'dart:convert';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:intl/intl.dart';

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
/// hidden, which can block the UI thread for several seconds.
@visibleForTesting
int? goalSliderDivisions(double targetValue) {
  if (!targetValue.isFinite || targetValue <= 0 || targetValue > 100) return null;
  final roundedTarget = targetValue.round();
  return targetValue == roundedTarget ? roundedTarget : null;
}

/// Multi-goal widget supporting up to 3 goals with minimalistic UI
class GoalsWidget extends StatefulWidget {
  const GoalsWidget({super.key, this.onRefresh});

  /// How many goals a person can keep at once.
  static const int maxGoals = 4;

  final VoidCallback? onRefresh;

  @override
  State<GoalsWidget> createState() => GoalsWidgetState();
}

class GoalsWidgetState extends State<GoalsWidget> with WidgetsBindingObserver {
  static const String _goalsEmojiKey = 'goals_tracker_emojis';

  // Available emojis for goals
  static const List<String> _availableEmojis = [
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

  // Local emoji storage (goalId -> emoji)
  Map<String, String> _goalEmojis = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadEmojis();
  }

  void refresh() {
    Provider.of<GoalsProvider>(context, listen: false).refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      Provider.of<GoalsProvider>(context, listen: false).refresh();
    }
  }

  Future<void> _loadEmojis() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final emojisJson = prefs.getString(_goalsEmojiKey);

      if (emojisJson != null && mounted) {
        final Map<String, dynamic> decoded = json.decode(emojisJson);
        setState(() {
          _goalEmojis = decoded.map((k, v) => MapEntry(k, v.toString()));
        });
      }
    } catch (_) {}
  }

  Future<void> _saveEmojis() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final emojisJson = json.encode(_goalEmojis);
      await prefs.setString(_goalsEmojiKey, emojisJson);
      widget.onRefresh?.call();
    } catch (_) {}
  }

  String _getSmartEmoji(String title) {
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

  String _getGoalEmoji(String goalId) {
    return _goalEmojis[goalId] ?? '🎯';
  }

  void addGoal() {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    if (goalsProvider.goals.length >= GoalsWidget.maxGoals) {
      OmiFeedback.info(context, context.l10n.maximumGoalsAllowed(GoalsWidget.maxGoals));
      return;
    }

    PlatformManager.instance.analytics.goalAddButtonTapped(source: 'home');
    OmiHaptics.light();
    showGoalFormSheet(context, onSave: (title, current, target, _) => _saveGoal(null, title, current, target, null));
  }

  void _editGoal(Goal goal) {
    OmiHaptics.light();
    showGoalFormSheet(
      context,
      goal: goal,
      emojiChoices: _availableEmojis,
      initialEmoji: _getGoalEmoji(goal.id),
      onSave: (title, current, target, emoji) => _saveGoal(goal, title, current, target, emoji),
      onDelete: () {
        PlatformManager.instance.analytics.goalDeleted(goalId: goal.id, source: 'home', method: 'button');
        _deleteGoal(goal);
      },
    );
  }

  Future<void> _saveGoal(Goal? existingGoal, String title, double current, double target, String? emoji) async {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);

    if (existingGoal != null) {
      await goalsProvider.updateGoal(existingGoal.id, title: title, currentValue: current, targetValue: target);

      PlatformManager.instance.analytics.goalUpdated(goalId: existingGoal.id, source: 'home');
      if (emoji != null) {
        PlatformManager.instance.analytics.goalEmojiSelected(emoji: emoji);
        if (mounted) setState(() => _goalEmojis[existingGoal.id] = emoji);
      }
    } else {
      final smartEmoji = _getSmartEmoji(title);
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
        if (mounted) setState(() => _goalEmojis[created.id] = smartEmoji);
      }
    }

    await _saveEmojis();
  }

  /// Immediate with Undo (D5); the emoji is forgotten once the delete commits.
  void _deleteGoal(Goal goal) {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    deleteGoalWithUndo(
      context,
      goalsProvider,
      goal,
      onDeleted: () {
        _goalEmojis.remove(goal.id);
        if (mounted) setState(() {});
        _saveEmojis();
      },
    );
  }

  /// "4/12 books", "2,450.5/6,000 USD": grouped, at most one decimal, with the goal's unit.
  String _progressLabel(Goal goal) {
    final number = NumberFormat.decimalPattern(context.l10n.localeName)..maximumFractionDigits = 1;
    final unit = goal.unit?.trim();
    final values = '${number.format(goal.currentValue)}/${number.format(goal.targetValue)}';
    return unit == null || unit.isEmpty ? values : '$values $unit';
  }

  /// Progress is ink however far along (black and white, like Settings); the bar's length and the
  /// "6/12" beside it carry the state.
  Color _getColor(double progress) => OmiColors.textPrimary;

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

        // The page's bar carries the title and the add button.
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          padding: const EdgeInsets.only(top: OmiSpacing.sm, bottom: OmiSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
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
    final emoji = _getGoalEmoji(goal.id);

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
        _deleteGoal(goal);
      },
      child: GestureDetector(
        onTap: () {
          _editGoal(goal);
          WidgetsBinding.instance.addPostFrameCallback((_) {
            PlatformManager.instance.analytics.goalItemTappedForEdit(goalId: goal.id, source: 'home');
          });
        },
        child: Container(
          margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
          decoration: BoxDecoration(
            color: OmiColors.groupedCard,
            borderRadius: OmiRadius.xlAll,
            border: Border.all(color: OmiColors.groupedBorder),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          child: Row(
            children: [
              // Emoji icon
              Container(
                width: 40,
                height: 40,
                margin: const EdgeInsets.only(right: 12),
                decoration: BoxDecoration(
                  color: OmiColors.iconTile,
                  borderRadius: OmiRadius.mdAll,
                  border: Border.all(color: OmiColors.groupedBorder),
                ),
                child: Center(child: ExcludeSemantics(child: Text(emoji, style: OmiType.headline))),
              ),
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      goal.title,
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                      maxLines: 2,
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
                                onChanged: (value) => _updateGoalProgressUI(goal, value),
                                onChangeEnd: (value) {
                                  PlatformManager.instance.analytics.goalProgressChanged(
                                    goalId: goal.id,
                                    oldValue: goal.currentValue,
                                    newValue: value,
                                    targetValue: goal.targetValue,
                                  );
                                  _saveGoalProgress(goal, value);
                                },
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _progressLabel(goal),
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

  // Update UI state only (called during drag) - use provider for immediate feedback
  void _updateGoalProgressUI(Goal goal, double newValue) {
    if (newValue == goal.currentValue) return;
    OmiHaptics.light();
    // The provider will notify listeners and the UI will update
  }

  // Save to storage and API (called when drag ends)
  Future<void> _saveGoalProgress(Goal goal, double newValue) async {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    await goalsProvider.updateGoalProgress(goal.id, newValue);
  }
}
