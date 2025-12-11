import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/study_data.dart';

/// Screen states for the study session
enum _StudyState {
  modeSelection,
  studying,
  results,
}

/// Full-screen study experience with flashcards and ABC questions
class StudyScreen extends StatefulWidget {
  final StudyData data;

  const StudyScreen({
    super.key,
    required this.data,
  });

  @override
  State<StudyScreen> createState() => _StudyScreenState();
}

class _StudyScreenState extends State<StudyScreen>
    with TickerProviderStateMixin {
  _StudyState _state = _StudyState.modeSelection;
  StudyMode? _selectedMode;
  int _currentIndex = 0;
  late StudyScore _score;
  late List<StudyQuestionData> _activeQuestions;

  // Flashcard state
  bool _isFlipped = false;
  late AnimationController _flipController;
  late Animation<double> _flipAnimation;

  // ABC state
  int? _selectedOption;
  bool _isRevealed = false;
  List<String>? _shuffledOptions;

  @override
  void initState() {
    super.initState();
    _score = StudyScore();
    _activeQuestions = [];

    _flipController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _flipAnimation = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _flipController, curve: Curves.easeInOutCubic),
    );
  }

  @override
  void dispose() {
    _flipController.dispose();
    super.dispose();
  }

  void _selectMode(StudyMode mode) {
    setState(() {
      _selectedMode = mode;
      _activeQuestions = _getQuestionsForMode(mode);
      _score = StudyScore(
        totalQuestions: _activeQuestions.length,
        flashcardsTotal:
            _activeQuestions.where((q) => q.isFlashcard).length,
        abcTotal:
            _activeQuestions.where((q) => q.isMultipleChoice).length,
      );
      _currentIndex = 0;
      _state = _StudyState.studying;
      _prepareCurrentQuestion();
    });
    HapticFeedback.mediumImpact();
  }

  List<StudyQuestionData> _getQuestionsForMode(StudyMode mode) {
    switch (mode) {
      case StudyMode.flashcardsOnly:
        return widget.data.flashcards;
      case StudyMode.quizOnly:
        return widget.data.multipleChoice;
      case StudyMode.mixed:
        final questions = List<StudyQuestionData>.from(widget.data.questions);
        questions.shuffle(Random());
        return questions;
    }
  }

  void _prepareCurrentQuestion() {
    _isFlipped = false;
    _flipController.reset();
    _selectedOption = null;
    _isRevealed = false;

    if (_currentIndex < _activeQuestions.length) {
      final question = _activeQuestions[_currentIndex];
      if (question.isMultipleChoice) {
        _shuffledOptions = question.getShuffledOptions();
      }
    }
  }

  void _flipCard() {
    if (_isFlipped) return;
    setState(() {
      _isFlipped = true;
    });
    _flipController.forward();
    HapticFeedback.selectionClick();
  }

  void _handleFlashcardResult(bool gotIt) {
    if (gotIt) {
      _score.recordCorrect(isFlashcard: true);
    } else {
      _score.recordIncorrect();
    }
    HapticFeedback.mediumImpact();
    _nextQuestion();
  }

  void _selectOption(int index) {
    if (_isRevealed) return;
    setState(() {
      _selectedOption = index;
    });
    HapticFeedback.selectionClick();
  }

  void _checkAnswer() {
    if (_selectedOption == null || _isRevealed) return;

    final question = _activeQuestions[_currentIndex];
    final isCorrect =
        _shuffledOptions![_selectedOption!] == question.correctAnswer;

    setState(() {
      _isRevealed = true;
    });

    if (isCorrect) {
      _score.recordCorrect(isFlashcard: false);
      HapticFeedback.mediumImpact();
    } else {
      _score.recordIncorrect();
      HapticFeedback.heavyImpact();
    }
  }

  void _nextQuestion() {
    if (_currentIndex < _activeQuestions.length - 1) {
      setState(() {
        _currentIndex++;
        _prepareCurrentQuestion();
      });
    } else {
      setState(() {
        _state = _StudyState.results;
      });
      HapticFeedback.heavyImpact();
    }
  }

  void _tryAgain() {
    setState(() {
      _state = _StudyState.modeSelection;
      _currentIndex = 0;
      _score = StudyScore();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: _buildContent(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.close, color: Colors.white),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              widget.data.title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (_state == _StudyState.studying) ...[
            // Streak indicator
            if (_score.currentStreak >= 2)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFFFBBF24), Color(0xFFF59E0B)],
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.local_fire_department,
                        size: 16, color: Colors.white),
                    const SizedBox(width: 4),
                    Text(
                      '${_score.currentStreak}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
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

  Widget _buildContent() {
    switch (_state) {
      case _StudyState.modeSelection:
        return _buildModeSelection();
      case _StudyState.studying:
        return _buildStudyView();
      case _StudyState.results:
        return _buildResults();
    }
  }

  Widget _buildModeSelection() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Choose your study mode',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '${widget.data.questions.length} questions available',
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 32),

          // Flashcards mode
          if (widget.data.flashcardCount > 0)
            _ModeCard(
              icon: Icons.flip,
              title: 'Flashcards',
              subtitle: '${widget.data.flashcardCount} cards · Flip to reveal',
              color: const Color(0xFF10B981),
              onTap: () => _selectMode(StudyMode.flashcardsOnly),
            ),
          if (widget.data.flashcardCount > 0) const SizedBox(height: 12),

          // Quiz mode
          if (widget.data.abcCount > 0)
            _ModeCard(
              icon: Icons.quiz_outlined,
              title: 'Quiz Mode',
              subtitle: '${widget.data.abcCount} questions · Multiple choice',
              color: const Color(0xFFF59E0B),
              onTap: () => _selectMode(StudyMode.quizOnly),
            ),
          if (widget.data.abcCount > 0) const SizedBox(height: 12),

          // Mixed mode
          if (widget.data.flashcardCount > 0 && widget.data.abcCount > 0)
            _ModeCard(
              icon: Icons.shuffle,
              title: 'Mixed Mode',
              subtitle:
                  '${widget.data.questions.length} total · All question types',
              color: const Color(0xFF8B5CF6),
              onTap: () => _selectMode(StudyMode.mixed),
            ),
        ],
      ),
    );
  }

  Widget _buildStudyView() {
    final question = _activeQuestions[_currentIndex];

    return Column(
      children: [
        // Progress bar
        _buildProgressBar(),

        // Question content
        Expanded(
          child: question.isFlashcard
              ? _buildFlashcard(question)
              : _buildAbcQuestion(question),
        ),
      ],
    );
  }

  Widget _buildProgressBar() {
    final progress = (_currentIndex + 1) / _activeQuestions.length;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Question ${_currentIndex + 1} of ${_activeQuestions.length}',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.6),
                  fontSize: 12,
                ),
              ),
              Text(
                '${(progress * 100).toInt()}%',
                style: const TextStyle(
                  color: Color(0xFF8B5CF6),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            height: 6,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.1),
              borderRadius: BorderRadius.circular(3),
            ),
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: progress,
              child: Container(
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF8B5CF6), Color(0xFF6366F1)],
                  ),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFlashcard(StudyQuestionData question) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          Expanded(
            child: GestureDetector(
              onTap: _isFlipped ? null : _flipCard,
              child: AnimatedBuilder(
                animation: _flipAnimation,
                builder: (context, child) {
                  final angle = _flipAnimation.value * pi;
                  final isFront = angle < pi / 2;

                  return Transform(
                    transform: Matrix4.identity()
                      ..setEntry(3, 2, 0.001)
                      ..rotateY(angle),
                    alignment: Alignment.center,
                    child: isFront
                        ? _buildCardFace(
                            content: question.question,
                            isBack: false,
                          )
                        : Transform(
                            transform: Matrix4.identity()..rotateY(pi),
                            alignment: Alignment.center,
                            child: _buildCardFace(
                              content: question.correctAnswer,
                              isBack: true,
                            ),
                          ),
                  );
                },
              ),
            ),
          ),

          const SizedBox(height: 24),

          // Action buttons (shown after flip)
          if (_isFlipped)
            Row(
              children: [
                Expanded(
                  child: _ActionButton(
                    icon: Icons.refresh,
                    label: 'Review',
                    color: const Color(0xFFF59E0B),
                    onTap: () => _handleFlashcardResult(false),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _ActionButton(
                    icon: Icons.check,
                    label: 'Got it!',
                    color: const Color(0xFF10B981),
                    onTap: () => _handleFlashcardResult(true),
                  ),
                ),
              ],
            )
          else
            Text(
              'Tap card to reveal answer',
              style: TextStyle(
                color: Colors.white.withOpacity(0.5),
                fontSize: 14,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildCardFace({
    required String content,
    required bool isBack,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: isBack
            ? Colors.white.withOpacity(0.1)
            : Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isBack
              ? const Color(0xFF10B981).withOpacity(0.3)
              : Colors.white.withOpacity(0.15),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            isBack ? Icons.lightbulb_outline : Icons.help_outline,
            color: isBack
                ? const Color(0xFF10B981).withOpacity(0.6)
                : Colors.white.withOpacity(0.3),
            size: 32,
          ),
          const SizedBox(height: 24),
          Text(
            content,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: isBack ? Colors.white : Colors.white.withOpacity(0.9),
              fontSize: 20,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAbcQuestion(StudyQuestionData question) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Question
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              question.question,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                height: 1.5,
              ),
            ),
          ),

          const SizedBox(height: 24),

          // Options
          Expanded(
            child: ListView.builder(
              itemCount: _shuffledOptions!.length,
              itemBuilder: (context, index) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _buildOption(index, question),
                );
              },
            ),
          ),

          // Check / Next button
          if (_selectedOption != null && !_isRevealed)
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _checkAnswer,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF8B5CF6),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Text(
                  'Check Answer',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            )
          else if (_isRevealed)
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _nextQuestion,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white.withOpacity(0.1),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: Text(
                  _currentIndex < _activeQuestions.length - 1
                      ? 'Next Question'
                      : 'See Results',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildOption(int index, StudyQuestionData question) {
    final letter = String.fromCharCode(65 + index); // A, B, C, D
    final isSelected = _selectedOption == index;
    final isCorrect = _shuffledOptions![index] == question.correctAnswer;

    Color borderColor = Colors.white.withOpacity(0.1);
    Color bgColor = Colors.white.withOpacity(0.02);
    IconData? trailingIcon;

    if (_isRevealed) {
      if (isCorrect) {
        borderColor = const Color(0xFF10B981);
        bgColor = const Color(0xFF10B981).withOpacity(0.15);
        trailingIcon = Icons.check_circle;
      } else if (isSelected && !isCorrect) {
        borderColor = const Color(0xFFEF4444);
        bgColor = const Color(0xFFEF4444).withOpacity(0.15);
        trailingIcon = Icons.cancel;
      }
    } else if (isSelected) {
      borderColor = const Color(0xFF8B5CF6);
      bgColor = const Color(0xFF8B5CF6).withOpacity(0.1);
    }

    return GestureDetector(
      onTap: _isRevealed ? null : () => _selectOption(index),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor, width: 1.5),
        ),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: isSelected
                    ? const Color(0xFF8B5CF6).withOpacity(0.2)
                    : Colors.white.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Text(
                  letter,
                  style: TextStyle(
                    color: isSelected
                        ? const Color(0xFF8B5CF6)
                        : Colors.white.withOpacity(0.7),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                _shuffledOptions![index],
                style: TextStyle(
                  color: Colors.white.withOpacity(0.9),
                  fontSize: 16,
                ),
              ),
            ),
            if (trailingIcon != null)
              Icon(
                trailingIcon,
                color: isCorrect
                    ? const Color(0xFF10B981)
                    : const Color(0xFFEF4444),
                size: 24,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildResults() {
    final percentage = _score.percentage;
    final tier = _getTier(percentage);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const SizedBox(height: 24),

          // Score circle
          Container(
            width: 180,
            height: 180,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: tier.color.withOpacity(0.3),
                width: 8,
              ),
            ),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '${percentage.toInt()}%',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 48,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    tier.label,
                    style: TextStyle(
                      color: tier.color,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 24),

          // Motivational message
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              tier.message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withOpacity(0.8),
                fontSize: 16,
                height: 1.5,
              ),
            ),
          ),

          const SizedBox(height: 32),

          // Stats card
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              children: [
                if (_score.flashcardsTotal > 0)
                  _statRow(
                    Icons.flip,
                    'Flashcards',
                    '${_score.flashcardsKnown}/${_score.flashcardsTotal}',
                  ),
                if (_score.flashcardsTotal > 0 && _score.abcTotal > 0)
                  const SizedBox(height: 12),
                if (_score.abcTotal > 0)
                  _statRow(
                    Icons.quiz_outlined,
                    'Quiz Questions',
                    '${_score.abcCorrect}/${_score.abcTotal}',
                  ),
                const SizedBox(height: 12),
                _statRow(
                  Icons.local_fire_department,
                  'Best Streak',
                  '${_score.maxStreak}',
                ),
              ],
            ),
          ),

          const SizedBox(height: 32),

          // Action buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _tryAgain,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: BorderSide(color: Colors.white.withOpacity(0.3)),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text('Try Again'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: ElevatedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF8B5CF6),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text('Done'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _statRow(IconData icon, String label, String value) {
    return Row(
      children: [
        Icon(icon, color: Colors.white.withOpacity(0.6), size: 20),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 14,
            ),
          ),
        ),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  _PerformanceTier _getTier(double percentage) {
    if (percentage >= 90) {
      return _PerformanceTier(
        label: 'Excellent!',
        color: const Color(0xFF10B981),
        message: "Outstanding! You've mastered this material!",
      );
    } else if (percentage >= 70) {
      return _PerformanceTier(
        label: 'Great!',
        color: const Color(0xFF8B5CF6),
        message: 'Great progress! Just a few concepts to reinforce.',
      );
    } else if (percentage >= 50) {
      return _PerformanceTier(
        label: 'Good effort',
        color: const Color(0xFFF59E0B),
        message: "You're building a foundation. Keep practicing!",
      );
    } else {
      return _PerformanceTier(
        label: 'Keep trying',
        color: const Color(0xFFEF4444),
        message: 'Every expert was once a beginner. Try again!',
      );
    }
  }
}

class _PerformanceTier {
  final String label;
  final Color color;
  final String message;

  _PerformanceTier({
    required this.label,
    required this.color,
    required this.message,
  });
}

class _ModeCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  const _ModeCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: color.withOpacity(0.1),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: color.withOpacity(0.3),
            width: 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: color.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: color, size: 24),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right,
              color: Colors.white.withOpacity(0.5),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ActionButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: color.withOpacity(0.15),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: color.withOpacity(0.3),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
