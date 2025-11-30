/// Data model for a rich list item rendered from LLM XML tags
class RichListItemData {
  final String title;
  final String? description;
  final String? thumbnailUrl;
  final String? url;

  const RichListItemData({
    required this.title,
    this.description,
    this.thumbnailUrl,
    this.url,
  });

  /// Parse from XML attributes map
  factory RichListItemData.fromAttributes(Map<String, String> attributes) {
    return RichListItemData(
      title: attributes['title'] ?? '',
      description: attributes['description'],
      thumbnailUrl: attributes['thumb'],
      url: attributes['url'],
    );
  }

  bool get hasUrl => url != null && url!.isNotEmpty;
  bool get hasThumbnail => thumbnailUrl != null && thumbnailUrl!.isNotEmpty;
}
