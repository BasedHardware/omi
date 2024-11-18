import 'package:friend_private/widgets/extensions/string.dart';

class AppReview {
  String uid;
  DateTime ratedAt;
  double score;
  String review;
  String username;
  String response;
  DateTime? updatedAt;
  DateTime? respondedAt;

  AppReview({
    required this.uid,
    required this.ratedAt,
    required this.score,
    required this.review,
    this.username = '',
    this.response = '',
    this.updatedAt,
    this.respondedAt,
  });

  factory AppReview.fromJson(Map<String, dynamic> json) {
    return AppReview(
      uid: json['uid'],
      ratedAt: DateTime.parse(json['rated_at']).toLocal(),
      score: json['score'],
      review: json['review'],
      username: json['user_name'] ?? '',
      response: json['response'] ?? '',
      updatedAt: (json['updated_at'] == "" || json['updated_at'] == null)
          ? null
          : DateTime.parse(json['updated_at']).toLocal(),
      respondedAt: (json['responded_at'] == "" || json['responded_at'] == null)
          ? null
          : DateTime.parse(json['responded_at']).toLocal(),
    );
  }

  toJson() {
    return {
      'uid': uid,
      'rated_at': ratedAt.toUtc().toIso8601String(),
      'score': score,
      'review': review,
      'username': username,
      'response': response,
      'updated_at': updatedAt?.toUtc().toIso8601String() ?? '',
      'responded_at': respondedAt?.toUtc().toIso8601String() ?? '',
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
  bool isInstructionsUrl;
  List<AuthStep> authSteps;

  ExternalIntegration({
    required this.triggersOn,
    required this.webhookUrl,
    required this.setupCompletedUrl,
    required this.setupInstructionsFilePath,
    required this.isInstructionsUrl,
    this.authSteps = const [],
  });

  factory ExternalIntegration.fromJson(Map<String, dynamic> json) {
    return ExternalIntegration(
      triggersOn: json['triggers_on'],
      webhookUrl: json['webhook_url'],
      setupCompletedUrl: json['setup_completed_url'],
      isInstructionsUrl: json['is_instructions_url'] ?? false,
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
      'is_instructions_url': isInstructionsUrl,
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
  String? uid;
  String name;
  String author;
  String? email;
  String category;
  String status;
  String description;
  String image;
  Set<String> capabilities;
  bool private;
  bool approved;
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
    required this.status,
    this.uid,
    this.email,
    required this.category,
    required this.approved,
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
      category: json['category'] ?? 'other',
      approved: json['approved'] ?? true,
      status: json['status'] ?? 'approved',
      id: json['id'],
      email: json['email'] ?? '',
      uid: json['uid'] ?? '',
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

  updateReviewResponse(String response, reviewId, DateTime respondedAt) {
    var idx = reviews.indexWhere((element) => element.uid == reviewId);
    if (idx != -1) {
      reviews[idx].response = response;
      reviews[idx].updatedAt = respondedAt;
    }
  }

  bool isOwner(String uid) {
    return this.uid == uid;
  }

  bool isUnderReview() {
    return status == 'under-review';
  }

  bool isRejected() {
    return status == 'rejected';
  }

  String getCategoryName() {
    return category.decodeString.split('-').map((e) => e.capitalize()).join(' ');
  }

  List<AppCapability> getCapabilitiesFromIds(List<AppCapability> allCapabilities) {
    return allCapabilities.where((e) => capabilities.contains(e.id)).toList();
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
      'private': private,
      'category': category,
      'approved': approved,
      'status': status,
      'uid': uid,
      'email': email,
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

class AppCapability {
  String title;
  String id;
  List<TriggerEvent> triggerEvents = [];
  List<NotificationScope> notificationScopes = [];
  AppCapability({
    required this.title,
    required this.id,
    this.triggerEvents = const [],
    this.notificationScopes = const [],
  });

  factory AppCapability.fromJson(Map<String, dynamic> json) {
    return AppCapability(
      title: json['title'],
      id: json['id'],
      triggerEvents: TriggerEvent.fromJsonList(json['triggers'] ?? []),
      notificationScopes: NotificationScope.fromJsonList(json['scopes'] ?? []),
    );
  }

  toJson() {
    return {
      'title': title,
      'id': id,
      'triggers': triggerEvents.map((e) => e.toJson()).toList(),
      'scopes': notificationScopes.map((e) => e.toJson()).toList(),
    };
  }

  static List<AppCapability> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => AppCapability.fromJson(e)).toList();
  }

  bool hasTriggers() => triggerEvents.isNotEmpty;
  bool hasScopes() => notificationScopes.isNotEmpty;
}

class TriggerEvent {
  String title;
  String id;
  TriggerEvent({
    required this.title,
    required this.id,
  });

  factory TriggerEvent.fromJson(Map<String, dynamic> json) {
    return TriggerEvent(
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

  static List<TriggerEvent> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => TriggerEvent.fromJson(e)).toList();
  }
}

class NotificationScope {
  String title;
  String id;
  NotificationScope({
    required this.title,
    required this.id,
  });

  factory NotificationScope.fromJson(Map<String, dynamic> json) {
    return NotificationScope(
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

  static List<NotificationScope> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => NotificationScope.fromJson(e)).toList();
  }
}
