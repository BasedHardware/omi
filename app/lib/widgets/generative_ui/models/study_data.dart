import 'dart:math';

/// Represents a single study question (flashcard OR multiple choice)
class StudyQuestionData {
  final String question;
  final String correctAnswer;
  final List<String> wrongOptions;

  const StudyQuestionData({
    required this.question,
    required this.correctAnswer,
    this.wrongOptions = const [],
  });

  /// True if this is a flashcard (flip to reveal)
  bool get isFlashcard => wrongOptions.isEmpty;

  /// True if this is a multiple choice question
  bool get isMultipleChoice => wrongOptions.isNotEmpty;

  /// Get all options shuffled (for ABC display)
  List<String> getShuffledOptions() {
    final options = [correctAnswer, ...wrongOptions];
    final random = Random();
    options.shuffle(random);
    return options;
  }

  /// Get the index of correct answer in shuffled options
  int getCorrectIndex(List<String> shuffledOptions) {
    return shuffledOptions.indexOf(correctAnswer);
  }
}

/// Container for a study session
class StudyData {
  final String title;
  final List<StudyQuestionData> questions;

  const StudyData({
    required this.title,
    required this.questions,
  });

  bool get isEmpty => questions.isEmpty;

  int get flashcardCount => questions.where((q) => q.isFlashcard).length;
  int get abcCount => questions.where((q) => q.isMultipleChoice).length;

  /// Filter questions by type
  List<StudyQuestionData> get flashcards =>
      questions.where((q) => q.isFlashcard).toList();
  List<StudyQuestionData> get multipleChoice =>
      questions.where((q) => q.isMultipleChoice).toList();
}

/// Study mode selection
enum StudyMode {
  flashcardsOnly,
  quizOnly,
  mixed,
}

/// Score tracking for a study session
class StudyScore {
  int correctAnswers;
  int totalQuestions;
  int flashcardsKnown;
  int flashcardsTotal;
  int abcCorrect;
  int abcTotal;
  int currentStreak;
  int maxStreak;

  StudyScore({
    this.correctAnswers = 0,
    this.totalQuestions = 0,
    this.flashcardsKnown = 0,
    this.flashcardsTotal = 0,
    this.abcCorrect = 0,
    this.abcTotal = 0,
    this.currentStreak = 0,
    this.maxStreak = 0,
  });

  double get percentage =>
      totalQuestions > 0 ? (correctAnswers / totalQuestions) * 100 : 0;

  void recordCorrect({required bool isFlashcard}) {
    correctAnswers++;
    currentStreak++;
    if (currentStreak > maxStreak) {
      maxStreak = currentStreak;
    }
    if (isFlashcard) {
      flashcardsKnown++;
    } else {
      abcCorrect++;
    }
  }

  void recordIncorrect() {
    currentStreak = 0;
  }
}
