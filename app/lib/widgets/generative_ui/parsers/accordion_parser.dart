import '../models/accordion_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <accordion> tags containing expandable section elements.
///
/// Example:
/// ```xml
/// <accordion title="FAQ">
///   <section title="What is this?">
///     This is the content that will be shown when expanded.
///     It supports **markdown** formatting.
///   </section>
///   <section title="How does it work?">
///     Another expandable section with its own content.
///   </section>
/// </accordion>
/// ```
class AccordionParser extends BaseTagParser {
  // Pattern to match <accordion ...>...</accordion> blocks
  static final _accordionPattern = RegExp(
    r'<accordion([^>]*)>([\s\S]*?)</accordion>',
    caseSensitive: false,
  );

  // Pattern to match <section title="...">...</section> tags within accordion
  static final _sectionPattern = RegExp(
    r'<section\s+([^>]*)>([\s\S]*?)</section>',
    caseSensitive: false,
  );

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

      items.add(AccordionItemData.fromParsed(
        attributes: sectionAttrs,
        innerContent: sectionContent,
      ));
    }

    if (items.isEmpty) return null;

    return AccordionSegment(AccordionDisplayData(
      title: attributes['title'],
      items: items,
      allowMultiple: attributes['multiple']?.toLowerCase() == 'true',
    ));
  }
}
