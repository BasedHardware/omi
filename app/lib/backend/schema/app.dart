import 'package:omi/utils/other/string_utils.dart';
import 'package:omi/widgets/extensions/string.dart';

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

class Action {
  String action;

  Action({
    required this.action,
  });

  factory Action.fromJson(Map<String, dynamic> json) {
    return Action(
      action: json['action'],
    );
  }

  toJson() {
    return {
      'action': action,
    };
  }
}

class ChatTool {
  String name;
  String description;
  String endpoint;
  String method;
  bool authRequired;
  String? statusMessage;

  ChatTool({
    required this.name,
    required this.description,
    required this.endpoint,
    this.method = 'POST',
    this.authRequired = true,
    this.statusMessage,
  });

  factory ChatTool.fromJson(Map<String, dynamic> json) {
    return ChatTool(
      name: json['name'],
      description: json['description'],
      endpoint: json['endpoint'],
      method: json['method'] ?? 'POST',
      authRequired: json['auth_required'] ?? true,
      statusMessage: json['status_message'],
    );
  }

  toJson() {
    return {
      'name': name,
      'description': description,
      'endpoint': endpoint,
      'method': method,
      'auth_required': authRequired,
      if (statusMessage != null) 'status_message': statusMessage,
    };
  }

  static List<ChatTool> fromJsonList(List<dynamic>? jsonList) {
    if (jsonList == null) return [];
    return jsonList.map((e) => ChatTool.fromJson(e)).toList();
  }
}

class ExternalIntegration {
  String? triggersOn;
  String? webhookUrl;
  String? setupCompletedUrl;
  String? setupInstructionsFilePath;
  bool? isInstructionsUrl;
  List<AuthStep> authSteps = [];
  String? appHomeUrl;
  List<Action>? actions;
  String? chatToolsManifestUrl;

  ExternalIntegration({
    this.triggersOn,
    this.webhookUrl,
    this.setupCompletedUrl,
    this.setupInstructionsFilePath,
    this.isInstructionsUrl,
    this.authSteps = const [],
    this.appHomeUrl,
    this.actions,
    this.chatToolsManifestUrl,
  });

  factory ExternalIntegration.fromJson(Map<String, dynamic> json) {
    return ExternalIntegration(
      triggersOn: json['triggers_on'],
      webhookUrl: json['webhook_url'],
      setupCompletedUrl: json['setup_completed_url'],
      appHomeUrl: json['app_home_url'],
      isInstructionsUrl: json['is_instructions_url'] ?? false,
      setupInstructionsFilePath: json['setup_instructions_file_path'],
      authSteps: json['auth_steps'] == null
          ? []
          : (json['auth_steps'] ?? []).map<AuthStep>((e) => AuthStep.fromJson(e)).toList(),
      actions: json['actions'] == null ? null : (json['actions'] ?? []).map<Action>((e) => Action.fromJson(e)).toList(),
      chatToolsManifestUrl: json['chat_tools_manifest_url'],
    );
  }

  String getTriggerOnString() {
    switch (triggersOn) {
      case 'memory_creation':
        return 'Conversation Creation';
      case 'transcript_processed':
        return 'Transcript Segment Processed';
      case 'audio_bytes':
        return 'Audio Bytes Streamed';
      default:
        return 'Unknown';
    }
  }

  toJson() {
    return {
      'triggers_on': triggersOn,
      'webhook_url': webhookUrl,
      'setup_completed_url': setupCompletedUrl,
      'app_home_url': appHomeUrl,
      'is_instructions_url': isInstructionsUrl,
      'setup_instructions_file_path': setupInstructionsFilePath,
      'auth_steps': authSteps.map((e) => e.toJson()).toList(),
      'actions': actions?.map((e) => e.toJson()).toList(),
      'chat_tools_manifest_url': chatToolsManifestUrl,
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
  List<String> connectedAccounts = [];
  Map? twitter;
  bool private;
  bool approved;
  String? conversationPrompt;
  String? chatPrompt;
  ExternalIntegration? externalIntegration;
  ProactiveNotification? proactiveNotification;
  List<AppReview> reviews;
  AppReview? userReview;
  double? ratingAvg;
  int ratingCount;
  int installs;
  bool enabled;
  bool deleted;
  int? usageCount;
  double? moneyMade;
  bool isPaid;
  String? paymentPlan;
  double? price;
  bool isUserPaid;
  String? paymentLink;
  List<String> thumbnailIds;
  List<String> thumbnailUrls;
  String? username;
  bool? isPopular;
  List<ChatTool>? chatTools;
  DateTime? createdAt;
  DateTime? updatedAt;
  double? score; // Computed ranking score for sorting (temporary debug field)

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
    this.conversationPrompt,
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
    this.proactiveNotification,
    this.usageCount,
    this.moneyMade,
    required this.isPaid,
    this.paymentPlan,
    this.price,
    required this.isUserPaid,
    this.paymentLink,
    this.thumbnailIds = const [],
    this.thumbnailUrls = const [],
    this.username,
    this.connectedAccounts = const [],
    this.twitter,
    this.isPopular = false,
    this.chatTools,
    this.createdAt,
    this.updatedAt,
    this.score,
  });

  String getName() {
    return tryDecodingText(name);
  }

  String? getRatingAvg() => ratingAvg?.toStringAsFixed(1);

  bool hasCapability(String capability) => capabilities.contains(capability);

  bool worksWithMemories() => hasCapability('memories');

  bool worksWithChat() => hasCapability('chat') || hasCapability('persona');

  bool isNotPersona() => !hasCapability('persona');

  bool worksExternally() => hasCapability('external_integration');

  bool hasConversationsAccess() {
    if (worksExternally()) {
      final actions = externalIntegration?.actions;
      if (actions != null) {
        return actions.any((a) => a.action == 'create_conversation' || a.action == 'read_conversations');
      }
    }
    return false;
  }

  bool hasMemoriesAccess() {
    if (worksExternally()) {
      final actions = externalIntegration?.actions;
      if (actions != null) {
        return actions.any((a) => a.action == 'create_facts' || a.action == 'read_memories');
      }
    }
    return false;
  }

  bool hasTasksAccess() {
  if (worksExternally()) {
    final actions = externalIntegration?.actions;
    if (actions != null) {
      return actions.any((a) => a.action == 'read_tasks');
    }
  }
  return false;
}

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
      conversationPrompt: json['memory_prompt'],
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
      proactiveNotification: json['proactive_notification'] != null
          ? ProactiveNotification.fromJson(json['proactive_notification'])
          : null,
      usageCount: json['usage_count'] ?? 0,
      moneyMade: json['money_made'] ?? 0.0,
      isPaid: json['is_paid'] ?? false,
      paymentPlan: json['payment_plan'],
      price: json['price'] ?? 0.0,
      isUserPaid: json['is_user_paid'] ?? false,
      paymentLink: json['payment_link'],
      thumbnailIds: (json['thumbnails'] as List<dynamic>?)?.cast<String>() ?? [],
      thumbnailUrls: (json['thumbnail_urls'] as List<dynamic>?)?.cast<String>() ?? [],
      username: json['username'],
      connectedAccounts: (json['connected_accounts'] as List<dynamic>?)?.cast<String>() ?? [],
      twitter: json['twitter'],
      isPopular: json['is_popular'] ?? false,
      chatTools: ChatTool.fromJsonList(json['chat_tools']),
      createdAt: json['created_at'] != null ? DateTime.parse(json['created_at']).toLocal() : null,
      updatedAt: json['updated_at'] != null ? DateTime.parse(json['updated_at']).toLocal() : null,
      score: json['score']?.toDouble(),
    );
  }

  String getFormattedPrice() {
    if (price == null) {
      return 'Free';
    }
    if (paymentPlan == 'monthly_recurring') {
      return '\$${price!} per month';
    } else {
      return '\$${price!}';
    }
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

  /// Returns the most recent date (updated_at preferred, falls back to created_at)
  DateTime? getLastUpdatedDate() {
    return updatedAt ?? createdAt;
  }

  List<AppCapability> getCapabilitiesFromIds(List<AppCapability> allCapabilities) {
    return allCapabilities.where((e) => capabilities.contains(e.id)).toList();
  }

  List<String> getConnectedAccountNames() {
    return connectedAccounts.map((e) => e.capitalize()).toList();
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'author': author,
      'description': description,
      'image': image,
      'capabilities': capabilities.toList(),
      'memory_prompt': conversationPrompt,
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
      'proactive_notification': proactiveNotification?.toJson(),
      'usage_count': usageCount,
      'money_made': moneyMade,
      'is_paid': isPaid,
      'payment_plan': paymentPlan,
      'price': price,
      'is_user_paid': isUserPaid,
      'payment_link': paymentLink,
    };
  }

  static List<App> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => App.fromJson(e)).toList();

  List<NotificationScope> getNotificationScopesFromIds(List<NotificationScope> allScopes) {
    if (proactiveNotification == null) {
      return [];
    }
    return allScopes.where((e) => proactiveNotification!.scopes.contains(e.id)).toList();
  }
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
  List<CapacityAction> actions = [];

  AppCapability({
    required this.title,
    required this.id,
    this.triggerEvents = const [],
    this.notificationScopes = const [],
    this.actions = const [],
  });

  factory AppCapability.fromJson(Map<String, dynamic> json) {
    return AppCapability(
      title: json['title'],
      id: json['id'],
      triggerEvents: TriggerEvent.fromJsonList(json['triggers'] ?? []),
      notificationScopes: NotificationScope.fromJsonList(json['scopes'] ?? []),
      actions: CapacityAction.fromJsonList(json['actions'] ?? []),
    );
  }

  toJson() {
    return {
      'title': title,
      'id': id,
      'triggers': triggerEvents.map((e) => e.toJson()).toList(),
      'scopes': notificationScopes.map((e) => e.toJson()).toList(),
      'actions': actions.map((e) => e.toJson()).toList(),
    };
  }

  static List<AppCapability> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => AppCapability.fromJson(e)).toList();
  }

  bool hasTriggers() => triggerEvents.isNotEmpty;
  bool hasScopes() => notificationScopes.isNotEmpty;
  bool hasActions() => actions.isNotEmpty;
}

class CapacityAction {
  String title;
  String id;
  String? docUrl;
  String? description;

  CapacityAction({
    required this.title,
    required this.id,
    this.docUrl,
    this.description,
  });

  factory CapacityAction.fromJson(Map<String, dynamic> json) {
    return CapacityAction(
      title: json['title'],
      id: json['id'],
      docUrl: json['doc_url'],
      description: json['description'],
    );
  }

  toJson() {
    return {
      'title': title,
      'id': id,
      'doc_url': docUrl,
      'description': description,
    };
  }

  static List<CapacityAction> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => CapacityAction.fromJson(e)).toList();
  }
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

class ProactiveNotification {
  List<String> scopes;

  ProactiveNotification({
    required this.scopes,
  });

  factory ProactiveNotification.fromJson(Map<String, dynamic> json) {
    return ProactiveNotification(
      scopes: json['scopes'].map<String>((e) => e.toString()).toList(),
    );
  }

  toJson() {
    return {
      'scopes': scopes,
    };
  }
}

class PaymentPlan {
  final String title;
  final String id;

  PaymentPlan({
    required this.title,
    required this.id,
  });

  factory PaymentPlan.fromJson(Map<String, dynamic> json) {
    return PaymentPlan(
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

  static List<PaymentPlan> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => PaymentPlan.fromJson(e)).toList();
  }
}

class AppApiKey {
  final String id;
  final String label;
  final DateTime createdAt;
  String? secret; // Only available when first created

  AppApiKey({
    required this.id,
    required this.label,
    required this.createdAt,
    this.secret,
  });

  factory AppApiKey.fromJson(Map<String, dynamic> json) {
    return AppApiKey(
      id: json['id'],
      label: json['label'] ?? 'API Key',
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      secret: json['secret'],
    );
  }

  toJson() {
    return {
      'id': id,
      'label': label,
      'created_at': createdAt.toUtc().toIso8601String(),
      if (secret != null) 'secret': secret,
    };
  }

  static List<AppApiKey> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => AppApiKey.fromJson(e)).toList();
  }
}
