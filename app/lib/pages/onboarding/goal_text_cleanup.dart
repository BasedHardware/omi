/// Conservative, offline cleanup of a spoken goal. Only anchored speech/prompt
/// wrappers are removed; the outcome, constraints and negation stay untouched.
String cleanIntroductionGoal(String transcript) {
  var text = transcript.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (text.length >= 2 &&
      ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith('“') && text.endsWith('”')))) {
    text = text.substring(1, text.length - 1).trim();
  }
  final filler = RegExp(r'^(?:um|uh|erm|well|okay|ok|so),\s*', caseSensitive: false);
  while (filler.hasMatch(text)) {
    text = text.replaceFirst(filler, '').trim();
  }
  if (RegExp(
    r'^(?:right now[, ]+)?my\s+(?:(?:number (?:one|1)|#1|main|primary|top|current)\s+)?goal\s+is(?:\s+to)?[.!?]?$',
    caseSensitive: false,
  ).hasMatch(text)) {
    return '';
  }
  text = text.replaceFirst(
    RegExp(
      r'^(?:right now[, ]+)?my\s+(?:(?:number (?:one|1)|#1|main|primary|top|current)\s+)?goal\s+is\s+(?:to\s+)?',
      caseSensitive: false,
    ),
    '',
  );
  text = text.replaceFirst(RegExp(r'^I\s+(?:want|would like)\s+to\s+', caseSensitive: false), '').trim();
  if (text.endsWith('.') && !text.endsWith('..') && !RegExp(r'(?:\b[A-Za-z]\.){2,}$').hasMatch(text)) {
    text = text.substring(0, text.length - 1).trim();
  }
  // An unfinished starter is not itself a goal.
  if (RegExp(r'^(?:(?:right now[, ]+)?my (?:number (?:one|1) )?goal is(?: to)?|I (?:want|would like) to)$',
          caseSensitive: false)
      .hasMatch(text)) {
    return '';
  }
  if (text.isEmpty) return text;
  // Do not alter product names such as iOS, eBay or acronyms.
  final firstWord = text.split(' ').first;
  if (firstWord == firstWord.toLowerCase()) text = text[0].toUpperCase() + text.substring(1);
  return text;
}
