import 'package:omi/backend/schema/gen/apps_wire.g.dart' as wire;
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
    return AppReview.fromGenerated(
      wire.GeneratedAppReview.fromJson(json),
      updatedAt: (json['updated_at'] == "" || json['updated_at'] == null)
          ? null
          : DateTime.parse(json['updated_at']).toLocal(),
    );
  }

  factory AppReview.fromGenerated(wire.GeneratedAppReview generated, {DateTime? updatedAt}) {
    return AppReview(
      uid: generated.uid,
      ratedAt: generated.ratedAt.toLocal(),
      score: generated.score,
      review: generated.review,
      username: generated.username ?? '',
      response: generated.response ?? '',
      updatedAt: updatedAt,
      respondedAt: generated.respondedAt?.toLocal(),
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

  AuthStep({required this.name, required this.url});

  factory AuthStep.fromJson(Map<String, dynamic> json) {
    return AuthStep.fromGenerated(wire.GeneratedAuthStep.fromJson(json));
  }

  factory AuthStep.fromGenerated(wire.GeneratedAuthStep generated) {
    return AuthStep(name: generated.name, url: generated.url);
  }

  toJson() {
    return {'name': name, 'url': url};
  }
}

class Action {
  String action;

  Action({required this.action});

  factory Action.fromJson(Map<String, dynamic> json) {
    return Action.fromGenerated(wire.GeneratedAction.fromJson(json));
  }

  factory Action.fromGenerated(wire.GeneratedAction generated) {
    return Action(action: generated.action);
  }

  toJson() {
    return {'action': action};
  }
}

class ChatTool {
  String name;
  String description;
  String endpoint;
  String method;
  bool authRequired;
  String? statusMessage;
  bool isMcp;

  ChatTool({
    required this.name,
    required this.description,
    required this.endpoint,
    this.method = 'POST',
    this.authRequired = true,
    this.statusMessage,
    this.isMcp = false,
  });

  factory ChatTool.fromJson(Map<String, dynamic> json) {
    return ChatTool.fromGenerated(wire.GeneratedChatTool.fromJson(json));
  }

  factory ChatTool.fromGenerated(wire.GeneratedChatTool generated) {
    return ChatTool(
      name: generated.name,
      description: generated.description,
      endpoint: generated.endpoint,
      method: generated.method,
      authRequired: generated.authRequired,
      statusMessage: generated.statusMessage,
      isMcp: generated.isMcp,
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
      'is_mcp': isMcp,
    };
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
  String? mcpServerUrl;

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
    this.mcpServerUrl,
  });

  factory ExternalIntegration.fromJson(Map<String, dynamic> json) {
    return ExternalIntegration.fromGenerated(
      wire.GeneratedExternalIntegration.fromJson(json),
      legacyIsInstructionsUrl: json.containsKey('is_instructions_url') ? null : false,
    );
  }

  factory ExternalIntegration.fromGenerated(
    wire.GeneratedExternalIntegration generated, {
    bool? legacyIsInstructionsUrl,
  }) {
    return ExternalIntegration(
      triggersOn: generated.triggersOn,
      webhookUrl: generated.webhookUrl,
      setupCompletedUrl: generated.setupCompletedUrl,
      appHomeUrl: generated.appHomeUrl,
      isInstructionsUrl: legacyIsInstructionsUrl ?? generated.isInstructionsUrl,
      setupInstructionsFilePath: generated.setupInstructionsFilePath,
      authSteps: (generated.authSteps ?? const []).map(AuthStep.fromGenerated).toList(),
      actions: generated.actions?.map(Action.fromGenerated).toList(),
      chatToolsManifestUrl: generated.chatToolsManifestUrl,
      mcpServerUrl: generated.mcpServerUrl,
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
      if (mcpServerUrl != null) 'mcp_server_url': mcpServerUrl,
    };
  }
}

class AppUsageHistory {
  DateTime date;
  int count;

  AppUsageHistory({required this.date, required this.count});

  factory AppUsageHistory.fromJson(Map<String, dynamic> json) {
    return AppUsageHistory(date: DateTime.parse(json['date']).toLocal(), count: json['count']);
  }

  toJson() {
    return {'date': date.toUtc().toIso8601String(), 'count': count};
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
  bool official;
  String? sourceCodeUrl;

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
    this.isPopular = false,
    this.chatTools,
    this.createdAt,
    this.updatedAt,
    this.score,
    this.official = false,
    this.sourceCodeUrl,
  });

  String getName() {
    return tryDecodingText(name);
  }

  String? getRatingAvg() => ratingAvg?.toStringAsFixed(1);

  bool hasCapability(String capability) => capabilities.contains(capability);

  bool worksWithMemories() => hasCapability('memories');

  bool worksWithChat() => hasCapability('chat');

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
    return App.fromGeneratedDetail(
      wire.GeneratedApp.fromJson(json),
      approvedFallback: json.containsKey('approved') ? null : true,
      privateFallback: json['private'] as bool? ?? json['id'].toString().contains('private'),
    );
  }

  factory App.fromGeneratedDetail(
    wire.GeneratedApp generated, {
    bool? approvedFallback,
    bool? privateFallback,
  }) {
    return App(
      category: generated.category,
      approved: approvedFallback ?? generated.approved,
      status: generated.status,
      id: generated.id,
      email: generated.email ?? '',
      uid: generated.uid ?? '',
      name: generated.name,
      author: generated.author,
      description: generated.description,
      image: generated.image,
      externalIntegration: generated.externalIntegration == null
          ? null
          : ExternalIntegration.fromGenerated(generated.externalIntegration!),
      ratingAvg: generated.ratingAvg,
      ratingCount: generated.ratingCount,
      capabilities: generated.capabilities.toSet(),
      chatPrompt: generated.chatPrompt,
      conversationPrompt: generated.memoryPrompt,
      reviews: generated.reviews.map(AppReview.fromGenerated).toList(),
      userReview: generated.userReview == null ? null : AppReview.fromGenerated(generated.userReview!),
      deleted: false,
      enabled: generated.enabled,
      installs: generated.installs,
      private: privateFallback ?? generated.private,
      proactiveNotification: generated.proactiveNotification == null
          ? null
          : ProactiveNotification.fromGenerated(generated.proactiveNotification!),
      usageCount: generated.usageCount ?? 0,
      moneyMade: generated.moneyMade ?? 0.0,
      isPaid: generated.isPaid ?? false,
      paymentPlan: generated.paymentPlan,
      price: generated.price ?? 0.0,
      isUserPaid: generated.isUserPaid ?? false,
      paymentLink: generated.paymentLink,
      thumbnailIds: generated.thumbnails ?? [],
      thumbnailUrls: generated.thumbnailUrls ?? [],
      username: generated.username,
      isPopular: generated.isPopular ?? false,
      chatTools: (generated.chatTools ?? const []).map(ChatTool.fromGenerated).toList(),
      createdAt: generated.createdAt,
      updatedAt: null,
      score: generated.score,
      official: generated.official ?? false,
      sourceCodeUrl: generated.sourceCodeUrl,
    );
  }

  factory App.fromGenerated(
    wire.GeneratedAppBaseModel generated, {
    bool? approvedFallback,
    bool? privateFallback,
  }) {
    return App(
      category: generated.category,
      approved: approvedFallback ?? generated.approved,
      status: generated.status,
      id: generated.id,
      email: '',
      uid: generated.uid ?? '',
      name: generated.name,
      author: generated.author,
      description: generated.description,
      image: generated.image,
      externalIntegration: generated.externalIntegration == null
          ? null
          : ExternalIntegration.fromGenerated(generated.externalIntegration!),
      ratingAvg: generated.ratingAvg,
      ratingCount: generated.ratingCount,
      capabilities: generated.capabilities.toSet(),
      chatPrompt: null,
      conversationPrompt: null,
      reviews: [],
      userReview: null,
      deleted: false,
      enabled: generated.enabled,
      installs: generated.installs,
      private: privateFallback ?? generated.private,
      proactiveNotification: generated.proactiveNotification == null
          ? null
          : ProactiveNotification.fromGenerated(generated.proactiveNotification!),
      usageCount: 0,
      moneyMade: 0.0,
      isPaid: generated.isPaid ?? false,
      paymentPlan: generated.paymentPlan,
      price: generated.price ?? 0.0,
      isUserPaid: generated.isUserPaid ?? false,
      paymentLink: generated.paymentLink,
      thumbnailIds: generated.thumbnails ?? [],
      thumbnailUrls: generated.thumbnailUrls ?? [],
      username: generated.username,
      isPopular: generated.isPopular ?? false,
      chatTools: (generated.chatTools ?? const []).map(ChatTool.fromGenerated).toList(),
      createdAt: generated.createdAt,
      updatedAt: null,
      score: generated.score,
      official: generated.official ?? false,
      sourceCodeUrl: generated.sourceCodeUrl,
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
      'official': official,
      'source_code_url': sourceCodeUrl,
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
  Category({required this.title, required this.id});

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category.fromGenerated(wire.GeneratedAppSelectOption.fromJson(json));
  }

  factory Category.fromGenerated(wire.GeneratedAppSelectOption generated) {
    return Category(title: generated.title, id: generated.id);
  }

  toJson() {
    return {'title': title, 'id': id};
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
    return AppCapability.fromGenerated(wire.GeneratedAppCapabilityResponse.fromJson(json));
  }

  factory AppCapability.fromGenerated(wire.GeneratedAppCapabilityResponse generated) {
    return AppCapability(
      title: generated.title,
      id: generated.id,
      triggerEvents: (generated.triggers ?? const []).map(TriggerEvent.fromGenerated).toList(),
      notificationScopes: (generated.scopes ?? const []).map(NotificationScope.fromGenerated).toList(),
      actions: (generated.actions ?? const []).map(CapacityAction.fromGenerated).toList(),
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

  bool hasTriggers() => triggerEvents.isNotEmpty;
  bool hasScopes() => notificationScopes.isNotEmpty;
  bool hasActions() => actions.isNotEmpty;
}

class CapacityAction {
  String title;
  String id;
  String? docUrl;
  String? description;

  CapacityAction({required this.title, required this.id, this.docUrl, this.description});

  factory CapacityAction.fromJson(Map<String, dynamic> json) {
    return CapacityAction.fromGenerated(wire.GeneratedAppCapabilityAction.fromJson(json));
  }

  factory CapacityAction.fromGenerated(wire.GeneratedAppCapabilityAction generated) {
    return CapacityAction(
      title: generated.title,
      id: generated.id,
      docUrl: generated.docUrl,
      description: generated.description,
    );
  }

  toJson() {
    return {'title': title, 'id': id, 'doc_url': docUrl, 'description': description};
  }
}

class TriggerEvent {
  String title;
  String id;
  TriggerEvent({required this.title, required this.id});

  factory TriggerEvent.fromJson(Map<String, dynamic> json) {
    return TriggerEvent.fromGenerated(wire.GeneratedAppSelectOption.fromJson(json));
  }

  factory TriggerEvent.fromGenerated(wire.GeneratedAppSelectOption generated) {
    return TriggerEvent(title: generated.title, id: generated.id);
  }

  toJson() {
    return {'title': title, 'id': id};
  }
}

class NotificationScope {
  String title;
  String id;
  NotificationScope({required this.title, required this.id});

  factory NotificationScope.fromJson(Map<String, dynamic> json) {
    return NotificationScope.fromGenerated(wire.GeneratedAppSelectOption.fromJson(json));
  }

  factory NotificationScope.fromGenerated(wire.GeneratedAppSelectOption generated) {
    return NotificationScope(title: generated.title, id: generated.id);
  }

  toJson() {
    return {'title': title, 'id': id};
  }
}

class ProactiveNotification {
  List<String> scopes;

  ProactiveNotification({required this.scopes});

  factory ProactiveNotification.fromJson(Map<String, dynamic> json) {
    return ProactiveNotification.fromGenerated(wire.GeneratedProactiveNotification.fromJson(json));
  }

  factory ProactiveNotification.fromGenerated(wire.GeneratedProactiveNotification generated) {
    return ProactiveNotification(scopes: generated.scopes);
  }

  toJson() {
    return {'scopes': scopes};
  }
}

class PaymentPlan {
  final String title;
  final String id;

  PaymentPlan({required this.title, required this.id});

  factory PaymentPlan.fromJson(Map<String, dynamic> json) {
    return PaymentPlan.fromGenerated(wire.GeneratedAppSelectOption.fromJson(json));
  }

  factory PaymentPlan.fromGenerated(wire.GeneratedAppSelectOption generated) {
    return PaymentPlan(title: generated.title, id: generated.id);
  }

  toJson() {
    return {'title': title, 'id': id};
  }
}

class AppApiKey {
  final String id;
  final String label;
  final DateTime createdAt;
  String? secret; // Only available when first created

  AppApiKey({required this.id, required this.label, required this.createdAt, this.secret});

  factory AppApiKey.fromJson(Map<String, dynamic> json) {
    return AppApiKey.fromGenerated(wire.GeneratedAppApiKeyResponse.fromJson(json));
  }

  factory AppApiKey.fromGenerated(wire.GeneratedAppApiKeyResponse generated) {
    return AppApiKey(
      id: generated.id,
      label: generated.label,
      createdAt: generated.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0),
      secret: generated.secret,
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
}
