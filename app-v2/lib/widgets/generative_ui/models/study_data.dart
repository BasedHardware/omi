import 'dart:math';

/// Represents a single study question (flashcard OR multiple choice).
class StudyQuestionData {
  final String question;
  final String correctAnswer;
  final List<String> wrongOptions;

  const StudyQuestionData({required this.question, required this.correctAnswer, this.wrongOptions = const []});

  bool get isFlashcard => wrongOptions.isEmpty;
  bool get isMultipleChoice => wrongOptions.isNotEmpty;

  List<String> getShuffledOptions() {
    final options = [correctAnswer, ...wrongOptions];
    final random = Random();
    options.shuffle(random);
    return options;
  }

  int getCorrectIndex(List<String> shuffledOptions) {
    return shuffledOptions.indexOf(correctAnswer);
  }
}

/// Container for a study session.
class StudyData {
  final String title;
  final List<StudyQuestionData> questions;

  const StudyData({required this.title, required this.questions});

  bool get isEmpty => questions.isEmpty;

  int get flashcardCount => questions.where((q) => q.isFlashcard).length;
  int get abcCount => questions.where((q) => q.isMultipleChoice).length;

  List<StudyQuestionData> get flashcards => questions.where((q) => q.isFlashcard).toList();
  List<StudyQuestionData> get multipleChoice => questions.where((q) => q.isMultipleChoice).toList();
}

/// Study mode selection.
enum StudyMode { flashcardsOnly, quizOnly, mixed }
