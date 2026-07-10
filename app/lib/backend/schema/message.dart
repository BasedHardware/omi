import 'package:collection/collection.dart';
import 'package:omi/backend/schema/gen/messages_wire.g.dart' as wire;
import 'package:uuid/uuid.dart';

enum MessageSender { ai, human }

enum MessageType {
  text('text'),
  daySummary('day_summary');

  final String value;

  const MessageType(this.value);

  static MessageType valuesFromString(String value) {
    return MessageType.values.firstWhereOrNull((e) => e.value == value) ?? MessageType.text;
  }
}

class MessageConversationStructured {
  String title;
  String emoji;

  MessageConversationStructured(this.title, this.emoji);

  static MessageConversationStructured fromJson(Map<String, dynamic> json) {
    return MessageConversationStructured.fromGenerated(wire.GeneratedMessageConversationStructured.fromJson(json));
  }

  factory MessageConversationStructured.fromGenerated(wire.GeneratedMessageConversationStructured generated) {
    return MessageConversationStructured(generated.title, generated.emoji);
  }

  wire.GeneratedMessageConversationStructured toGenerated() {
    return wire.GeneratedMessageConversationStructured(emoji: emoji, title: title);
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class MessageConversation {
  String id;
  DateTime createdAt;
  MessageConversationStructured structured;

  MessageConversation(this.id, this.createdAt, this.structured);

  static MessageConversation fromJson(Map<String, dynamic> json) {
    return MessageConversation.fromGenerated(wire.GeneratedMessageConversation.fromJson(json));
  }

  factory MessageConversation.fromGenerated(wire.GeneratedMessageConversation generated) {
    return MessageConversation(
      generated.id,
      generated.createdAt,
      MessageConversationStructured.fromGenerated(generated.structured),
    );
  }

  wire.GeneratedMessageConversation toGenerated() {
    return wire.GeneratedMessageConversation(createdAt: createdAt, id: id, structured: structured.toGenerated());
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class MessageFile {
  String id;
  String openaiFileId;
  String? thumbnail;
  String? thumbnailName;
  String name;
  String mimeType;
  DateTime createdAt;

  MessageFile(this.openaiFileId, this.thumbnail, this.name, this.mimeType, this.id, this.createdAt, this.thumbnailName);

  static MessageFile fromJson(Map<String, dynamic> json) {
    return MessageFile.fromGenerated(wire.GeneratedFileChat.fromJson(json));
  }

  factory MessageFile.fromGenerated(wire.GeneratedFileChat generated) {
    return MessageFile(
      generated.openaiFileId,
      generated.thumbnail,
      generated.name,
      generated.mimeType,
      generated.id,
      generated.createdAt,
      generated.thumbName,
    );
  }

  wire.GeneratedFileChat toGenerated() {
    return wire.GeneratedFileChat(
      createdAt: createdAt,
      id: id,
      mimeType: mimeType,
      name: name,
      openaiFileId: openaiFileId,
      thumbName: thumbnailName,
      thumbnail: thumbnail,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();

  String mimeTypeToFileType() {
    if (mimeType.contains('image')) {
      return 'image';
    } else {
      return 'file';
    }
  }
}

class ChartDataPoint {
  String label;
  double value;

  ChartDataPoint(this.label, this.value);

  static ChartDataPoint fromJson(Map<String, dynamic> json) {
    return ChartDataPoint.fromGenerated(wire.GeneratedChartDataPoint.fromJson(json));
  }

  factory ChartDataPoint.fromGenerated(wire.GeneratedChartDataPoint generated) {
    return ChartDataPoint(generated.label, generated.value);
  }

  wire.GeneratedChartDataPoint toGenerated() {
    return wire.GeneratedChartDataPoint(label: label, value: value);
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class ChartDataset {
  String label;
  List<ChartDataPoint> dataPoints;
  String? color;

  ChartDataset(this.label, this.dataPoints, {this.color});

  static ChartDataset fromJson(Map<String, dynamic> json) {
    return ChartDataset.fromGenerated(wire.GeneratedChartDataset.fromJson(json));
  }

  factory ChartDataset.fromGenerated(wire.GeneratedChartDataset generated) {
    return ChartDataset(
      generated.label,
      generated.dataPoints.map(ChartDataPoint.fromGenerated).toList(),
      color: generated.color,
    );
  }

  wire.GeneratedChartDataset toGenerated() {
    return wire.GeneratedChartDataset(
      color: color,
      dataPoints: dataPoints.map((p) => p.toGenerated()).toList(),
      label: label,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class ChartData {
  String chartType; // 'line' or 'bar'
  String title;
  String? xLabel;
  String? yLabel;
  List<ChartDataset> datasets;

  ChartData(this.chartType, this.title, this.datasets, {this.xLabel, this.yLabel});

  static ChartData? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    return ChartData.fromGenerated(wire.GeneratedChartData.fromJson(json));
  }

  static ChartData? tryFromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    if (!_hasTypedChartDataShape(json)) return null;
    try {
      return ChartData.fromJson(json);
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  static bool _hasTypedChartDataShape(Map<String, dynamic> json) {
    const requiredKeys = {'chart_type', 'title', 'datasets'};
    final chartType = json['chart_type'];
    return (chartType == 'line' || chartType == 'bar') && requiredKeys.every(json.containsKey);
  }

  factory ChartData.fromGenerated(wire.GeneratedChartData generated) {
    return ChartData(
      generated.chartType,
      generated.title,
      generated.datasets.map(ChartDataset.fromGenerated).toList(),
      xLabel: generated.xLabel,
      yLabel: generated.yLabel,
    );
  }

  wire.GeneratedChartData toGenerated() {
    return wire.GeneratedChartData(
      chartType: chartType,
      datasets: datasets.map((d) => d.toGenerated()).toList(),
      title: title,
      xLabel: xLabel,
      yLabel: yLabel,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class ServerMessage {
  String id;
  DateTime createdAt;
  String text;
  MessageSender sender;
  MessageType type;

  String? appId;
  bool fromIntegration;

  List<MessageFile> files;
  List filesId;

  List<MessageConversation> memories;
  bool askForNps;

  /// User rating for this message: 1 = thumbs up, -1 = thumbs down, null = no rating
  int? rating;

  List<String> thinkings = [];
  ChartData? chartData;
  Map<String, dynamic>? rawChartData;

  ServerMessage(
    this.id,
    this.createdAt,
    this.text,
    this.sender,
    this.type,
    this.appId,
    this.fromIntegration,
    this.files,
    this.filesId,
    this.memories, {
    this.askForNps = true,
    this.rating,
    this.chartData,
    this.rawChartData,
  });

  static ServerMessage fromJson(Map<String, dynamic> json) {
    return ServerMessage.fromGeneratedWireJson(json);
  }

  static ServerMessage fromGeneratedWireJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedMessage.fromJson(json);
    final fromIntegration = (json['from_integration'] as bool?) ?? generated.fromExternalIntegration;
    return ServerMessage.fromGenerated(generated, fromIntegration: fromIntegration);
  }

  static ServerMessage fromResponseJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedResponseMessage.fromJson(json);
    final fromIntegration = (json['from_integration'] as bool?) ?? generated.fromExternalIntegration;
    return ServerMessage.fromGeneratedResponse(generated, fromIntegration: fromIntegration);
  }

  factory ServerMessage.fromGenerated(
    wire.GeneratedMessage generated, {
    bool? fromIntegration,
    bool askForNps = true,
    ChartData? chartData,
  }) {
    final rawChartData = generated.chartData;
    final parsedChartData = chartData ?? ChartData.tryFromJson(rawChartData);
    return ServerMessage(
      generated.id,
      generated.createdAt,
      generated.text,
      MessageSender.values.firstWhere((e) => e.toString().split('.').last == generated.sender),
      MessageType.valuesFromString(generated.type),
      generated.pluginId ?? generated.appId,
      fromIntegration ?? generated.fromExternalIntegration,
      generated.files.map(MessageFile.fromGenerated).toList(),
      generated.filesId,
      generated.memories.map(MessageConversation.fromGenerated).toList(),
      askForNps: askForNps,
      rating: generated.rating,
      chartData: parsedChartData,
      rawChartData: rawChartData,
    );
  }

  factory ServerMessage.fromGeneratedResponse(
    wire.GeneratedResponseMessage generated, {
    bool? fromIntegration,
    ChartData? chartData,
  }) {
    final rawChartData = generated.chartData;
    final parsedChartData = chartData ?? ChartData.tryFromJson(rawChartData);
    return ServerMessage(
      generated.id,
      generated.createdAt,
      generated.text,
      MessageSender.values.firstWhere((e) => e.toString().split('.').last == generated.sender),
      MessageType.valuesFromString(generated.type),
      generated.pluginId ?? generated.appId,
      fromIntegration ?? generated.fromExternalIntegration,
      generated.files.map(MessageFile.fromGenerated).toList(),
      generated.filesId,
      generated.memories.map(MessageConversation.fromGenerated).toList(),
      askForNps: generated.askForNps ?? false,
      rating: generated.rating,
      chartData: parsedChartData,
      rawChartData: rawChartData,
    );
  }

  /// Kept hand-written: emits legacy `from_integration` key (generated uses
  /// `from_external_integration`) and preserves `rawChartData` fallback for
  /// `chart_data` when `chartData` parsing failed.

  Map<String, dynamic> toJson() {
    final chartJson = rawChartData ?? chartData?.toJson();
    return {
      'id': id,
      'created_at': createdAt.toUtc().toIso8601String(),
      'text': text,
      'sender': sender.toString().split('.').last,
      'type': type.toString().split('.').last,
      'plugin_id': appId,
      'from_integration': fromIntegration,
      'memories': memories.map((m) => m.toJson()).toList(),
      'files': files.map((m) => m.toJson()).toList(),
      'ask_for_nps': askForNps,
      'rating': rating,
      'chart_data': chartJson,
    };
  }

  bool areFilesOfSameType() {
    if (files.isEmpty) {
      return true;
    }

    final firstType = files.first.mimeTypeToFileType();
    return files.every((element) => element.mimeTypeToFileType() == firstType);
  }

  static ServerMessage empty({String? appId}) {
    return ServerMessage('0000', DateTime.now(), '', MessageSender.ai, MessageType.text, appId, false, [], [], []);
  }

  static ServerMessage failedMessage() {
    return ServerMessage(
      const Uuid().v4(),
      DateTime.now(),
      'Looks like we are having issues with the server. Please try again later.',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      [],
      [],
      [],
    );
  }

  bool get isEmpty => id == '0000';
}

enum MessageChunkType {
  think('think'),
  data('data'),
  done('done'),
  error('error'),
  message('message');

  final String value;

  const MessageChunkType(this.value);
}

class ServerMessageChunk {
  String messageId;
  MessageChunkType type;
  String text;
  ServerMessage? message;

  ServerMessageChunk(this.messageId, this.text, this.type, {this.message});

  static ServerMessageChunk failedMessage() {
    return ServerMessageChunk(
      const Uuid().v4(),
      'Looks like we are having issues with the server. Please try again later.',
      MessageChunkType.error,
    );
  }
}
