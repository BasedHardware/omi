import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Multi-goal widget supporting up to 3 goals with minimalistic UI
class GoalsWidget extends StatefulWidget {
  const GoalsWidget({super.key, this.onRefresh});

  final VoidCallback? onRefresh;

  @override
  State<GoalsWidget> createState() => GoalsWidgetState();
}

class GoalsWidgetState extends State<GoalsWidget> with WidgetsBindingObserver {
  List<Goal> _goals = [];
  bool _isLoading = true;
  bool _isExpanded = false;
  
  static const String _goalsStorageKey = 'goals_tracker_local_goals';
  static const String _goalsEmojiKey = 'goals_tracker_emojis';
  static const int _maxGoals = 3;
  
  // Available emojis for goals
  static const List<String> _availableEmojis = [
    '🎯', '💪', '📚', '💰', '🏃', '🧘', '💡', '🔥', '⭐', '🚀',
    '💎', '🏆', '📈', '❤️', '🎨', '🎵', '✈️', '🏠', '🌱', '⏰',
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
    _loadGoals();
  }
  
  void refresh() {
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
      // Also save emojis
      final emojisJson = json.encode(_goalEmojis);
      await prefs.setString(_goalsEmojiKey, emojisJson);
    } catch (e) {
      debugPrint('[GOALS] Error saving goals: $e');
    }
  }
  
  String _getSmartEmoji(String title) {
    final lowerTitle = title.toLowerCase();
    
    // Keyword to emoji mapping - order matters (more specific first)
    final Map<List<String>, String> keywordMap = {
      // Money/Business goals
      ['revenue', 'money', 'income', 'profit', 'sales', '\$', 'dollar', 'earn']: '💰',
      ['users', 'customers', 'clients', 'subscribers', 'followers', 'growth', 'million', '1m', '10k', '100k', 'mrr', 'arr']: '🚀',
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
                  isNew ? 'Add Goal' : 'Edit Goal',
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
                        'Icon',
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
                                setSheetState(() => _selectedEmoji = emoji);
                              },
                              child: Container(
                                width: 44,
                                height: 44,
                                margin: const EdgeInsets.only(right: 8),
                                decoration: BoxDecoration(
                                  color: isSelected 
                                      ? Colors.white.withOpacity(0.15) 
                                      : Colors.white.withOpacity(0.05),
                                  borderRadius: BorderRadius.circular(12),
                                  border: isSelected 
                                      ? Border.all(color: Colors.white.withOpacity(0.3), width: 2)
                                      : null,
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
                      'Goal title',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _titleController,
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
                          'Current',
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
                          'Target',
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
                          Navigator.pop(context);
                          await _deleteGoal(existingGoal);
                        },
                        style: TextButton.styleFrom(
                          foregroundColor: Colors.red,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        ),
                        child: const Text('Delete'),
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
                      child: Text(isNew ? 'Add Goal' : 'Save'),
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

    if (existingGoal != null) {
      // Update existing goal
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
      if (index >= 0) {
        setState(() {
          _goals[index] = updated;
          _goalEmojis[existingGoal.id] = _selectedEmoji; // Save emoji
        });
      }

      // Try to sync to backend
      if (!existingGoal.id.startsWith('local_')) {
        await updateGoal(existingGoal.id, title: title, currentValue: current, targetValue: target);
      }
    } else {
      // Create new goal
      final newGoalId = 'local_${DateTime.now().millisecondsSinceEpoch}';
      final smartEmoji = _getSmartEmoji(title); // Auto-select emoji based on title
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

      setState(() {
        _goals.add(newGoal);
        _goalEmojis[newGoalId] = smartEmoji; // Save smart emoji for new goal
      });

      // Try to create on backend
      final created = await createGoal(
        title: title,
        goalType: 'numeric',
        targetValue: target,
        currentValue: current,
      );
      
      if (created != null) {
        final index = _goals.indexWhere((g) => g.id == newGoal.id);
        if (index >= 0 && mounted) {
          setState(() {
            _goals[index] = created;
            // Move emoji to the new backend id
            _goalEmojis[created.id] = smartEmoji;
            _goalEmojis.remove(newGoalId);
          });
        }
      }
    }

    await _saveGoalsLocally();
  }

  Future<void> _deleteGoal(Goal goal) async {
    HapticFeedback.mediumImpact();
    setState(() {
      _goals.removeWhere((g) => g.id == goal.id);
      _goalEmojis.remove(goal.id); // Remove emoji mapping
    });
    await _saveGoalsLocally();

    if (!goal.id.startsWith('local_')) {
      await deleteGoal(goal.id);
    }
  }

  String _rawNum(double v) {
    return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
  }

  String _formatNum(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)}M';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(1)}K';
    return _rawNum(v);
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
    if (_isLoading) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.only(top: 16, bottom: 20),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withOpacity(0.08),
            width: 1,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Goals',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (_goals.length < _maxGoals)
                  GestureDetector(
                    onTap: _addGoal,
                    child: Icon(
                      Icons.add_rounded,
                      size: 22,
                      color: Colors.white.withOpacity(0.5),
                    ),
                  ),
              ],
            ),
          ),
          // Goals list
          if (_goals.isEmpty)
            GestureDetector(
              onTap: _addGoal,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Center(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.add_rounded, size: 18, color: Colors.white.withOpacity(0.4)),
                      const SizedBox(width: 8),
                      Text(
                        'Tap to add a goal',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.white.withOpacity(0.4),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            )
          else
            ..._goals.asMap().entries.map((entry) {
              final goal = entry.value;
              final isLast = entry.key == _goals.length - 1;
              return _buildGoalItem(goal, isLast);
            }),
        ],
      ),
    );
  }

  Widget _buildGoalItem(Goal goal, bool isLast) {
    final progress = goal.progressPercentage;
    final color = _getColor(progress);
    final emoji = _getGoalEmoji(goal.id);

    return GestureDetector(
      onTap: () => _editGoal(goal),
      child: Container(
        margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
        child: Row(
          children: [
            // Emoji icon
            Container(
              width: 36,
              height: 36,
              margin: const EdgeInsets.only(right: 12),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.1),
                borderRadius: BorderRadius.circular(10),
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
                  const SizedBox(height: 6),
                  // Progress bar
                  Stack(
                    children: [
                      Container(
                        height: 6,
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                      FractionallySizedBox(
                        widthFactor: progress.clamp(0.0, 1.0),
                        child: Container(
                          height: 6,
                          decoration: BoxDecoration(
                            color: color,
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Expand icon
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: Icon(
                _isExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                size: 20,
                color: Colors.white.withOpacity(0.3),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
