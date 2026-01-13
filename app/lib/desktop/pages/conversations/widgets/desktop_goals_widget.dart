import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Desktop multi-goal widget supporting up to 3 goals with minimalistic UI
class DesktopGoalsWidget extends StatefulWidget {
  const DesktopGoalsWidget({super.key});

  @override
  State<DesktopGoalsWidget> createState() => _DesktopGoalsWidgetState();
}

class _DesktopGoalsWidgetState extends State<DesktopGoalsWidget> with WidgetsBindingObserver {
  List<Goal> _goals = [];
  bool _isLoading = true;
  
  static const String _goalsStorageKey = 'goals_tracker_local_goals';
  static const String _goalsEmojiKey = 'goals_tracker_emojis';
  static const int _maxGoals = 3;
  
  // Available emojis for goals
  static const List<String> _availableEmojis = [
    '🎯', '💪', '📚', '💰', '🏃', '🧘', '💡', '🔥', '⭐', '🚀',
    '💎', '🏆', '📈', '❤️', '🎨', '🎵', '✈️', '🏠', '🌱', '⏰',
  ];
  
  Map<String, String> _goalEmojis = {};
  String _selectedEmoji = '🎯';

  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _currentController = TextEditingController();
  final TextEditingController _targetController = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadGoals();
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
      _loadGoals();
    }
  }

  Future<void> _loadGoals() async {
    try {
      // Load emojis from local storage
      final prefs = await SharedPreferences.getInstance();
      final emojisJson = prefs.getString(_goalsEmojiKey);
      
      if (emojisJson != null) {
        final Map<String, dynamic> decoded = json.decode(emojisJson);
        _goalEmojis = decoded.map((k, v) => MapEntry(k, v.toString()));
      }
      
      // Fetch goals from backend (source of truth for cross-device sync)
      final backendGoals = await getAllGoals();
      
      if (backendGoals.isNotEmpty && mounted) {
        setState(() {
          _goals = backendGoals;
          _isLoading = false;
        });
        // Save to local storage as cache
        await _saveGoalsLocally();
      } else {
        // Fallback: try to load from local storage if backend is empty/unavailable
        final goalsJson = prefs.getString(_goalsStorageKey);
        if (goalsJson != null) {
          try {
            final List<dynamic> decoded = json.decode(goalsJson);
            final localGoals = decoded.map((e) => Goal.fromJson(e)).toList();
            if (localGoals.isNotEmpty && mounted) {
              setState(() {
                _goals = localGoals;
                _isLoading = false;
              });
              return;
            }
          } catch (e) {
            debugPrint('[GOALS] Error parsing local goals: $e');
          }
        }
        if (mounted) {
          setState(() => _isLoading = false);
        }
      }
    } catch (e) {
      debugPrint('[GOALS] Error loading goals: $e');
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _saveGoalsLocally() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final goalsJson = json.encode(_goals.map((g) => g.toJson()).toList());
      await prefs.setString(_goalsStorageKey, goalsJson);
      final emojisJson = json.encode(_goalEmojis);
      await prefs.setString(_goalsEmojiKey, emojisJson);
    } catch (e) {
      debugPrint('[GOALS] Error saving goals: $e');
    }
  }
  
  String _getSmartEmoji(String title) {
    final lowerTitle = title.toLowerCase();
    
    final Map<List<String>, String> keywordMap = {
      ['revenue', 'money', 'income', 'profit', 'sales', '\$', 'dollar', 'earn']: '💰',
      ['users', 'customers', 'clients', 'subscribers', 'followers', 'growth', 'million', '1m', '10k', '100k', 'mrr', 'arr']: '🚀',
      ['startup', 'launch', 'business', 'company']: '🏆',
      ['invest', 'stock', 'crypto', 'trading']: '📈',
      ['workout', 'gym', 'exercise', 'lift', 'muscle', 'strength', 'pushup', 'pullup']: '💪',
      ['run', 'marathon', 'jog', 'cardio', 'steps', 'walk', 'mile', 'km']: '🏃',
      ['weight', 'lose', 'fat', 'diet', 'calories', 'kg', 'lbs', 'pounds']: '⚖️',
      ['meditat', 'mindful', 'yoga', 'breath', 'calm', 'peace', 'zen']: '🧘',
      ['sleep', 'rest', 'hours']: '😴',
      ['water', 'hydrat', 'drink']: '💧',
      ['health', 'wellness', 'healthy']: '❤️',
      ['read', 'book', 'pages', 'chapter']: '📚',
      ['learn', 'study', 'course', 'class', 'skill', 'certif']: '🎓',
      ['code', 'program', 'develop', 'app', 'software', 'tech']: '💻',
      ['language', 'spanish', 'french', 'chinese', 'english', 'german']: '🗣️',
      ['write', 'blog', 'article', 'post', 'content', 'words']: '✍️',
      ['video', 'youtube', 'tiktok', 'film']: '🎬',
      ['music', 'song', 'piano', 'guitar', 'sing']: '🎵',
      ['art', 'draw', 'paint', 'design', 'create']: '🎨',
      ['photo', 'picture', 'camera']: '📸',
      ['task', 'todo', 'complete', 'finish', 'done']: '✅',
      ['habit', 'daily', 'streak', 'consistent', 'routine']: '🔥',
      ['time', 'hour', 'minute', 'focus', 'pomodoro', 'productive']: '⏰',
      ['project', 'ship', 'deliver', 'deadline']: '🎯',
      ['travel', 'trip', 'visit', 'country', 'city', 'vacation']: '✈️',
      ['home', 'house', 'apartment', 'move', 'buy']: '🏠',
      ['save', 'saving', 'budget', 'emergency fund']: '🏦',
      ['friend', 'social', 'network', 'connect', 'meet']: '👥',
      ['family', 'kids', 'parent']: '👨‍👩‍👧',
      ['date', 'relationship', 'love']: '💕',
      ['goal', 'target', 'achieve', 'accomplish']: '🎯',
      ['win', 'first', 'best', 'top', 'champion']: '🏆',
      ['grow', 'improve', 'better', 'progress']: '🌱',
      ['star', 'success', 'excellent']: '⭐',
    };
    
    for (final entry in keywordMap.entries) {
      for (final keyword in entry.key) {
        if (lowerTitle.contains(keyword)) {
          return entry.value;
        }
      }
    }
    
    return '🎯';
  }
  
  String _getGoalEmoji(String goalId) {
    return _goalEmojis[goalId] ?? '🎯';
  }

  void _addGoal() {
    if (_goals.length >= _maxGoals) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Maximum $_maxGoals goals allowed'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    _titleController.clear();
    _currentController.text = '0';
    _targetController.text = '100';
    _selectedEmoji = '🎯';

    _showGoalDialog(null);
  }

  void _editGoal(Goal goal) {
    _titleController.text = goal.title;
    _currentController.text = _rawNum(goal.currentValue);
    _targetController.text = _rawNum(goal.targetValue);
    _selectedEmoji = _getGoalEmoji(goal.id);

    _showGoalDialog(goal);
  }

  void _showGoalDialog(Goal? existingGoal) {
    final isNew = existingGoal == null;
    
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          backgroundColor: ResponsiveHelper.backgroundSecondary,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            isNew ? 'Add Goal' : 'Edit Goal',
            style: const TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          content: SizedBox(
            width: 360,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Emoji selector (only for editing)
                if (!isNew) ...[
                  Text(
                    'Icon',
                    style: TextStyle(
                      color: ResponsiveHelper.textTertiary,
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
                        return MouseRegion(
                          cursor: SystemMouseCursors.click,
                          child: GestureDetector(
                            onTap: () {
                              setDialogState(() => _selectedEmoji = emoji);
                            },
                            child: Container(
                              width: 40,
                              height: 40,
                              margin: const EdgeInsets.only(right: 6),
                              decoration: BoxDecoration(
                                color: isSelected 
                                    ? ResponsiveHelper.purplePrimary.withOpacity(0.2)
                                    : ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                                borderRadius: BorderRadius.circular(10),
                                border: isSelected 
                                    ? Border.all(color: ResponsiveHelper.purplePrimary, width: 2)
                                    : null,
                              ),
                              child: Center(
                                child: Text(emoji, style: const TextStyle(fontSize: 20)),
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                // Title field
                Text(
                  'Goal title',
                  style: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _titleController,
                  style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                  decoration: InputDecoration(
                    filled: true,
                    fillColor: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                // Current & Target
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Current',
                            style: TextStyle(
                              color: ResponsiveHelper.textTertiary,
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _currentController,
                            keyboardType: TextInputType.number,
                            style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                            decoration: InputDecoration(
                              filled: true,
                              fillColor: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(10),
                                borderSide: BorderSide.none,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Target',
                            style: TextStyle(
                              color: ResponsiveHelper.textTertiary,
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _targetController,
                            keyboardType: TextInputType.number,
                            style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                            decoration: InputDecoration(
                              filled: true,
                              fillColor: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(10),
                                borderSide: BorderSide.none,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          actions: [
            if (!isNew)
              TextButton(
                onPressed: () async {
                  Navigator.pop(context);
                  await _deleteGoal(existingGoal);
                },
                style: TextButton.styleFrom(
                  foregroundColor: ResponsiveHelper.errorColor,
                ),
                child: const Text('Delete'),
              ),
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(
                'Cancel',
                style: TextStyle(color: ResponsiveHelper.textTertiary),
              ),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(context);
                await _saveGoal(existingGoal);
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: ResponsiveHelper.purplePrimary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
              child: Text(isNew ? 'Add Goal' : 'Save'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _saveGoal(Goal? existingGoal) async {
    final title = _titleController.text.trim();
    if (title.isEmpty) return;

    final current = double.tryParse(_currentController.text) ?? 0;
    final target = double.tryParse(_targetController.text) ?? 100;

    try {
      if (existingGoal != null) {
        final updated = Goal(
          id: existingGoal.id,
          title: title,
          goalType: existingGoal.goalType,
          currentValue: current,
          targetValue: target,
          minValue: existingGoal.minValue,
          maxValue: target,
          isActive: true,
          createdAt: existingGoal.createdAt,
          updatedAt: DateTime.now(),
        );

        final index = _goals.indexWhere((g) => g.id == existingGoal.id);
        if (index >= 0 && mounted) {
          setState(() {
            _goals[index] = updated;
            _goalEmojis[existingGoal.id] = _selectedEmoji;
          });
        }

        if (!existingGoal.id.startsWith('local_')) {
          await updateGoal(existingGoal.id, title: title, currentValue: current, targetValue: target);
        }
      } else {
        final newGoalId = 'local_${DateTime.now().millisecondsSinceEpoch}';
        final smartEmoji = _getSmartEmoji(title);
        final newGoal = Goal(
          id: newGoalId,
          title: title,
          goalType: 'numeric',
          currentValue: current,
          targetValue: target,
          minValue: 0,
          maxValue: target,
          isActive: true,
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        );

        if (mounted) {
          setState(() {
            _goals.add(newGoal);
            _goalEmojis[newGoalId] = smartEmoji;
          });
        }

        final created = await createGoal(
          title: title,
          goalType: 'numeric',
          targetValue: target,
          currentValue: current,
        );
        
        if (created != null && mounted) {
          final index = _goals.indexWhere((g) => g.id == newGoal.id);
          if (index >= 0) {
            setState(() {
              _goals[index] = created;
              _goalEmojis[created.id] = smartEmoji;
              _goalEmojis.remove(newGoalId);
            });
          }
        }
      }

      await _saveGoalsLocally();
    } catch (e) {
      debugPrint('[GOALS] Error saving goal: $e');
    }
  }

  Future<void> _deleteGoal(Goal goal) async {
    setState(() {
      _goals.removeWhere((g) => g.id == goal.id);
      _goalEmojis.remove(goal.id);
    });
    await _saveGoalsLocally();

    if (!goal.id.startsWith('local_')) {
      await deleteGoal(goal.id);
    }
  }

  String _rawNum(double v) {
    return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
  }

  Color _getColor(double progress) {
    if (progress >= 0.8) return const Color(0xFF22C55E);
    if (progress >= 0.6) return const Color(0xFF84CC16);
    if (progress >= 0.4) return const Color(0xFFFBBF24);
    if (progress >= 0.2) return const Color(0xFFF97316);
    return ResponsiveHelper.textTertiary;
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Goals',
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (_goals.length < _maxGoals)
                MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: GestureDetector(
                    onTap: _addGoal,
                    child: Icon(
                      Icons.add_rounded,
                      size: 20,
                      color: ResponsiveHelper.textTertiary,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          // Goals list - use Expanded to fill available space
          Expanded(
            child: _goals.isEmpty
                ? MouseRegion(
                    cursor: SystemMouseCursors.click,
                    child: GestureDetector(
                      onTap: _addGoal,
                      child: Center(
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.add_rounded, size: 16, color: ResponsiveHelper.textTertiary),
                            const SizedBox(width: 8),
                            Text(
                              'Tap to add a goal',
                              style: TextStyle(
                                fontSize: 13,
                                color: ResponsiveHelper.textTertiary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  )
                : ListView(
                    padding: EdgeInsets.zero,
                    children: _goals.asMap().entries.map((entry) {
                      final goal = entry.value;
                      final isLast = entry.key == _goals.length - 1;
                      return _buildGoalItem(goal, isLast);
                    }).toList(),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildGoalItem(Goal goal, bool isLast) {
    final progress = goal.progressPercentage;
    final color = _getColor(progress);
    final emoji = _getGoalEmoji(goal.id);

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => _editGoal(goal),
        child: Container(
          margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            children: [
              // Emoji icon
              Container(
                width: 32,
                height: 32,
                margin: const EdgeInsets.only(right: 12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Center(
                  child: Text(emoji, style: const TextStyle(fontSize: 16)),
                ),
              ),
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            goal.title,
                            style: const TextStyle(
                              color: ResponsiveHelper.textPrimary,
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          '${_rawNum(goal.currentValue)}/${_rawNum(goal.targetValue)}',
                          style: TextStyle(
                            color: ResponsiveHelper.textTertiary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    // Progress bar
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final progressWidth = constraints.maxWidth * progress.clamp(0.0, 1.0);
                        return Stack(
                          children: [
                            Container(
                              height: 4,
                              width: double.infinity,
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                            Container(
                              height: 4,
                              width: progressWidth,
                              decoration: BoxDecoration(
                                color: color,
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                          ],
                        );
                      },
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
