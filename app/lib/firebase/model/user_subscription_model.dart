// To parse this JSON data, do
//
//     final userSubscriptionModel = userSubscriptionModelFromJson(jsonString);

import 'dart:convert';

UserSubscriptionModel userSubscriptionModelFromJson(String str) => UserSubscriptionModel.fromJson(json.decode(str));

String userSubscriptionModelToJson(UserSubscriptionModel data) => json.encode(data.toJson());

class UserSubscriptionModel {
  String? userId;
  String? pluginId;
  String? transactionId;
  String? purchaseId;
  String? productId;
  bool? isPremium;
  String? platform;
  DateTime? startDate;
  DateTime? expiryDate;
  DateTime? createdDate;
  DateTime? updatedDate;

  UserSubscriptionModel({
    this.userId,
    this.pluginId,
    this.transactionId,
    this.purchaseId,
    this.productId,
    this.isPremium,
    this.platform,
    this.startDate,
    this.expiryDate,
    this.createdDate,
    this.updatedDate,
  });

  factory UserSubscriptionModel.fromJson(Map<String, dynamic> json) => UserSubscriptionModel(
    userId: json["user_id"],
    pluginId: json["plugin_id"],
    transactionId: json["transaction_id"],
    purchaseId: json["purchase_id"],
    productId: json["product_id"],
    isPremium: json["is_premium"],
    platform: json["platform"],
    startDate: json["start_date"] == null ? null : DateTime.parse(json["start_date"]),
    expiryDate: json["expiry_date"] == null ? null : DateTime.parse(json["expiry_date"]),
    createdDate: json["created_date"] == null ? null : DateTime.parse(json["created_date"]),
    updatedDate: json["updated_date"] == null ? null : DateTime.parse(json["updated_date"]),
  );

  Map<String, dynamic> toJson() => {
    "user_id": userId,
    "plugin_id": pluginId,
    "transaction_id": transactionId,
    "purchase_id": purchaseId,
    "product_id": productId,
    "is_premium": isPremium,
    "platform": platform,
    "start_date": startDate?.toIso8601String(),
    "expiry_date": expiryDate?.toIso8601String(),
    "created_date": createdDate?.toIso8601String(),
    "updated_date": updatedDate?.toIso8601String(),
  };
}
