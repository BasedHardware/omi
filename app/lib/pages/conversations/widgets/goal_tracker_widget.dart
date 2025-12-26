import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/goals.dart';

/// Goal tracker widget with semicircle gauge
class GoalTrackerWidget extends StatefulWidget {
  const GoalTrackerWidget({super.key});

  @override
  State<GoalTrackerWidget> createState() => _GoalTrackerWidgetState();
}

class _GoalTrackerWidgetState extends State<GoalTrackerWidget>
    with WidgetsBindingObserver {
  Goal? _goal;
  GoalSuggestion? _suggestion;
  String? _advice;
  bool _isLoading = true;
  bool _isEditingGoal = false;
  bool _isEditingValue = false;

  final TextEditingController _goalTitleController = TextEditingController();
  final TextEditingController _currentValueController = TextEditingController();
  final TextEditingController _targetValueController = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadGoal();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _goalTitleController.dispose();
    _currentValueController.dispose();
    _targetValueController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _loadGoal();
    }
  }

  Future<void> _loadGoal() async {
    setState(() => _isLoading = true);

    try {
      // Try to get existing goal
      final goal = await getCurrentGoal();

      if (goal != null && mounted) {
        setState(() {
          _goal = goal;
          _goalTitleController.text = goal.title;
          _currentValueController.text = _rawNum(goal.currentValue);
          _targetValueController.text = _rawNum(goal.targetValue);
        });
        _loadAdvice();
      } else {
        // No goal - try to get suggestion for when user wants to create
        final suggestion = await suggestGoal();
        if (mounted) {
          setState(() => _suggestion = suggestion);
        }
      }
    } catch (e) {
      debugPrint('Error loading goal: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _loadAdvice() async {
    if (_goal == null) return;
    try {
      final advice = await getGoalAdvice();
      if (mounted && advice != null) setState(() => _advice = advice);
    } catch (e) {
      debugPrint('Error loading advice: $e');
    }
  }

  Future<void> _createGoalFromSuggestion() async {
    if (_suggestion == null) {
      _createDefaultGoal();
      return;
    }
    
    HapticFeedback.lightImpact();
    setState(() => _isLoading = true);
    
    try {
      final goal = await createGoal(
        title: _suggestion!.suggestedTitle,
        goalType: _suggestion!.suggestedType,
        targetValue: _suggestion!.suggestedTarget,
        minValue: _suggestion!.suggestedMin,
        maxValue: _suggestion!.suggestedMax,
      );
      
      if (goal != null && mounted) {
        setState(() {
          _goal = goal;
          _goalTitleController.text = goal.title;
          _currentValueController.text = _rawNum(goal.currentValue);
          _targetValueController.text = _rawNum(goal.targetValue);
          _isLoading = false;
        });
        _loadAdvice();
      } else {
        _createDefaultGoal();
      }
    } catch (e) {
      debugPrint('Error creating goal: $e');
      _createDefaultGoal();
    }
  }

  Future<void> _saveTitle() async {
    if (_goal == null || _goalTitleController.text.trim().isEmpty) {
      if (mounted) setState(() => _isEditingGoal = false);
      return;
    }
    HapticFeedback.lightImpact();
    final newTitle = _goalTitleController.text.trim();
    
    if (!mounted) return;
    
    try {
      Goal? updatedGoal;
      if (_goal!.id.startsWith('temp_')) {
        debugPrint('Creating new goal: $newTitle');
        updatedGoal = await createGoal(
          title: newTitle,
          goalType: _goal!.goalType,
          targetValue: _goal!.targetValue,
          currentValue: _goal!.currentValue,
          minValue: _goal!.minValue,
          maxValue: _goal!.maxValue,
        );
        if (updatedGoal == null) {
          debugPrint('createGoal returned null');
        }
      } else {
        debugPrint('Updating goal ${_goal!.id} with title: $newTitle');
        updatedGoal = await updateGoal(_goal!.id, title: newTitle);
        if (updatedGoal == null) {
          debugPrint('updateGoal returned null');
        }
      }
      
      if (mounted) {
        if (updatedGoal != null) {
          setState(() { 
            _goal = updatedGoal;
            _isEditingGoal = false;
          });
          _loadAdvice();
        } else {
          // Save failed - close editor anyway but don't update goal
          setState(() => _isEditingGoal = false);
        }
      }
    } catch (e) {
      debugPrint('Error saving title: $e');
      if (mounted) {
        setState(() => _isEditingGoal = false);
      }
    }
  }

  Future<void> _saveValues() async {
    if (_goal == null) { setState(() => _isEditingValue = false); return; }
    HapticFeedback.lightImpact();
    
    final currentVal = _parseNum(_currentValueController.text) ?? _goal!.currentValue;
    final targetVal = _parseNum(_targetValueController.text) ?? _goal!.targetValue;

    try {
      if (_goal!.id.startsWith('temp_')) {
        setState(() {
          _goal = Goal(
            id: _goal!.id, title: _goal!.title, goalType: _goal!.goalType,
            currentValue: currentVal, targetValue: targetVal,
            minValue: _goal!.minValue, maxValue: targetVal,
            isActive: true, createdAt: _goal!.createdAt, updatedAt: DateTime.now(),
          );
          _isEditingValue = false;
        });
      } else {
        final updated = await updateGoal(_goal!.id, currentValue: currentVal, targetValue: targetVal, maxValue: targetVal);
        if (updated != null && mounted) {
          setState(() { _goal = updated; _isEditingValue = false; });
          _loadAdvice();
        }
      }
    } catch (e) {
      debugPrint('Error: $e');
    }
    setState(() => _isEditingValue = false);
  }

  void _createDefaultGoal() {
    HapticFeedback.lightImpact();
    setState(() {
      _goal = Goal(
        id: 'temp_${DateTime.now().millisecondsSinceEpoch}',
        title: 'My goal', goalType: 'numeric',
        currentValue: 0, targetValue: 100, minValue: 0, maxValue: 100,
        isActive: true, createdAt: DateTime.now(), updatedAt: DateTime.now(),
      );
      _goalTitleController.text = 'My goal';
      _currentValueController.text = '0';
      _targetValueController.text = '100';
      _isEditingGoal = true;
      _isLoading = false;
    });
  }

  String _formatNum(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)}M';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(1)}K';
    return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
  }

  // Raw number for text fields (no K/M suffix)
  String _rawNum(double v) {
    return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
  }

  // Parse number that might have K/M suffix
  double? _parseNum(String s) {
    s = s.trim().toUpperCase();
    if (s.endsWith('M')) {
      final num = double.tryParse(s.substring(0, s.length - 1));
      return num != null ? num * 1000000 : null;
    }
    if (s.endsWith('K')) {
      final num = double.tryParse(s.substring(0, s.length - 1));
      return num != null ? num * 1000 : null;
    }
    return double.tryParse(s);
  }

  Color _getColor(double p) {
    if (p >= 0.8) return const Color(0xFF22C55E);
    if (p >= 0.6) return const Color(0xFF84CC16);
    if (p >= 0.4) return const Color(0xFFFBBF24);
    if (p >= 0.2) return const Color(0xFFF97316);
    return const Color(0xFFEF4444);
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) return _buildLoading();
    if (_goal == null) return _buildEmpty();
    return _buildContent();
  }

  Widget _buildLoading() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: const Center(
        child: SizedBox(width: 20, height: 20,
          child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation<Color>(Colors.white24)),
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    final hasSuggestion = _suggestion != null;
    
    return GestureDetector(
      onTap: hasSuggestion ? _createGoalFromSuggestion : _createDefaultGoal,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(16)),
        child: Column(
          children: [
            Text(
              'GOAL',
              style: TextStyle(
                fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 1.5,
                color: Colors.white.withOpacity(0.3),
              ),
            ),
            const SizedBox(height: 12),
            if (hasSuggestion) ...[
              Text(
                _suggestion!.suggestedTitle,
                style: TextStyle(fontSize: 14, color: Colors.white.withOpacity(0.7)),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Tap to track this goal',
                style: TextStyle(fontSize: 12, color: Colors.white.withOpacity(0.35)),
              ),
            ] else ...[
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.add_rounded, size: 18, color: Colors.white.withOpacity(0.4)),
                  const SizedBox(width: 8),
                  Text('Tap to set a goal', style: TextStyle(fontSize: 14, color: Colors.white.withOpacity(0.5))),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    final progress = _goal!.progressPercentage;
    final color = _getColor(progress);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Column(
        children: [
          // Main card with gauge
          GestureDetector(
            onTap: () { HapticFeedback.lightImpact(); setState(() => _isEditingValue = true); },
            child: Container(
              padding: const EdgeInsets.fromLTRB(24, 16, 24, 20),
              decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(16)),
              child: Column(
                children: [
                  // "Goal" label
                  Text(
                    'GOAL',
                    style: TextStyle(
                      fontSize: 10, fontWeight: FontWeight.w500, letterSpacing: 1.5,
                      color: Colors.white.withOpacity(0.3),
                    ),
                  ),
                  const SizedBox(height: 8),
                  // Title
                  GestureDetector(
                    onTap: () { HapticFeedback.lightImpact(); setState(() => _isEditingGoal = true); },
                    child: _isEditingGoal ? _buildTitleEdit() : Text(
                      _goal!.title,
                      style: TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w400,
                        color: Colors.white.withOpacity(0.7),
                      ),
                      textAlign: TextAlign.center,
                      maxLines: 2,
                    ),
                  ),
                  
                  const SizedBox(height: 16),
                  
                  // Gauge
                  _isEditingValue ? _buildValueEdit(color) : SizedBox(
                    height: 160,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        CustomPaint(
                          size: const Size(260, 160),
                          painter: _GaugePainter(progress: progress, color: color),
                        ),
                        // Main number
                        Positioned(
                          bottom: 10,
                          child: Text(
                            _formatNum(_goal!.currentValue),
                            style: const TextStyle(
                              fontSize: 64, fontWeight: FontWeight.w300,
                              color: Colors.white, height: 1,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Advice section
          if (_advice != null && _advice!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(16)),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('💡', style: TextStyle(fontSize: 16)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _advice!,
                      style: TextStyle(fontSize: 14, color: Colors.white.withOpacity(0.7), height: 1.4),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTitleEdit() {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _goalTitleController,
            autofocus: true,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 14, color: Colors.white.withOpacity(0.9)),
            decoration: InputDecoration(
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              filled: true, fillColor: Colors.white.withOpacity(0.1),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
            ),
            onSubmitted: (_) => _saveTitle(),
          ),
        ),
        const SizedBox(width: 8),
        GestureDetector(
          onTap: _saveTitle,
          child: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(color: const Color(0xFF22C55E), borderRadius: BorderRadius.circular(8)),
            child: const Icon(Icons.check, size: 18, color: Colors.white),
          ),
        ),
      ],
    );
  }

  Widget _buildValueEdit(Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _numField(_currentValueController, 'CURRENT', color),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Text('/', style: TextStyle(fontSize: 36, fontWeight: FontWeight.w200, color: Colors.white.withOpacity(0.2))),
              ),
              _numField(_targetValueController, 'TARGET', Colors.white60),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              GestureDetector(
                onTap: _saveValues,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 10),
                  decoration: BoxDecoration(color: const Color(0xFF22C55E), borderRadius: BorderRadius.circular(20)),
                  child: const Text('Save', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Colors.white)),
                ),
              ),
              const SizedBox(width: 10),
              GestureDetector(
                onTap: () {
                  _currentValueController.text = _rawNum(_goal!.currentValue);
                  _targetValueController.text = _rawNum(_goal!.targetValue);
                  setState(() => _isEditingValue = false);
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 10),
                  decoration: BoxDecoration(color: Colors.white.withOpacity(0.1), borderRadius: BorderRadius.circular(20)),
                  child: Text('Cancel', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Colors.white.withOpacity(0.6))),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _numField(TextEditingController c, String label, Color color) {
    return Column(
      children: [
        Text(label, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 1, color: Colors.white.withOpacity(0.35))),
        const SizedBox(height: 6),
        SizedBox(
          width: 100,
          child: TextField(
            controller: c,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 28, fontWeight: FontWeight.w300, color: color),
            decoration: InputDecoration(
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(vertical: 8),
              filled: true, fillColor: Colors.white.withOpacity(0.05),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
            ),
          ),
        ),
      ],
    );
  }
}

class _GaugePainter extends CustomPainter {
  final double progress;
  final Color color;

  _GaugePainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height - 5);
    final radius = size.width / 2 - 15;
    
    const totalTicks = 40;
    const startAngle = math.pi;
    const sweepAngle = math.pi;
    const tickLength = 14.0;
    
    final filledTicks = (progress * totalTicks).round();

    for (int i = 0; i <= totalTicks; i++) {
      final angle = startAngle + (sweepAngle * i / totalTicks);
      final isFilled = i <= filledTicks;
      
      final innerRadius = radius - tickLength;
      final outerRadius = radius;
      
      final p1 = Offset(center.dx + innerRadius * math.cos(angle), center.dy + innerRadius * math.sin(angle));
      final p2 = Offset(center.dx + outerRadius * math.cos(angle), center.dy + outerRadius * math.sin(angle));

      final paint = Paint()
        ..color = isFilled ? color : Colors.white.withOpacity(0.15)
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round;

      canvas.drawLine(p1, p2, paint);
    }
  }

  @override
  bool shouldRepaint(_GaugePainter old) => old.progress != progress || old.color != color;
}
