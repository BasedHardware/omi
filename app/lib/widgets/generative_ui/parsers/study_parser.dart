import '../models/study_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for study mode tags (flashcards and ABC questions)
///
/// XML Format:
/// ```xml
/// <study title="Topic Title">
///   <q>Question text<a>Answer text</a></q>
///   <q>Question<a>Correct</a><o>Wrong 1</o><o>Wrong 2</o><o>Wrong 3</o></q>
/// </study>
/// ```
class StudyParser extends BaseTagParser {
  static final _studyPattern = RegExp(
    r'<study([^>]*)>([\s\S]*?)</study>',
    caseSensitive: false,
  );

  static final _questionPattern = RegExp(
    r'<q>([\s\S]*?)</q>',
    caseSensitive: false,
  );

  static final _answerPattern = RegExp(
    r'<a>([\s\S]*?)</a>',
    caseSensitive: false,
  );

  static final _optionPattern = RegExp(
    r'<o>([\s\S]*?)</o>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _studyPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final attributes = parseAttributes(match.group(1) ?? '');
    final innerContent = match.group(2) ?? '';

    final questions = <StudyQuestionData>[];

    for (final qMatch in _questionPattern.allMatches(innerContent)) {
      final qContent = qMatch.group(1) ?? '';

      // Extract answer (first <a> tag)
      final answerMatch = _answerPattern.firstMatch(qContent);
      if (answerMatch == null) continue;

      final correctAnswer = answerMatch.group(1)?.trim() ?? '';
      if (correctAnswer.isEmpty) continue;

      // Extract wrong options (<o> tags)
      final wrongOptions = _optionPattern
          .allMatches(qContent)
          .map((m) => m.group(1)?.trim() ?? '')
          .where((s) => s.isNotEmpty)
          .toList();

      // Question text is content before <a> tag
      final questionText = qContent.substring(0, answerMatch.start).trim();
      if (questionText.isEmpty) continue;

      questions.add(StudyQuestionData(
        question: questionText,
        correctAnswer: correctAnswer,
        wrongOptions: wrongOptions,
      ));
    }

    if (questions.isEmpty) return null;

    return StudySegment(StudyData(
      title: attributes['title'] ?? 'Study Session',
      questions: questions,
    ));
  }
}
