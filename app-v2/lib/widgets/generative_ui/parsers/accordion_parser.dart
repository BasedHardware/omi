import '../models/accordion_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for `<accordion>` tags containing expandable section elements.
class AccordionParser extends BaseTagParser {
  static final _accordionPattern = RegExp(r'<accordion([^>]*)>([\s\S]*?)</accordion>', caseSensitive: false);

  static final _sectionPattern = RegExp(r'<section\s+([^>]*)>([\s\S]*?)</section>', caseSensitive: false);

  @override
  RegExp get pattern => _accordionPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final accordionAttributes = match.group(1) ?? '';
    final innerContent = match.group(2) ?? '';
    return _parseAccordion(accordionAttributes, innerContent);
  }

  AccordionSegment? _parseAccordion(String accordionAttributes, String innerContent) {
    final attributes = parseAttributes(accordionAttributes);
    final items = <AccordionItemData>[];

    for (final sectionMatch in _sectionPattern.allMatches(innerContent)) {
      final sectionAttrString = sectionMatch.group(1) ?? '';
      final sectionContent = sectionMatch.group(2) ?? '';
      final sectionAttrs = parseAttributes(sectionAttrString);

      items.add(AccordionItemData.fromParsed(attributes: sectionAttrs, innerContent: sectionContent));
    }

    if (items.isEmpty) return null;

    return AccordionSegment(
      AccordionDisplayData(
        title: attributes['title'],
        items: items,
        allowMultiple: attributes['multiple']?.toLowerCase() == 'true',
      ),
    );
  }
}
