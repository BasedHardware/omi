/// Data model for accordion items rendered from LLM XML tags
class AccordionItemData {
  final String title;
  final String content;

  const AccordionItemData({
    required this.title,
    required this.content,
  });

  /// Parse from XML attributes and inner content
  factory AccordionItemData.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
  }) {
    return AccordionItemData(
      title: attributes['title'] ?? 'Untitled',
      content: innerContent.trim(),
    );
  }
}

/// Data model for the entire accordion component
class AccordionDisplayData {
  final String? title;
  final List<AccordionItemData> items;
  final bool allowMultiple;

  const AccordionDisplayData({
    this.title,
    required this.items,
    this.allowMultiple = false,
  });

  bool get isEmpty => items.isEmpty;
}
