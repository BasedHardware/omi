import 'package:omi/backend/schema/gen/announcements_wire.g.dart' as wire;

enum AnnouncementType { changelog, feature, announcement }

enum TriggerType { immediate, versionUpgrade, firmwareUpgrade }

String _triggerTypeToWire(TriggerType trigger) {
  switch (trigger) {
    case TriggerType.immediate:
      return 'immediate';
    case TriggerType.versionUpgrade:
      return 'version_upgrade';
    case TriggerType.firmwareUpgrade:
      return 'firmware_upgrade';
  }
}

TriggerType _triggerTypeFromWire(String? trigger) {
  switch (trigger) {
    case 'immediate':
      return TriggerType.immediate;
    case 'firmware_upgrade':
      return TriggerType.firmwareUpgrade;
    case 'version_upgrade':
      return TriggerType.versionUpgrade;
    default:
      throw FormatException('Unknown announcement trigger: $trigger');
  }
}

String _announcementTypeToWire(AnnouncementType type) => type.name;

AnnouncementType _announcementTypeFromWire(String type) {
  final announcementType = AnnouncementType.values.asNameMap()[type];
  if (announcementType == null) {
    throw FormatException('Unknown announcement type: $type');
  }
  return announcementType;
}

class Targeting {
  final String? appVersionMin;
  final String? appVersionMax;
  final String? firmwareVersionMin;
  final String? firmwareVersionMax;
  final List<String>? deviceModels;
  final List<String>? platforms;
  final TriggerType trigger;
  final List<String>? testUids;

  Targeting({
    this.appVersionMin,
    this.appVersionMax,
    this.firmwareVersionMin,
    this.firmwareVersionMax,
    this.deviceModels,
    this.platforms,
    this.trigger = TriggerType.versionUpgrade,
    this.testUids,
  });

  factory Targeting.fromJson(Map<String, dynamic> json) {
    return Targeting.fromGenerated(wire.GeneratedTargeting.fromJson(json));
  }

  factory Targeting.fromGenerated(wire.GeneratedTargeting generated) {
    return Targeting(
      appVersionMin: generated.appVersionMin,
      appVersionMax: generated.appVersionMax,
      firmwareVersionMin: generated.firmwareVersionMin,
      firmwareVersionMax: generated.firmwareVersionMax,
      deviceModels: generated.deviceModels ?? const [],
      platforms: generated.platforms ?? const [],
      trigger: _triggerTypeFromWire(generated.trigger),
      testUids: generated.testUids,
    );
  }

  wire.GeneratedTargeting toGenerated() {
    return wire.GeneratedTargeting(
      appVersionMin: appVersionMin,
      appVersionMax: appVersionMax,
      firmwareVersionMin: firmwareVersionMin,
      firmwareVersionMax: firmwareVersionMax,
      deviceModels: deviceModels,
      platforms: platforms,
      trigger: _triggerTypeToWire(trigger),
      testUids: testUids,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

// Display model for controlling announcement presentation
class Display {
  final int priority;
  final DateTime? startAt;
  final DateTime? expiresAt;
  final bool dismissible;
  final bool showOnce;

  Display({this.priority = 0, this.startAt, this.expiresAt, this.dismissible = true, this.showOnce = true});

  factory Display.fromJson(Map<String, dynamic> json) {
    return Display.fromGenerated(wire.GeneratedDisplay.fromJson(json));
  }

  factory Display.fromGenerated(wire.GeneratedDisplay generated) {
    return Display(
      priority: generated.priority,
      startAt: generated.startAt,
      expiresAt: generated.expiresAt,
      dismissible: generated.dismissible,
      showOnce: generated.showOnce,
    );
  }

  wire.GeneratedDisplay toGenerated() {
    return wire.GeneratedDisplay(
      priority: priority,
      startAt: startAt,
      expiresAt: expiresAt,
      dismissible: dismissible,
      showOnce: showOnce,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

// Changelog content models
class ChangelogItem {
  final String title;
  final String description;
  final String? icon;

  ChangelogItem({required this.title, required this.description, this.icon});

  factory ChangelogItem.fromJson(Map<String, dynamic> json) {
    return ChangelogItem(
      title: json['title'] as String,
      description: json['description'] as String,
      icon: json['icon'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {'title': title, 'description': description, 'icon': icon};
}

class ChangelogContent {
  final String title;
  final List<ChangelogItem> changes;

  ChangelogContent({required this.title, required this.changes});

  factory ChangelogContent.fromJson(Map<String, dynamic> json) {
    return ChangelogContent(
      title: json['title'] as String,
      changes: (json['changes'] as List<dynamic>)
          .map((item) => ChangelogItem.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {'title': title, 'changes': changes.map((item) => item.toJson()).toList()};
}

// Feature content models
class FeatureStep {
  final String title;
  final String description;
  final String? imageUrl;
  final String? videoUrl;
  final String? highlightText;

  FeatureStep({required this.title, required this.description, this.imageUrl, this.videoUrl, this.highlightText});

  factory FeatureStep.fromJson(Map<String, dynamic> json) {
    return FeatureStep(
      title: json['title'] as String,
      description: json['description'] as String,
      imageUrl: json['image_url'] as String?,
      videoUrl: json['video_url'] as String?,
      highlightText: json['highlight_text'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'description': description,
      'image_url': imageUrl,
      'video_url': videoUrl,
      'highlight_text': highlightText,
    };
  }
}

class FeatureContent {
  final String title;
  final List<FeatureStep> steps;

  FeatureContent({required this.title, required this.steps});

  factory FeatureContent.fromJson(Map<String, dynamic> json) {
    return FeatureContent(
      title: json['title'] as String,
      steps:
          (json['steps'] as List<dynamic>).map((item) => FeatureStep.fromJson(item as Map<String, dynamic>)).toList(),
    );
  }

  Map<String, dynamic> toJson() => {'title': title, 'steps': steps.map((step) => step.toJson()).toList()};
}

// Announcement content models
class AnnouncementCTA {
  final String text;
  final String action;

  AnnouncementCTA({required this.text, required this.action});

  factory AnnouncementCTA.fromJson(Map<String, dynamic> json) {
    return AnnouncementCTA(text: json['text'] as String, action: json['action'] as String);
  }

  Map<String, dynamic> toJson() => {'text': text, 'action': action};
}

class AnnouncementContent {
  final String title;
  final String body;
  final String? imageUrl;
  final AnnouncementCTA? cta;

  AnnouncementContent({required this.title, required this.body, this.imageUrl, this.cta});

  factory AnnouncementContent.fromJson(Map<String, dynamic> json) {
    return AnnouncementContent(
      title: json['title'] as String,
      body: json['body'] as String,
      imageUrl: json['image_url'] as String?,
      cta: json['cta'] == null ? null : AnnouncementCTA.fromJson(json['cta'] as Map<String, dynamic>),
    );
  }

  Map<String, dynamic> toJson() => {'title': title, 'body': body, 'image_url': imageUrl, 'cta': cta?.toJson()};
}

// Main announcement model
class Announcement {
  final String id;
  final AnnouncementType type;
  final DateTime createdAt;
  final bool active;

  // Version fields (used by /changelogs endpoint)
  final String? appVersion;
  final String? firmwareVersion;
  final List<String>? deviceModels;
  final DateTime? expiresAt;

  // Flexible targeting and display options
  final Targeting? targeting;
  final Display? display;

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
    this.targeting,
    this.display,
    required this.content,
  });

  factory Announcement.fromJson(Map<String, dynamic> json) {
    return Announcement.fromGenerated(wire.GeneratedAnnouncement.fromJson(json));
  }

  factory Announcement.fromGenerated(wire.GeneratedAnnouncement generated) {
    return Announcement(
      id: generated.id,
      type: _announcementTypeFromWire(generated.type),
      createdAt: generated.createdAt,
      active: generated.active,
      appVersion: generated.appVersion,
      firmwareVersion: generated.firmwareVersion,
      deviceModels: generated.deviceModels,
      expiresAt: generated.expiresAt,
      targeting: generated.targeting == null ? null : Targeting.fromGenerated(generated.targeting!),
      display: generated.display == null ? null : Display.fromGenerated(generated.display!),
      content: generated.content,
    );
  }

  wire.GeneratedAnnouncement toGenerated() {
    return wire.GeneratedAnnouncement(
      id: id,
      type: _announcementTypeToWire(type),
      createdAt: createdAt,
      active: active,
      appVersion: appVersion,
      firmwareVersion: firmwareVersion,
      deviceModels: deviceModels,
      expiresAt: expiresAt,
      targeting: targeting?.toGenerated(),
      display: display?.toGenerated(),
      content: content,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();

  // Type-specific content getters
  ChangelogContent get changelogContent => ChangelogContent.fromJson(content);
  FeatureContent get featureContent => FeatureContent.fromJson(content);
  AnnouncementContent get announcementContent => AnnouncementContent.fromJson(content);

  // Get effective display priority (defaults to 0)
  int get effectivePriority => display?.priority ?? 0;

  // Get effective trigger type
  TriggerType get effectiveTrigger => targeting?.trigger ?? TriggerType.versionUpgrade;
}
