import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Multi-goal widget supporting up to 3 goals with minimalistic UI
class GoalsWidget extends StatefulWidget {
  const GoalsWidget({super.key, this.onRefresh});

  final VoidCallback? onRefresh;

  @override
  State<GoalsWidget> createState() => GoalsWidgetState();
}

class GoalsWidgetState extends State<GoalsWidget> with WidgetsBindingObserver {
  static const String _goalsEmojiKey = 'goals_tracker_emojis';
  static const int _maxGoals = 3;

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
  String _selectedEmoji = '🎯';

  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _currentController = TextEditingController();
  final TextEditingController _targetController = TextEditingController();

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
    _titleController.dispose();
    _currentController.dispose();
    _targetController.dispose();
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
        'arr'
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
    if (goalsProvider.goals.length >= _maxGoals) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.maximumGoalsAllowed(_maxGoals)),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    MixpanelManager().goalAddButtonTapped(source: 'home');
    HapticFeedback.lightImpact();
    _titleController.clear();
    _currentController.text = '0';
    _targetController.text = '100';
    _selectedEmoji = '🎯'; // Default emoji, will be updated based on title when saved

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => _buildGoalEditSheet(null),
    );
  }

  void _editGoal(Goal goal) {
    HapticFeedback.lightImpact();
    _titleController.text = goal.title;
    _currentController.text = _rawNum(goal.currentValue);
    _targetController.text = _rawNum(goal.targetValue);
    _selectedEmoji = _getGoalEmoji(goal.id); // Load existing emoji

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => _buildGoalEditSheet(goal),
    );
  }

  Widget _buildGoalEditSheet(Goal? existingGoal) {
    final isNew = existingGoal == null;

    return StatefulBuilder(
      builder: (context, setSheetState) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: Container(
          decoration: const BoxDecoration(
            color: Color(0xFF1A1A1A),
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          padding: const EdgeInsets.all(24),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 20),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade700,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Text(
                  isNew ? context.l10n.addGoal : context.l10n.editGoal,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 24),
                // Emoji selector - only show when editing (not when creating new)
                if (!isNew) ...[
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        context.l10n.icon,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 8),
                      SizedBox(
                        height: 44,
                        child: ListView.builder(
                          scrollDirection: Axis.horizontal,
                          itemCount: _availableEmojis.length,
                          itemBuilder: (context, index) {
                            final emoji = _availableEmojis[index];
                            final isSelected = emoji == _selectedEmoji;
                            return GestureDetector(
                              onTap: () {
                                HapticFeedback.selectionClick();
                                MixpanelManager().goalEmojiSelected(emoji: emoji);
                                setSheetState(() => _selectedEmoji = emoji);
                              },
                              child: Container(
                                width: 44,
                                height: 44,
                                margin: const EdgeInsets.only(right: 8),
                                decoration: BoxDecoration(
                                  color: isSelected ? Colors.white.withOpacity(0.15) : Colors.white.withOpacity(0.05),
                                  borderRadius: BorderRadius.circular(12),
                                  border:
                                      isSelected ? Border.all(color: Colors.white.withOpacity(0.3), width: 2) : null,
                                ),
                                child: Center(
                                  child: Text(emoji, style: const TextStyle(fontSize: 22)),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                ],
                // Title field with label above
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.l10n.goalTitle,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _titleController,
                      autofocus: true,
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: Colors.white.withOpacity(0.08),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                // Current & Target fields with labels above
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.l10n.current,
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.5),
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _currentController,
                            keyboardType: TextInputType.number,
                            style: const TextStyle(color: Colors.white, fontSize: 16),
                            decoration: InputDecoration(
                              filled: true,
                              fillColor: Colors.white.withOpacity(0.08),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(12),
                                borderSide: BorderSide.none,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.l10n.target,
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.5),
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _targetController,
                            keyboardType: TextInputType.number,
                            style: const TextStyle(color: Colors.white, fontSize: 16),
                            decoration: InputDecoration(
                              filled: true,
                              fillColor: Colors.white.withOpacity(0.08),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(12),
                                borderSide: BorderSide.none,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                // Action buttons
                Row(
                  children: [
                    if (!isNew) ...[
                      Expanded(
                        child: TextButton(
                          onPressed: () async {
                            MixpanelManager().goalDeleted(goalId: existingGoal.id, source: 'home', method: 'button');
                            Navigator.pop(context);
                            await _deleteGoal(existingGoal);
                          },
                          style: TextButton.styleFrom(
                            foregroundColor: Colors.red,
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                          child: Text(context.l10n.delete),
                        ),
                      ),
                      const SizedBox(width: 12),
                    ],
                    Expanded(
                      flex: isNew ? 1 : 2,
                      child: ElevatedButton(
                        onPressed: () async {
                          Navigator.pop(context);
                          await _saveGoal(existingGoal);
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF22C55E),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: Text(isNew ? context.l10n.addGoal : context.l10n.save),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _saveGoal(Goal? existingGoal) async {
    final title = _titleController.text.trim();
    if (title.isEmpty) return;

    final current = double.tryParse(_currentController.text) ?? 0;
    final target = double.tryParse(_targetController.text) ?? 100;
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);

    if (existingGoal != null) {
      // Update existing goal via provider
      await goalsProvider.updateGoal(
        existingGoal.id,
        title: title,
        currentValue: current,
        targetValue: target,
      );

      MixpanelManager().goalUpdated(goalId: existingGoal.id, source: 'home');
      // Save emoji
      setState(() {
        _goalEmojis[existingGoal.id] = _selectedEmoji;
      });
    } else {
      // Create new goal via provider
      final smartEmoji = _getSmartEmoji(title);
      final created = await goalsProvider.createGoal(
        title: title,
        goalType: 'numeric',
        targetValue: target,
        currentValue: current,
      );

      if (created != null) {
        MixpanelManager()
            .goalCreated(goalId: created.id, titleLength: title.length, targetValue: target, source: 'home');
        setState(() {
          _goalEmojis[created.id] = smartEmoji;
        });
      }
    }

    await _saveEmojis();
  }

  Future<void> _deleteGoal(Goal goal) async {
    HapticFeedback.mediumImpact();
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    await goalsProvider.deleteGoal(goal.id);

    setState(() {
      _goalEmojis.remove(goal.id);
    });
    await _saveEmojis();
  }

  String _rawNum(double v) {
    return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
  }

  Color _getColor(double progress) {
    if (progress >= 0.8) return const Color(0xFF22C55E);
    if (progress >= 0.6) return const Color(0xFF84CC16);
    if (progress >= 0.4) return const Color(0xFFFBBF24);
    if (progress >= 0.2) return const Color(0xFFF97316);
    return const Color(0xFF6B7280);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<GoalsProvider>(
      builder: (context, goalsProvider, child) {
        if (goalsProvider.isLoading) {
          return const SizedBox.shrink();
        }

        final goals = goalsProvider.goals;

        // If no goals, hide the widget (Add Goals button is now in Daily Score widget)
        if (goals.isEmpty) {
          return const SizedBox.shrink();
        }

        return Container(
          margin: const EdgeInsets.only(left: 16, right: 16),
          padding: const EdgeInsets.only(top: 16, bottom: 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.only(left: 8, bottom: 12),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      context.l10n.goals,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (goals.length < _maxGoals)
                      GestureDetector(
                        onTap: addGoal,
                        child: Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: Colors.grey.withValues(alpha: 0.12),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            Icons.add,
                            size: 18,
                            color: Colors.grey[400],
                          ),
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
    final emoji = _getGoalEmoji(goal.id);

    return Dismissible(
      key: Key(goal.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20.0),
        color: Colors.red,
        child: const Icon(Icons.delete, color: Colors.white),
      ),
      onDismissed: (direction) async {
        MixpanelManager().goalDeleted(goalId: goal.id, source: 'home', method: 'swipe');
        await _deleteGoal(goal);
      },
      child: GestureDetector(
        onTap: () {
          MixpanelManager().goalItemTappedForEdit(goalId: goal.id, source: 'home');
          _editGoal(goal);
        },
        child: Container(
          margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(24),
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
                  color: Colors.white.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Center(
                  child: Text(emoji, style: const TextStyle(fontSize: 18)),
                ),
              ),
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      goal.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
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
                                inactiveTrackColor: Colors.white.withOpacity(0.1),
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
                                divisions: goal.targetValue >= 1 ? goal.targetValue.toInt() : null,
                                onChanged: (value) => _updateGoalProgressUI(goal, value),
                                onChangeEnd: (value) {
                                  MixpanelManager().goalProgressChanged(
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
                          '${_rawNum(goal.currentValue)}/${_rawNum(goal.targetValue)}',
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.white.withOpacity(0.5),
                            fontWeight: FontWeight.w500,
                          ),
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
    HapticFeedback.lightImpact();
    // The provider will notify listeners and the UI will update
  }

  // Save to storage and API (called when drag ends)
  Future<void> _saveGoalProgress(Goal goal, double newValue) async {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    await goalsProvider.updateGoalProgress(goal.id, newValue);
  }
}
