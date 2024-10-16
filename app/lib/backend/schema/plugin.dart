class PluginReview {
  String uid;
  DateTime ratedAt;
  double score;
  String review;

  PluginReview({
    required this.uid,
    required this.ratedAt,
    required this.score,
    required this.review,
  });

  factory PluginReview.fromJson(Map<String, dynamic> json) {
    return PluginReview(
      uid: json['uid'],
      ratedAt: DateTime.parse(json['rated_at']),
      score: json['score'],
      review: json['review'],
    );
  }

  toJson() {
    return {
      'uid': uid,
      'rated_at': ratedAt.toIso8601String(),
      'score': score,
      'review': review,
    };
  }

  static List<PluginReview> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => PluginReview.fromJson(e)).toList();
  }
}

class ExternalIntegration {
  String triggersOn;
  String webhookUrl;
  String? setupCompletedUrl;
  String setupInstructionsFilePath;

  ExternalIntegration({
    required this.triggersOn,
    required this.webhookUrl,
    required this.setupCompletedUrl,
    required this.setupInstructionsFilePath,
  });

  factory ExternalIntegration.fromJson(Map<String, dynamic> json) {
    return ExternalIntegration(
      triggersOn: json['triggers_on'],
      webhookUrl: json['webhook_url'],
      setupCompletedUrl: json['setup_completed_url'],
      setupInstructionsFilePath: json['setup_instructions_file_path'],
    );
  }

  String getTriggerOnString() {
    switch (triggersOn) {
      case 'memory_creation':
        return 'Memory Creation';
      case 'transcript_processed':
        return 'Transcript Segment Processed (every 30 seconds during conversation)';
      default:
        return 'Unknown';
    }
  }

  toJson() {
    return {
      'triggers_on': triggersOn,
      'webhook_url': webhookUrl,
      'setup_completed_url': setupCompletedUrl,
      'setup_instructions_file_path': setupInstructionsFilePath,
    };
  }
}

class Plugin {
  String id;
  String name;
  String author;
  String description;
  String image;
  Set<String> capabilities;

  String? memoryPrompt;
  String? chatPrompt;
  ExternalIntegration? externalIntegration;

  List<PluginReview> reviews;
  PluginReview? userReview;
  double? ratingAvg;
  int ratingCount;

  bool enabled;
  bool deleted;
  List<Content>? content;

  Plugin({
    required this.id,
    required this.name,
    required this.author,
    required this.description,
    required this.image,
    required this.capabilities,
    this.memoryPrompt,
    this.chatPrompt,
    this.externalIntegration,
    this.reviews = const [],
    this.userReview,
    this.ratingAvg,
    required this.ratingCount,
    required this.enabled,
    required this.deleted,
    this.content,
  });

  String? getRatingAvg() => ratingAvg?.toStringAsFixed(1);

  bool hasCapability(String capability) => capabilities.contains(capability);

  bool worksWithMemories() => hasCapability('memories');

  bool worksWithChat() => hasCapability('chat');

  bool worksExternally() => hasCapability('external_integration');

  factory Plugin.fromJson(Map<String, dynamic> json) {
    return Plugin(
      id: json['id'],
      name: json['name'],
      author: json['author'],
      description: json['description'],
      image: json['image'],
      chatPrompt: json['chat_prompt'],
      memoryPrompt: json['memory_prompt'],
      externalIntegration: json['external_integration'] != null
          ? ExternalIntegration.fromJson(json['external_integration'])
          : null,
      reviews: PluginReview.fromJsonList(json['reviews'] ?? []),
      userReview: json['user_review'] != null
          ? PluginReview.fromJson(json['user_review'])
          : null,
      ratingAvg: json['rating_avg'],
      ratingCount: json['rating_count'] ?? 0,
      capabilities:
          ((json['capabilities'] ?? []) as List).cast<String>().toSet(),
      deleted: json['deleted'] ?? false,
      enabled: json['enabled'] ?? false,
      content: json["content"] == null
          ? []
          : List<Content>.from(
              json["content"]!.map((x) => Content.fromJson(x))),
    );
  }

  String getImageUrl() =>
      'https://raw.githubusercontent.com/maxwell882000/shopify-components/main/$image';

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'author': author,
      'description': description,
      'image': image,
      'capabilities': capabilities.toList(),
      'memory_prompt': memoryPrompt,
      'chat_prompt': chatPrompt,
      'external_integration': externalIntegration?.toJson(),
      'reviews': reviews.map((e) => e.toJson()).toList(),
      'rating_avg': ratingAvg,
      'user_review': userReview?.toJson(),
      'rating_count': ratingCount,
      'deleted': deleted,
      'enabled': enabled,
      "content": content == null
          ? []
          : List<dynamic>.from(content!.map((x) => x.toJson())),
    };
  }

  static List<Plugin> fromJsonList(List<dynamic> jsonList) =>
      jsonList.map((e) => Plugin.fromJson(e)).toList();
}

class Content {
  String? pluginId;
  String? content;
  String? date;
  bool isExpanded = false;
  bool isFavourite = false;

  Content({
    this.pluginId,
    this.content,
    this.date,
  });

  factory Content.fromJson(Map<String, dynamic> json) => Content(
        pluginId: json["plugin_id"],
        content: json["content"],
        date: (json["date"] != null) ? json["date"].toString() : "",
      );

  Map<String, dynamic> toJson() => {
        "plugin_id": pluginId,
        "date": date,
        "content": content,
      };
}
