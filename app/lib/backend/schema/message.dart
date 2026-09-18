import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/gen/messages_wire.g.dart' as wire;
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/models/chat_evidence_reference.dart';
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
  List<Map<String, dynamic>> contentBlocks;

  /// Optional supplemental references. Text remains authoritative when this
  /// envelope is absent, malformed, unavailable, or from a future version.
  ChatEvidenceReferenceEnvelope? evidenceEnvelope;

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
    this.contentBlocks = const [],
    this.evidenceEnvelope,
  });

  static ServerMessage fromJson(Map<String, dynamic> json) {
    return ServerMessage.fromGeneratedWireJson(json);
  }

  static ServerMessage fromGeneratedWireJson(Map<String, dynamic> json) {
    // Evidence and content blocks are deliberately fail-soft UI chrome. Decode
    // them through the bounded compatibility parsers below instead of letting
    // the strict generated DTO reject an otherwise valid text answer — an FCM
    // push carries `content_blocks` as JSON text, which the generated
    // `List<Map>` reader rejects outright.
    final generatedJson = Map<String, dynamic>.from(json)
      ..remove('evidence')
      ..remove('content_blocks');
    final generated = wire.GeneratedMessage.fromJson(generatedJson);
    final fromIntegration = (json['from_integration'] as bool?) ?? generated.fromExternalIntegration;
    return ServerMessage.fromGenerated(
      generated,
      fromIntegration: fromIntegration,
      contentBlocks: _decodeContentBlocks(json['content_blocks'], generated.metadata),
      evidenceEnvelope: _decodeEvidenceEnvelope(json, generated.metadata),
    );
  }

  static ServerMessage fromResponseJson(Map<String, dynamic> json) {
    final generatedJson = Map<String, dynamic>.from(json)
      ..remove('evidence')
      ..remove('content_blocks');
    final generated = wire.GeneratedResponseMessage.fromJson(generatedJson);
    final fromIntegration = (json['from_integration'] as bool?) ?? generated.fromExternalIntegration;
    return ServerMessage.fromGeneratedResponse(
      generated,
      fromIntegration: fromIntegration,
      contentBlocks: _decodeContentBlocks(json['content_blocks'], generated.metadata),
      evidenceEnvelope: _decodeEvidenceEnvelope(json, generated.metadata),
    );
  }

  factory ServerMessage.fromGenerated(
    wire.GeneratedMessage generated, {
    bool? fromIntegration,
    bool askForNps = true,
    ChartData? chartData,
    List<Map<String, dynamic>> contentBlocks = const [],
    ChatEvidenceReferenceEnvelope? evidenceEnvelope,
  }) {
    final rawChartData = generated.chartData;
    final parsedChartData = chartData ?? ChartData.tryFromJson(rawChartData);
    return ServerMessage(
      generated.id,
      generated.createdAt,
      _textWithStructuredFallback(generated.text, contentBlocks),
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
      contentBlocks: contentBlocks,
      evidenceEnvelope: evidenceEnvelope,
    );
  }

  factory ServerMessage.fromGeneratedResponse(
    wire.GeneratedResponseMessage generated, {
    bool? fromIntegration,
    ChartData? chartData,
    List<Map<String, dynamic>> contentBlocks = const [],
    ChatEvidenceReferenceEnvelope? evidenceEnvelope,
  }) {
    final rawChartData = generated.chartData;
    final parsedChartData = chartData ?? ChartData.tryFromJson(rawChartData);
    return ServerMessage(
      generated.id,
      generated.createdAt,
      _textWithStructuredFallback(generated.text, contentBlocks),
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
      contentBlocks: contentBlocks,
      evidenceEnvelope: evidenceEnvelope,
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
      'content_blocks': contentBlocks,
      if (evidenceEnvelope != null) 'evidence': evidenceEnvelope!.toJson(),
    };
  }

  /// Decode only additive evidence fields. A malformed or unknown payload is
  /// treated as absent so released text/chat behavior remains unchanged.
  static ChatEvidenceReferenceEnvelope? _decodeEvidenceEnvelope(Map<String, dynamic> json, String? metadata) {
    final direct =
        json['evidence'] ?? json['evidence_envelope'] ?? json['evidence_refs'] ?? json['evidence_references'];
    final parsedDirect = _tryEvidenceEnvelope(direct);
    if (parsedDirect != null) return parsedDirect;

    if (metadata == null || metadata.isEmpty) return null;
    try {
      final decoded = jsonDecode(metadata);
      if (decoded is! Map) return null;
      final metadataMap = Map<String, dynamic>.from(decoded);
      return _tryEvidenceEnvelope(
        metadataMap['evidence'] ??
            metadataMap['evidence_envelope'] ??
            metadataMap['evidence_refs'] ??
            metadataMap['evidence_references'],
      );
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  static ChatEvidenceReferenceEnvelope? _tryEvidenceEnvelope(Object? value) {
    if (value is List) return ChatEvidenceReferenceEnvelope.tryFromJson({'references': value});
    return ChatEvidenceReferenceEnvelope.tryFromJson(value);
  }

  static List<Map<String, dynamic>> _decodeContentBlocks(dynamic firstClass, String? metadata) {
    // FCM data payloads are Dict[str, str], so a push (the only transport that
    // carries a `day_summary` message today) delivers `content_blocks` as JSON
    // text. Decode it here so both transports have one decoder; anything
    // malformed degrades to "no blocks", never to a lost message.
    final firstClassValue = firstClass is String ? _tryDecodeJson(firstClass) : firstClass;
    final direct = _mapList(firstClassValue);
    if (direct.isNotEmpty || firstClassValue is List) return direct;
    if (metadata == null || metadata.isEmpty) return const [];
    try {
      final decoded = jsonDecode(metadata);
      return decoded is Map<String, dynamic> ? _mapList(decoded['content_blocks']) : const [];
    } on FormatException {
      return const [];
    }
  }

  static List<Map<String, dynamic>> _mapList(dynamic value) {
    if (value is! List) return const [];
    return value.whereType<Map>().map((item) => Map<String, dynamic>.from(item)).toList(growable: false);
  }

  List<ChatContentBlock>? _typedContentBlocks;
  static Object? _tryDecodeJson(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return null;
    try {
      return jsonDecode(trimmed);
    } on FormatException {
      return null;
    }
  }

  /// The `memoryReviewCard` block for this message, when it carries a usable one.
  MemoryReviewCardBlock? get memoryReviewCard {
    for (final block in contentBlocks) {
      final card = MemoryReviewCardBlock.tryFromBlock(block);
      if (card != null) return card;
    }
    return null;
  }

  /// The one grounded follow-up question the answer invites, when present.
  String? get followUpQuestion {
    for (final block in contentBlocks) {
      if (!_followUpTypes.contains(block['type'])) continue;
      final text = block['text'];
      if (text is String && text.trim().isNotEmpty) return text.trim();
    }
    return null;
  }

  static const _followUpTypes = {'followUp', 'follow_up'};

  /// Typed projection of [contentBlocks], decoded once per message.
  ///
  /// The raw list stays authoritative on the wire (see [toJson]); this is the
  /// renderable view used by the chat content-block widgets.
  List<ChatContentBlock> get typedContentBlocks => _typedContentBlocks ??= ChatContentBlock.decodeList(contentBlocks);

  /// True when [text] carries nothing beyond the fallback text synthesized from
  /// [contentBlocks]. The interactive blocks then replace the body instead of
  /// repeating it.
  bool get textIsStructuredFallback {
    if (contentBlocks.isEmpty) return false;
    final fallback = _structuredFallbackText(contentBlocks);
    if (fallback.isEmpty) return false;
    final body = text.trim();
    return body.isEmpty || _normalizeWhitespace(body) == _normalizeWhitespace(fallback);
  }

  /// Returns the canonical body fallback for one raw wire block.
  ///
  /// A rich block can replace the ordinary message body on clients that know
  /// how to render it. Unrecognised or display-only blocks still need their
  /// synthesized line in that mode; otherwise a mixed turn silently loses
  /// thinking, tool, citation, or future block content.
  String? structuredFallbackTextForRawBlock(Map<String, dynamic> block) {
    final fallback = _blockFallbackText(block).trim();
    return fallback.isEmpty ? null : fallback;
  }

  static String _normalizeWhitespace(String value) {
    return value.split(RegExp(r'\s+')).where((part) => part.isNotEmpty).join(' ');
  }

  static String _structuredFallbackText(List<Map<String, dynamic>> blocks) {
    if (blocks.isEmpty) return '';
    return blocks.map(_blockFallbackText).where((value) => value.isNotEmpty).join('\n');
  }

  static String _textWithStructuredFallback(String text, List<Map<String, dynamic>> blocks) {
    if (text.trim().isNotEmpty || blocks.isEmpty) return text;
    return _structuredFallbackText(blocks);
  }

  static String _blockFallbackText(Map<String, dynamic> block) {
    String value(String camel, [String? snake]) {
      final candidate = block[camel] ?? (snake == null ? null : block[snake]);
      return candidate is String ? candidate.trim() : '';
    }

    String labelled(String label, Iterable<String> details) {
      final unique = details.where((detail) => detail.isNotEmpty).toSet().toList(growable: false);
      return unique.isEmpty ? label : '$label - ${unique.join(' - ')}';
    }

    switch (block['type']) {
      case 'text':
        return value('text').isEmpty ? 'Message' : value('text');
      case 'toolCall':
      case 'tool_call':
        return labelled('Tool', [value('name'), value('output'), value('inputSummary', 'input_summary')]);
      case 'thinking':
        return labelled('Thinking', [value('text')]);
      case 'discoveryCard':
      case 'discovery_card':
        return labelled('Discovery', [value('title'), value('summary')]);
      case 'questionCard':
      case 'question_card':
        return value('text').isEmpty ? 'Question' : value('text');
      case 'memoryReviewCard':
      case 'memory_review_card':
      case 'followUp':
      case 'follow_up':
        // Both render natively on mobile — MemoryReviewCard draws its own
        // "Things I learned today" heading, and ChatFollowUpChip draws the
        // question. Inventing the same words as fallback prose says them
        // twice; and when the block is malformed enough that no card renders
        // (MemoryReviewCardBlock.tryFromBlock returns null for an item-less
        // block), a bare heading over nothing is worse than no heading.
        return '';
      case 'taskCard':
      case 'task_card':
        return 'Task';
      case 'goalLink':
      case 'goal_link':
        return labelled('Goal', [value('summary')]);
      case 'captureLink':
      case 'capture_link':
        return labelled('Capture', [value('summary')]);
      case 'conversationLink':
      case 'conversation_link':
        return labelled('Meeting notes ready', [value('summary')]);
      case 'memoryLink':
      case 'memory_link':
        return labelled('Memory', [value('summary')]);
      case 'citation':
        return labelled('Source', [value('title'), value('preview')]);
      case 'evidence':
      case 'evidence_envelope':
        // Evidence is optional UI chrome. Never invent fallback answer text for
        // a reference-only block.
        return '';
      case 'agentSpawn':
      case 'agent_spawn':
        return labelled('Agent started', [value('title'), value('objective')]);
      case 'agentCompletion':
      case 'agent_completion':
        return labelled('Agent completed', [value('title'), value('output')]);
      default:
        return labelled('Chat item', [value('title'), value('summary'), value('text')]);
    }
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
