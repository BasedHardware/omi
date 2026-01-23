import 'package:json_annotation/json_annotation.dart';

part 'announcement.g.dart';

enum AnnouncementType {
  changelog,
  feature,
  announcement,
}

// Changelog content models
@JsonSerializable(fieldRename: FieldRename.snake)
class ChangelogItem {
  final String title;
  final String description;
  final String? icon;

  ChangelogItem({
    required this.title,
    required this.description,
    this.icon,
  });

  factory ChangelogItem.fromJson(Map<String, dynamic> json) => _$ChangelogItemFromJson(json);
  Map<String, dynamic> toJson() => _$ChangelogItemToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake, explicitToJson: true)
class ChangelogContent {
  final String title;
  final List<ChangelogItem> changes;

  ChangelogContent({
    required this.title,
    required this.changes,
  });

  factory ChangelogContent.fromJson(Map<String, dynamic> json) => _$ChangelogContentFromJson(json);
  Map<String, dynamic> toJson() => _$ChangelogContentToJson(this);
}

// Feature content models
@JsonSerializable(fieldRename: FieldRename.snake)
class FeatureStep {
  final String title;
  final String description;
  final String? imageUrl;
  final String? videoUrl;
  final String? highlightText;

  FeatureStep({
    required this.title,
    required this.description,
    this.imageUrl,
    this.videoUrl,
    this.highlightText,
  });

  factory FeatureStep.fromJson(Map<String, dynamic> json) => _$FeatureStepFromJson(json);
  Map<String, dynamic> toJson() => _$FeatureStepToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake, explicitToJson: true)
class FeatureContent {
  final String title;
  final List<FeatureStep> steps;

  FeatureContent({
    required this.title,
    required this.steps,
  });

  factory FeatureContent.fromJson(Map<String, dynamic> json) => _$FeatureContentFromJson(json);
  Map<String, dynamic> toJson() => _$FeatureContentToJson(this);
}

// Announcement content models
@JsonSerializable(fieldRename: FieldRename.snake)
class AnnouncementCTA {
  final String text;
  final String action;

  AnnouncementCTA({
    required this.text,
    required this.action,
  });

  factory AnnouncementCTA.fromJson(Map<String, dynamic> json) => _$AnnouncementCTAFromJson(json);
  Map<String, dynamic> toJson() => _$AnnouncementCTAToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake, explicitToJson: true)
class AnnouncementContent {
  final String title;
  final String body;
  final String? imageUrl;
  final AnnouncementCTA? cta;

  AnnouncementContent({
    required this.title,
    required this.body,
    this.imageUrl,
    this.cta,
  });

  factory AnnouncementContent.fromJson(Map<String, dynamic> json) => _$AnnouncementContentFromJson(json);
  Map<String, dynamic> toJson() => _$AnnouncementContentToJson(this);
}

// Main announcement model
@JsonSerializable(fieldRename: FieldRename.snake)
class Announcement {
  final String id;
  final AnnouncementType type;
  final DateTime createdAt;
  @JsonKey(defaultValue: true)
  final bool active;

  // Version triggers
  final String? appVersion;
  final String? firmwareVersion;
  @JsonKey(defaultValue: [])
  final List<String>? deviceModels;

  // For general announcements
  final DateTime? expiresAt;

  // Raw content - parsed based on type
  final Map<String, dynamic> content;

  Announcement({
    required this.id,
    required this.type,
    required this.createdAt,
    this.active = true,
    this.appVersion,
    this.firmwareVersion,
    this.deviceModels,
    this.expiresAt,
    required this.content,
  });

  factory Announcement.fromJson(Map<String, dynamic> json) => _$AnnouncementFromJson(json);
  Map<String, dynamic> toJson() => _$AnnouncementToJson(this);

  // Type-specific content getters
  ChangelogContent get changelogContent => ChangelogContent.fromJson(content);
  FeatureContent get featureContent => FeatureContent.fromJson(content);
  AnnouncementContent get announcementContent => AnnouncementContent.fromJson(content);
}
