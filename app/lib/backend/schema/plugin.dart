import 'dart:convert';

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
      'https://raw.githubusercontent.com/maxwell882000/shopify-components/main$image';

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

/// Subscription model

// To parse this JSON data, do
//
//     final productSubscription = productSubscriptionFromJson(jsonString);

ProductSubscription productSubscriptionFromJson(String str) => ProductSubscription.fromJson(json.decode(str));

String productSubscriptionToJson(ProductSubscription data) => json.encode(data.toJson());

class ProductSubscription {
  List<Product>? products;

  ProductSubscription({
    this.products,
  });

  factory ProductSubscription.fromJson(Map<String, dynamic> json) => ProductSubscription(
    products: json["products"] == null ? [] : List<Product>.from(json["products"]!.map((x) => Product.fromJson(x))),
  );

  Map<String, dynamic> toJson() => {
    "products": products == null ? [] : List<dynamic>.from(products!.map((x) => x.toJson())),
  };
}

class Product {
  dynamic collectionId;
  DateTime? createdAt;
  double? discountAmount;
  String? discountType;
  String? handle;
  int? id;
  Images? images;
  int? productId;
  int? shopifyProductId;
  SubscriptionDefaults? subscriptionDefaults;
  String? title;
  DateTime? updatedAt;

  Product({
    this.collectionId,
    this.createdAt,
    this.discountAmount,
    this.discountType,
    this.handle,
    this.id,
    this.images,
    this.productId,
    this.shopifyProductId,
    this.subscriptionDefaults,
    this.title,
    this.updatedAt,
  });

  factory Product.fromJson(Map<String, dynamic> json) => Product(
    collectionId: json["collection_id"],
    createdAt: json["created_at"] == null ? null : DateTime.parse(json["created_at"]),
    discountAmount: json["discount_amount"] == null ? 0.0 : json["discount_amount"].toDouble(),
    discountType: json["discount_type"],
    handle: json["handle"],
    id: json["id"],
    images: json["images"] == null ? null : Images.fromJson(json["images"]),
    productId: json["product_id"],
    shopifyProductId: json["shopify_product_id"],
    subscriptionDefaults: json["subscription_defaults"] == null ? null : SubscriptionDefaults.fromJson(json["subscription_defaults"]),
    title: json["title"],
    updatedAt: json["updated_at"] == null ? null : DateTime.parse(json["updated_at"]),
  );

  Map<String, dynamic> toJson() => {
    "collection_id": collectionId,
    "created_at": createdAt?.toIso8601String(),
    "discount_amount": discountAmount,
    "discount_type": discountType,
    "handle": handle,
    "id": id,
    "images": images?.toJson(),
    "product_id": productId,
    "shopify_product_id": shopifyProductId,
    "subscription_defaults": subscriptionDefaults?.toJson(),
    "title": title,
    "updated_at": updatedAt?.toIso8601String(),
  };
}

class Images {
  String? large;
  String? medium;
  String? original;
  String? small;

  Images({
    this.large,
    this.medium,
    this.original,
    this.small,
  });

  factory Images.fromJson(Map<String, dynamic> json) => Images(
    large: json["large"],
    medium: json["medium"],
    original: json["original"],
    small: json["small"],
  );

  Map<String, dynamic> toJson() => {
    "large": large,
    "medium": medium,
    "original": original,
    "small": small,
  };
}

class SubscriptionDefaults {
  bool? applyCutoffDateToCheckout;
  int? chargeIntervalFrequency;
  dynamic cutoffDayOfMonth;
  dynamic cutoffDayOfWeek;
  dynamic expireAfterSpecificNumberOfCharges;
  List<dynamic>? modifiableProperties;
  dynamic numberChargesUntilExpiration;
  dynamic orderDayOfMonth;
  dynamic orderDayOfWeek;
  List<String>? orderIntervalFrequencyOptions;
  String? orderIntervalUnit;
  List<int>? planIds;
  String? storefrontPurchaseOptions;
  bool? usePlansData;

  SubscriptionDefaults({
    this.applyCutoffDateToCheckout,
    this.chargeIntervalFrequency,
    this.cutoffDayOfMonth,
    this.cutoffDayOfWeek,
    this.expireAfterSpecificNumberOfCharges,
    this.modifiableProperties,
    this.numberChargesUntilExpiration,
    this.orderDayOfMonth,
    this.orderDayOfWeek,
    this.orderIntervalFrequencyOptions,
    this.orderIntervalUnit,
    this.planIds,
    this.storefrontPurchaseOptions,
    this.usePlansData,
  });

  factory SubscriptionDefaults.fromJson(Map<String, dynamic> json) => SubscriptionDefaults(
    applyCutoffDateToCheckout: json["apply_cutoff_date_to_checkout"],
    chargeIntervalFrequency: json["charge_interval_frequency"],
    cutoffDayOfMonth: json["cutoff_day_of_month"],
    cutoffDayOfWeek: json["cutoff_day_of_week"],
    expireAfterSpecificNumberOfCharges: json["expire_after_specific_number_of_charges"],
    modifiableProperties: json["modifiable_properties"] == null ? [] : List<dynamic>.from(json["modifiable_properties"]!.map((x) => x)),
    numberChargesUntilExpiration: json["number_charges_until_expiration"],
    orderDayOfMonth: json["order_day_of_month"],
    orderDayOfWeek: json["order_day_of_week"],
    orderIntervalFrequencyOptions: json["order_interval_frequency_options"] == null ? [] : List<String>.from(json["order_interval_frequency_options"]!.map((x) => x)),
    orderIntervalUnit: json["order_interval_unit"],
    planIds: json["plan_ids"] == null ? [] : List<int>.from(json["plan_ids"]!.map((x) => x)),
    storefrontPurchaseOptions: json["storefront_purchase_options"],
    usePlansData: json["use_plans_data"],
  );

  Map<String, dynamic> toJson() => {
    "apply_cutoff_date_to_checkout": applyCutoffDateToCheckout,
    "charge_interval_frequency": chargeIntervalFrequency,
    "cutoff_day_of_month": cutoffDayOfMonth,
    "cutoff_day_of_week": cutoffDayOfWeek,
    "expire_after_specific_number_of_charges": expireAfterSpecificNumberOfCharges,
    "modifiable_properties": modifiableProperties == null ? [] : List<dynamic>.from(modifiableProperties!.map((x) => x)),
    "number_charges_until_expiration": numberChargesUntilExpiration,
    "order_day_of_month": orderDayOfMonth,
    "order_day_of_week": orderDayOfWeek,
    "order_interval_frequency_options": orderIntervalFrequencyOptions == null ? [] : List<dynamic>.from(orderIntervalFrequencyOptions!.map((x) => x)),
    "order_interval_unit": orderIntervalUnit,
    "plan_ids": planIds == null ? [] : List<dynamic>.from(planIds!.map((x) => x)),
    "storefront_purchase_options": storefrontPurchaseOptions,
    "use_plans_data": usePlansData,
  };
}
