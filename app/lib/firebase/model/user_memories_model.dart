import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';

List<UserMemoriesModel> userMemoriesModelListFromJson(String str) =>
    List<UserMemoriesModel>.from(
        json.decode(str).map((x) => UserMemoriesModel.fromJson(x)));

String userMemoriesModelListToJson(List<UserMemoriesModel> data) =>
    json.encode(List<dynamic>.from(data.map((x) => x.toJson())));

UserMemoriesModel userMemoriesModelFromJson(String str) =>
    UserMemoriesModel.fromJson(json.decode(str));

String userMemoriesModelToJson(UserMemoriesModel data) =>
    json.encode(data.toJson());

class UserMemoriesModel {
  bool? discarded;
  List<TranscriptSegment>? transcriptSegments;
  DateTime? finishedAt;
  List<PluginsResult>? pluginsResults;
  DateTime? createdAt;
  String? language;
  String? source;
  bool? deleted;
  DateTime? startedAt;
  Structured? structured;
  String? id;
  String? refId;

  UserMemoriesModel({
    this.discarded,
    this.transcriptSegments,
    this.finishedAt,
    this.pluginsResults,
    this.createdAt,
    this.language,
    this.source,
    this.deleted,
    this.startedAt,
    this.structured,
    this.id,
  });

  factory UserMemoriesModel.fromJson(Map<String, dynamic> json) =>
      UserMemoriesModel(
        discarded: json["discarded"],
        transcriptSegments: json["transcript_segments"] == null
            ? []
            : List<TranscriptSegment>.from(json["transcript_segments"]!
                .map((x) => TranscriptSegment.fromJson(x))),
        finishedAt: json["finished_at"] != null
            ? (json["finished_at"] is String)
                ? (json["finished_at"] != "")
                    ? DateTime.parse(json["finished_at"])
                    : null
                : json["finished_at"].toDate()
            : null,
        pluginsResults: json["plugins_results"] == null
            ? []
            : List<PluginsResult>.from(
                json["plugins_results"]!.map((x) => PluginsResult.fromJson(x))),
        createdAt: json["created_at"] != null
            ? (json["created_at"] is String)
                ? (json["created_at"] != "")
                    ? DateTime.parse(json["created_at"])
                    : null
                : json["created_at"].toDate()
            : null,
        language: json["language"],
        source: json["source"],
        deleted: json["deleted"],
        startedAt: json["started_at"] != null
            ? (json["started_at"] is String)
                ? (json["started_at"] != "")
                    ? DateTime.parse(json["started_at"])
                    : null
                : json["started_at"].toDate()
            : null,
        structured: json["structured"] == null
            ? null
            : Structured.fromJson(json["structured"]),
        id: json["id"],
      );

  Map<String, dynamic> toJson() => {
        "discarded": discarded,
        "transcript_segments": transcriptSegments == null
            ? []
            : List<dynamic>.from(transcriptSegments!.map((x) => x.toJson())),
        "finished_at": finishedAt!.toIso8601String(),
        "plugins_results": pluginsResults == null
            ? []
            : List<dynamic>.from(pluginsResults!.map((x) => x.toJson())),
        "created_at": createdAt!.toIso8601String(),
        "language": language,
        "source": source,
        "deleted": deleted,
        "started_at": startedAt!.toIso8601String(),
        "structured": structured?.toJson(),
        "id": id,
      };

  Map<String, dynamic> toJsonTimeStamp() => {
        "discarded": discarded,
        "transcript_segments": transcriptSegments == null
            ? []
            : List<dynamic>.from(transcriptSegments!.map((x) => x.toJson())),
        "finished_at": Timestamp.fromDate(finishedAt!),
        "plugins_results": pluginsResults == null
            ? []
            : List<dynamic>.from(pluginsResults!.map((x) => x.toJson())),
        "created_at": Timestamp.fromDate(createdAt!),
        "language": language,
        "source": source,
        "deleted": deleted,
        "started_at": Timestamp.fromDate(startedAt!),
        "structured": structured?.toJson(),
        "id": id,
      };
}

class PluginsResult {
  String? pluginId;
  String? content;
  DateTime? createdAt;
  bool isExpanded = false;
  bool isFavourite = false;

  PluginsResult({
    this.pluginId,
    this.content,
    this.createdAt,
  });

  factory PluginsResult.fromJson(Map<String, dynamic> json) => PluginsResult(
        pluginId: json["plugin_id"],
        content: json["content"],
        createdAt: json["created_at"] != null
            ? (json["created_at"] is String)
                ? (json["created_at"] != "")
                    ? DateTime.parse(json["created_at"])
                    : null
                : json["created_at"].toDate()
            : null,
      );

  Map<String, dynamic> toJson() => {
        "plugin_id": pluginId,
        "content": content,
        "created_at": createdAt!.toIso8601String(),
      };

  Map<String, dynamic> toJsonTimeStamp() => {
        "plugin_id": pluginId,
        "content": content,
        "created_at": Timestamp.fromDate(createdAt!),
      };
}

class Structured {
  String? overview;
  String? emoji;
  List<ActionItem>? actionItems;
  String? category;
  String? title;
  List<dynamic>? events;

  Structured({
    this.overview,
    this.emoji,
    this.actionItems,
    this.category,
    this.title,
    this.events,
  });

  factory Structured.fromJson(Map<String, dynamic> json) => Structured(
        overview: json["overview"],
        emoji: json["emoji"],
        actionItems: json["action_items"] == null
            ? []
            : List<ActionItem>.from(
                json["action_items"]!.map((x) => ActionItem.fromJson(x))),
        category: json["category"],
        title: json["title"],
        events: json["events"] == null
            ? []
            : List<dynamic>.from(json["events"]!.map((x) => x)),
      );

  Map<String, dynamic> toJson() => {
        "overview": overview,
        "emoji": emoji,
        "action_items": actionItems == null
            ? []
            : List<dynamic>.from(actionItems!.map((x) => x.toJson())),
        "category": category,
        "title": title,
        "events":
            events == null ? [] : List<dynamic>.from(events!.map((x) => x)),
      };
}

class ActionItem {
  bool? completed;
  String? description;

  ActionItem({
    this.completed,
    this.description,
  });

  factory ActionItem.fromJson(Map<String, dynamic> json) => ActionItem(
        completed: json["completed"],
        description: json["description"],
      );

  Map<String, dynamic> toJson() => {
        "completed": completed,
        "description": description,
      };
}

class TranscriptSegment {
  String? speaker;
  int? speakerId;
  double? start;
  double? end;
  String? text;
  bool? isUser;

  TranscriptSegment({
    this.speaker,
    this.speakerId,
    this.start,
    this.end,
    this.text,
    this.isUser,
  });

  factory TranscriptSegment.fromJson(Map<String, dynamic> json) =>
      TranscriptSegment(
        speaker: json["speaker"],
        speakerId: json["speaker_id"],
        start: json["start"]?.toDouble(),
        end: json["end"]?.toDouble(),
        text: json["text"],
        isUser: json["is_user"],
      );

  Map<String, dynamic> toJson() => {
        "speaker": speaker,
        "speaker_id": speakerId,
        "start": start,
        "end": end,
        "text": text,
        "is_user": isUser,
      };
}
