import '../models/study_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for study mode tags (flashcards and ABC questions).
class StudyParser extends BaseTagParser {
  static final _studyPattern = RegExp(r'<study([^>]*)>([\s\S]*?)</study>', caseSensitive: false);

  static final _questionPattern = RegExp(r'<q>([\s\S]*?)</q>', caseSensitive: false);

  static final _answerPattern = RegExp(r'<a>([\s\S]*?)</a>', caseSensitive: false);

  static final _optionPattern = RegExp(r'<o>([\s\S]*?)</o>', caseSensitive: false);

  @override
  RegExp get pattern => _studyPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final attributes = parseAttributes(match.group(1) ?? '');
    final innerContent = match.group(2) ?? '';

    final questions = <StudyQuestionData>[];

    for (final qMatch in _questionPattern.allMatches(innerContent)) {
      final qContent = qMatch.group(1) ?? '';

      final answerMatch = _answerPattern.firstMatch(qContent);
      if (answerMatch == null) continue;

      final correctAnswer = answerMatch.group(1)?.trim() ?? '';
      if (correctAnswer.isEmpty) continue;

      final wrongOptions = _optionPattern
          .allMatches(qContent)
          .map((m) => m.group(1)?.trim() ?? '')
          .where((s) => s.isNotEmpty)
          .toList();

      final questionText = qContent.substring(0, answerMatch.start).trim();
      if (questionText.isEmpty) continue;

      questions.add(
        StudyQuestionData(question: questionText, correctAnswer: correctAnswer, wrongOptions: wrongOptions),
      );
    }

    if (questions.isEmpty) return null;

    return StudySegment(StudyData(title: attributes['title'] ?? 'Study Session', questions: questions));
  }
}
