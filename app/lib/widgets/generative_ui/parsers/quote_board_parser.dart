import '../models/quote_board_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <quote-board> tags containing journalist quotes.
///
/// Example:
/// ```xml
/// <quote-board>
///   <quote speaker="Speaker A" time="00:12:45" record="On the record">
///     "We can't fix everything this year, but we can stop it getting worse."
///   </quote>
///   <quote speaker="Speaker B" time="00:27:03" record="Background">
///     "People waited 40 minutes for a bus that never came."
///   </quote>
/// </quote-board>
/// ```
class QuoteBoardParser extends BaseTagParser {
  // Pattern to match <quote-board>...</quote-board> blocks
  static final _quoteBoardPattern = RegExp(
    r'<quote-board>([\s\S]*?)</quote-board>',
    caseSensitive: false,
  );

  // Pattern to match <quote ...>...</quote> tags within quote-board
  static final _quotePattern = RegExp(
    r'<quote\s+([^>]*)>([\s\S]*?)</quote>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _quoteBoardPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final innerContent = match.group(1) ?? '';
    return _parseQuoteBoard(innerContent);
  }

  QuoteBoardSegment? _parseQuoteBoard(String innerContent) {
    final quotes = <QuoteData>[];

    for (final quoteMatch in _quotePattern.allMatches(innerContent)) {
      final quoteAttrString = quoteMatch.group(1) ?? '';
      final quoteContent = quoteMatch.group(2) ?? '';
      final quoteAttrs = parseAttributes(quoteAttrString);

      quotes.add(QuoteData.fromParsed(
        attributes: quoteAttrs,
        innerContent: quoteContent,
      ));
    }

    if (quotes.isEmpty) return null;

    return QuoteBoardSegment(QuoteBoardDisplayData(
      quotes: quotes,
    ));
  }
}
