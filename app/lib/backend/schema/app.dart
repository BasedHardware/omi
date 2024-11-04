class AppReview {
  String uid;
  DateTime ratedAt;
  double score;
  String review;

  AppReview({
    required this.uid,
    required this.ratedAt,
    required this.score,
    required this.review,
  });

  factory AppReview.fromJson(Map<String, dynamic> json) {
    return AppReview(
      uid: json['uid'],
      ratedAt: DateTime.parse(json['rated_at']).toLocal(),
      score: json['score'],
      review: json['review'],
    );
  }

  toJson() {
    return {
      'uid': uid,
      'rated_at': ratedAt.toUtc().toIso8601String(),
      'score': score,
      'review': review,
    };
  }

  static List<AppReview> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => AppReview.fromJson(e)).toList();
  }
}

class AuthStep {
  String name;
  String url;

  AuthStep({
    required this.name,
    required this.url,
  });

  factory AuthStep.fromJson(Map<String, dynamic> json) {
    return AuthStep(
      name: json['name'],
      url: json['url'],
    );
  }

  toJson() {
    return {'name': name, 'url': url};
  }
}

class ExternalIntegration {
  String triggersOn;
  String webhookUrl;
  String? setupCompletedUrl;
  String setupInstructionsFilePath;
  List<AuthStep> authSteps;

  ExternalIntegration({
    required this.triggersOn,
    required this.webhookUrl,
    required this.setupCompletedUrl,
    required this.setupInstructionsFilePath,
    this.authSteps = const [],
  });

  factory ExternalIntegration.fromJson(Map<String, dynamic> json) {
    return ExternalIntegration(
      triggersOn: json['triggers_on'],
      webhookUrl: json['webhook_url'],
      setupCompletedUrl: json['setup_completed_url'],
      setupInstructionsFilePath: json['setup_instructions_file_path'],
      authSteps: json['auth_steps'] == null
          ? []
          : (json['auth_steps'] ?? []).map<AuthStep>((e) => AuthStep.fromJson(e)).toList(),
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
      'auth_steps': authSteps.map((e) => e.toJson()).toList(),
    };
  }
}

class AppUsageHistory {
  DateTime date;
  int count;

  AppUsageHistory({
    required this.date,
    required this.count,
  });

  factory AppUsageHistory.fromJson(Map<String, dynamic> json) {
    return AppUsageHistory(
      date: DateTime.parse(json['date']).toLocal(),
      count: json['count'],
    );
  }

  static List<AppUsageHistory> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => AppUsageHistory.fromJson(e)).toList();
  }

  toJson() {
    return {
      'date': date.toUtc().toIso8601String(),
      'count': count,
    };
  }
}

class App {
  String id;
  String name;
  String author;
  String description;
  String image;
  Set<String> capabilities;
  bool private;

  String? memoryPrompt;
  String? chatPrompt;
  ExternalIntegration? externalIntegration;

  // can be used for

  List<AppReview> reviews;
  AppReview? userReview;
  double? ratingAvg;
  int ratingCount;
  int installs;

  bool enabled;
  bool deleted;

  App({
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
    this.installs = 0,
    required this.ratingCount,
    required this.enabled,
    required this.deleted,
    this.private = false,
  });

  String? getRatingAvg() => ratingAvg?.toStringAsFixed(1);

  bool hasCapability(String capability) => capabilities.contains(capability);

  bool worksWithMemories() => hasCapability('memories');

  bool worksWithChat() => hasCapability('chat');

  bool worksExternally() => hasCapability('external_integration');

  factory App.fromJson(Map<String, dynamic> json) {
    return App(
      id: json['id'],
      name: json['name'],
      author: json['author'],
      description: json['description'],
      image: json['image'],
      chatPrompt: json['chat_prompt'],
      memoryPrompt: json['memory_prompt'],
      externalIntegration:
          json['external_integration'] != null ? ExternalIntegration.fromJson(json['external_integration']) : null,
      reviews: AppReview.fromJsonList(json['reviews'] ?? []),
      userReview: json['user_review'] != null ? AppReview.fromJson(json['user_review']) : null,
      ratingAvg: json['rating_avg'],
      ratingCount: json['rating_count'] ?? 0,
      capabilities: ((json['capabilities'] ?? []) as List).cast<String>().toSet(),
      deleted: json['deleted'] ?? false,
      enabled: json['enabled'] ?? false,
      installs: json['installs'] ?? 0,
      private: json['private'] ?? json['id'].toString().contains('private'),
    );
  }

  String getImageUrl() {
    if (image.startsWith('http')) {
      return image;
    } else {
      return 'https://raw.githubusercontent.com/BasedHardware/Omi/main$image';
    }
  }

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
      'installs': installs,
    };
  }

  static List<App> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => App.fromJson(e)).toList();
}

class Category {
  String title;
  String id;
  Category({
    required this.title,
    required this.id,
  });

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(
      title: json['title'],
      id: json['id'],
    );
  }

  toJson() {
    return {
      'title': title,
      'id': id,
    };
  }

  static List<Category> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => Category.fromJson(e)).toList();
  }
}
