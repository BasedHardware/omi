/// Typed projection of the chat `content_blocks` wire array.
///
/// The canonical schema is owned by the macOS agent runtime
/// (`desktop/macos/agent/src/runtime/types.ts` `ConversationContentBlock`) and
/// mirrored by the Swift codec (`ChatContentBlockCodec`). This decoder follows
/// the same required-field rules so a block that macOS drops is dropped here
/// too, and vice versa.
///
/// Two wire dialects reach mobile: camelCase (desktop/agent, stored verbatim by
/// the backend) and snake_case (validated chat-first specs). Every field is read
/// in both dialects. A malformed block decodes to `null` and is dropped; an
/// unrecognised `type` decodes to [UnknownContentBlock] so the message keeps its
/// text fallback instead of losing content.
library;

sealed class ChatContentBlock {
  const ChatContentBlock({required this.id});

  final String id;

  /// Canonical wire type name (camelCase), used for widget keys.
  String get type;

  /// Decodes a raw wire array, dropping malformed entries.
  static List<ChatContentBlock> decodeList(List<Map<String, dynamic>> raw) {
    final blocks = <ChatContentBlock>[];
    for (final entry in raw) {
      final block = tryDecode(entry);
      if (block != null) blocks.add(block);
    }
    return List.unmodifiable(blocks);
  }

  static ChatContentBlock? tryDecode(Map<String, dynamic> raw) {
    final type = _string(raw, 'type');
    final id = _string(raw, 'id');
    if (type == null || id == null) return null;

    switch (type) {
      case 'text':
        return TextContentBlock(id: id, text: _string(raw, 'text') ?? '');
      case 'toolCall':
      case 'tool_call':
        final name = _string(raw, 'name');
        if (name == null) return null;
        return ToolCallContentBlock(
          id: id,
          name: name,
          status: _string(raw, 'status') ?? 'completed',
          toolUseId: _string(raw, 'toolUseId', 'tool_use_id'),
          inputSummary: _string(raw, 'inputSummary', 'input_summary'),
          inputDetails: _string(raw, 'inputDetails', 'input_details'),
          output: _string(raw, 'output'),
        );
      case 'thinking':
        return ThinkingContentBlock(id: id, text: _string(raw, 'text') ?? '');
      case 'discoveryCard':
      case 'discovery_card':
        return DiscoveryCardContentBlock(
          id: id,
          title: _string(raw, 'title') ?? '',
          summary: _string(raw, 'summary') ?? '',
          fullText: _string(raw, 'fullText', 'full_text') ?? '',
        );
      case 'questionCard':
      case 'question_card':
        return _decodeQuestionCard(raw, id);
      case 'taskCard':
      case 'task_card':
        final taskId = _string(raw, 'taskId', 'task_id');
        if (taskId == null) return null;
        return TaskCardContentBlock(id: id, taskId: taskId);
      case 'goalLink':
      case 'goal_link':
        final goalId = _string(raw, 'goalId', 'goal_id');
        final summary = _string(raw, 'summary');
        if (goalId == null || summary == null) return null;
        return GoalLinkContentBlock(id: id, goalId: goalId, summary: summary);
      case 'captureLink':
      case 'capture_link':
        final conversationId = _string(raw, 'conversationId', 'conversation_id');
        final summary = _string(raw, 'summary');
        if (conversationId == null || summary == null) return null;
        return CaptureLinkContentBlock(
          id: id,
          conversationId: conversationId,
          summary: summary,
          momentTimestampMs: _int(raw, 'momentTimestampMs', 'moment_timestamp_ms'),
        );
      case 'conversationLink':
      case 'conversation_link':
        final conversationId = _string(raw, 'conversationId', 'conversation_id');
        final summary = _string(raw, 'summary');
        if (conversationId == null || summary == null) return null;
        return ConversationLinkContentBlock(
          id: id,
          conversationId: conversationId,
          summary: summary,
          recommendedActionItems: _decodeRecommendedActionItems(
            raw['recommendedActionItems'] ?? raw['recommended_action_items'],
          ),
        );
      case 'memoryLink':
      case 'memory_link':
        final memoryId = _string(raw, 'memoryId', 'memory_id');
        final summary = _string(raw, 'summary');
        if (memoryId == null || summary == null) return null;
        return MemoryLinkContentBlock(id: id, memoryId: memoryId, summary: summary);
      case 'citation':
        final ordinal = _int(raw, 'ordinal');
        final kind = _string(raw, 'kind');
        final sourceId = _string(raw, 'sourceId', 'source_id');
        if (ordinal == null || kind == null || sourceId == null) return null;
        return CitationContentBlock(
          id: id,
          ordinal: ordinal,
          kind: kind,
          sourceId: sourceId,
          title: _string(raw, 'title'),
          preview: _string(raw, 'preview'),
        );
      case 'agentSpawn':
      case 'agent_spawn':
        final sessionId = _string(raw, 'sessionId', 'session_id');
        final runId = _string(raw, 'runId', 'run_id');
        if (sessionId == null || runId == null) return null;
        return AgentSpawnContentBlock(
          id: id,
          sessionId: sessionId,
          runId: runId,
          pillId: _string(raw, 'pillId', 'pill_id'),
          title: _string(raw, 'title') ?? '',
          objective: _string(raw, 'objective') ?? '',
        );
      case 'agentCompletion':
      case 'agent_completion':
        // Older persisted agent completions omitted status. The desktop
        // codec preserves their historical completed default; explicit
        // terminal values (including timed_out/orphaned) still pass through.
        return AgentCompletionContentBlock(
          id: id,
          sessionId: _string(raw, 'sessionId', 'session_id'),
          runId: _string(raw, 'runId', 'run_id'),
          pillId: _string(raw, 'pillId', 'pill_id'),
          title: _string(raw, 'title') ?? '',
          output: _string(raw, 'output') ?? '',
          status: _string(raw, 'status') ?? 'completed',
        );
      default:
        return UnknownContentBlock(id: id, type: type, raw: Map.unmodifiable(raw));
    }
  }

  static ChatContentBlock? _decodeQuestionCard(Map<String, dynamic> raw, String id) {
    final questionId = _string(raw, 'questionId', 'question_id');
    final text = _string(raw, 'text');
    final subject = raw['subject'];
    if (questionId == null || text == null || subject is! Map) return null;
    final subjectMap = Map<String, dynamic>.from(subject);
    final subjectKind = _string(subjectMap, 'kind');
    final subjectId = _string(subjectMap, 'id');
    if (subjectKind == null || subjectId == null) return null;

    final rawOptions = raw['options'];
    if (rawOptions is! List) return null;
    final options = <QuestionCardOption>[];
    for (final entry in rawOptions) {
      if (entry is! Map) continue;
      final option = Map<String, dynamic>.from(entry);
      final optionId = _string(option, 'optionId', 'option_id');
      final label = _string(option, 'label');
      if (optionId == null || label == null) continue;
      options.add(
        QuestionCardOption(
          optionId: optionId,
          label: label,
          preparedAnswer: _string(option, 'preparedAnswer', 'prepared_answer') ?? label,
          isDeferral: option['defer'] == true,
        ),
      );
    }
    if (options.isEmpty) return null;

    return QuestionCardContentBlock(
      id: id,
      questionId: questionId,
      text: text,
      subjectKind: subjectKind,
      subjectId: subjectId,
      options: List.unmodifiable(options),
      selectedOptionId: _string(raw, 'selectedOptionId', 'selected_option_id'),
    );
  }

  static List<ConversationLinkActionItem> _decodeRecommendedActionItems(Object? value) {
    if (value is! List) return const [];
    final items = <ConversationLinkActionItem>[];
    for (final entry in value) {
      if (entry is! Map) continue;
      final item = Map<String, dynamic>.from(entry);
      final description = _string(item, 'description');
      if (description == null) continue;
      items.add(
        ConversationLinkActionItem(
          description: description,
          taskId: _string(item, 'taskId', 'task_id'),
        ),
      );
    }
    return List.unmodifiable(items);
  }

  static String? _string(Map<String, dynamic> raw, String camel, [String? snake]) {
    final value = raw[camel] ?? (snake == null ? null : raw[snake]);
    if (value is! String) return null;
    return value.trim().isEmpty ? null : value;
  }

  static int? _int(Map<String, dynamic> raw, String camel, [String? snake]) {
    final value = raw[camel] ?? (snake == null ? null : raw[snake]);
    if (value is int) return value;
    if (value is double) return value.toInt();
    if (value is String) return int.tryParse(value);
    return null;
  }
}

class TextContentBlock extends ChatContentBlock {
  const TextContentBlock({required super.id, required this.text});

  final String text;

  @override
  String get type => 'text';
}

class ToolCallContentBlock extends ChatContentBlock {
  const ToolCallContentBlock({
    required super.id,
    required this.name,
    required this.status,
    this.toolUseId,
    this.inputSummary,
    this.inputDetails,
    this.output,
  });

  final String name;
  final String status;
  final String? toolUseId;
  final String? inputSummary;
  final String? inputDetails;
  final String? output;

  @override
  String get type => 'toolCall';
}

class ThinkingContentBlock extends ChatContentBlock {
  const ThinkingContentBlock({required super.id, required this.text});

  final String text;

  @override
  String get type => 'thinking';
}

class DiscoveryCardContentBlock extends ChatContentBlock {
  const DiscoveryCardContentBlock({
    required super.id,
    required this.title,
    required this.summary,
    required this.fullText,
  });

  final String title;
  final String summary;
  final String fullText;

  @override
  String get type => 'discoveryCard';
}

class QuestionCardOption {
  const QuestionCardOption({
    required this.optionId,
    required this.label,
    required this.preparedAnswer,
    this.isDeferral = false,
  });

  final String optionId;
  final String label;
  final String preparedAnswer;
  final bool isDeferral;
}

class QuestionCardContentBlock extends ChatContentBlock {
  const QuestionCardContentBlock({
    required super.id,
    required this.questionId,
    required this.text,
    required this.subjectKind,
    required this.subjectId,
    required this.options,
    this.selectedOptionId,
  });

  final String questionId;
  final String text;
  final String subjectKind;
  final String subjectId;
  final List<QuestionCardOption> options;
  final String? selectedOptionId;

  @override
  String get type => 'questionCard';
}

class TaskCardContentBlock extends ChatContentBlock {
  const TaskCardContentBlock({required super.id, required this.taskId});

  final String taskId;

  @override
  String get type => 'taskCard';
}

class GoalLinkContentBlock extends ChatContentBlock {
  const GoalLinkContentBlock({required super.id, required this.goalId, required this.summary});

  final String goalId;
  final String summary;

  @override
  String get type => 'goalLink';
}

class CaptureLinkContentBlock extends ChatContentBlock {
  const CaptureLinkContentBlock({
    required super.id,
    required this.conversationId,
    required this.summary,
    this.momentTimestampMs,
  });

  final String conversationId;
  final String summary;
  final int? momentTimestampMs;

  @override
  String get type => 'captureLink';
}

class ConversationLinkActionItem {
  const ConversationLinkActionItem({required this.description, this.taskId});

  final String description;
  final String? taskId;
}

class ConversationLinkContentBlock extends ChatContentBlock {
  const ConversationLinkContentBlock({
    required super.id,
    required this.conversationId,
    required this.summary,
    this.recommendedActionItems = const [],
  });

  final String conversationId;
  final String summary;
  final List<ConversationLinkActionItem> recommendedActionItems;

  @override
  String get type => 'conversationLink';
}

class MemoryLinkContentBlock extends ChatContentBlock {
  const MemoryLinkContentBlock({required super.id, required this.memoryId, required this.summary});

  final String memoryId;
  final String summary;

  @override
  String get type => 'memoryLink';
}

class CitationContentBlock extends ChatContentBlock {
  const CitationContentBlock({
    required super.id,
    required this.ordinal,
    required this.kind,
    required this.sourceId,
    this.title,
    this.preview,
  });

  final int ordinal;
  final String kind;
  final String sourceId;
  final String? title;
  final String? preview;

  @override
  String get type => 'citation';
}

class AgentSpawnContentBlock extends ChatContentBlock {
  const AgentSpawnContentBlock({
    required super.id,
    required this.sessionId,
    required this.runId,
    this.pillId,
    this.title = '',
    this.objective = '',
  });

  final String sessionId;
  final String runId;
  final String? pillId;
  final String title;
  final String objective;

  @override
  String get type => 'agentSpawn';
}

class AgentCompletionContentBlock extends ChatContentBlock {
  const AgentCompletionContentBlock({
    required super.id,
    this.sessionId,
    this.runId,
    this.pillId,
    this.title = '',
    this.output = '',
    this.status = 'completed',
  });

  final String? sessionId;
  final String? runId;
  final String? pillId;
  final String title;
  final String output;
  final String status;

  @override
  String get type => 'agentCompletion';
}

/// A block type this client does not know. Kept so the message keeps rendering
/// its synthesized fallback text instead of silently losing content.
class UnknownContentBlock extends ChatContentBlock {
  const UnknownContentBlock({required super.id, required String type, required this.raw}) : _type = type;

  final String _type;
  final Map<String, dynamic> raw;

  @override
  String get type => _type;
}
