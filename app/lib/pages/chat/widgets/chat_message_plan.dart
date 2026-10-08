import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/models/chat_evidence_reference.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Conversation-shaped evidence is the same source list as [ServerMessage.memories].
/// Keep those citations on [MemoriesMessageWidget] only.
bool isConversationSourceEvidence(ChatEvidenceReferenceKind kind) {
  return kind == ChatEvidenceReferenceKind.conversationSummary || kind == ChatEvidenceReferenceKind.conversationSegment;
}

/// Supplemental chrome to render beside the answer. Conversation sources that
/// already appear as citation cards are stripped so the message has one list.
ChatEvidenceReferenceEnvelope? visibleSupplementalEvidence(ServerMessage message) {
  final evidence = message.evidenceEnvelope;
  if (evidence == null || evidence.isEmpty) return null;
  if (message.memories.isEmpty) return evidence;
  final leftover = evidence.references.where((ref) => !isConversationSourceEvidence(ref.kind)).toList();
  if (leftover.isEmpty) return null;
  return ChatEvidenceReferenceEnvelope(
    schemaVersion: evidence.schemaVersion,
    requestId: evidence.requestId,
    references: leftover,
  );
}

/// The widget that draws an AI reply's body, chosen exactly as [buildMessageWidget] always has.
enum ChatMessageLayout {
  /// Interactive content blocks replace a body that is only their own fallback projection.
  blocks,

  /// The answer cites conversations ([ServerMessage.memories]).
  citations,
  daySummary,

  /// The first message of a chat, with its starter options.
  initialOptions,
  normal,
}

/// One piece of an AI reply, in the order it renders.
enum ChatMessagePartKind {
  files,
  activity,
  body,
  blocksReplaceBody,
  daySummary,
  initialOptions,
  chart,
  chartPlaceholder,
  actionBar,
  citations,
  blocks,
  reviewCard,
  evidence,
  memoryActionReceipt,
}

/// One content block that renders: an interactive [component], or [text] (a text block or the
/// synthesized fallback line of a block without a component) when the blocks replace the body.
class ChatBlockEntry {
  const ChatBlockEntry({required this.index, required this.key, this.component, this.text});

  /// Position in the raw wire array.
  final int index;

  /// The Flutter widget key suffix, from the wire id or the index. Never a native row id.
  final String key;
  final ChatContentBlock? component;
  final String? text;
}

/// What an AI reply shows, decided once for both renderers. The Flutter widgets draw it as before;
/// the native transcript maps every part to rows, and a part it cannot map keeps the complete
/// Flutter chat instead of dropping content.
class ChatMessagePlan {
  ChatMessagePlan._(this.message, this.layout, this.parts, {required this.showTypingIndicator})
      : assert(_mapped(layout, parts));

  /// Whether [layout] renders every part, in order.
  static bool _mapped(ChatMessageLayout layout, List<ChatMessagePartKind> parts) {
    final allowed = _layoutParts[layout]!;
    var last = -1;
    for (final part in parts) {
      final position = allowed.indexOf(part);
      if (position <= last) return false;
      last = position;
    }
    return true;
  }

  /// [displayOptions] is true for the first message of a chat; [showTypingIndicator] while it streams.
  factory ChatMessagePlan.of(ServerMessage message, {required bool displayOptions, bool showTypingIndicator = false}) {
    final typing = showTypingIndicator;
    final renderable = hasRenderableBlocks(message);
    // A message whose text is only the fallback synthesized from its blocks has nothing to say that
    // the components do not already show, so the components replace the body instead of repeating it.
    // Day summaries, memory citations and the initial-options surface still render the normal body.
    final replace = renderable &&
        message.memories.isEmpty &&
        message.type != MessageType.daySummary &&
        !displayOptions &&
        message.textIsStructuredFallback;
    final layout = replace
        ? ChatMessageLayout.blocks
        : message.memories.isNotEmpty
            ? ChatMessageLayout.citations
            : message.type == MessageType.daySummary
                ? ChatMessageLayout.daySummary
                : displayOptions
                    ? ChatMessageLayout.initialOptions
                    : ChatMessageLayout.normal;
    final text = message.text.decodeString;
    final citationText = message.isEmpty ? '…' : text;
    final chart = message.chartData != null;
    final chartPlaceholder = !chart && typing && message.thinkings.any((t) => t.toLowerCase().contains('chart'));
    final steps = _steps(message).isNotEmpty;
    final parts = <ChatMessagePartKind>[
      ...switch (layout) {
        ChatMessageLayout.blocks => [ChatMessagePartKind.blocksReplaceBody],
        ChatMessageLayout.citations => [
            if (steps) ChatMessagePartKind.activity,
            if (!typing) ChatMessagePartKind.body,
            if (citationText.isNotEmpty && citationText != '…' && !typing) ChatMessagePartKind.actionBar,
            if (chart) ChatMessagePartKind.chart,
            if (chartPlaceholder) ChatMessagePartKind.chartPlaceholder,
            ChatMessagePartKind.citations,
          ],
        ChatMessageLayout.daySummary => [ChatMessagePartKind.daySummary],
        ChatMessageLayout.initialOptions => [
            if (!typing) ChatMessagePartKind.body,
            ChatMessagePartKind.initialOptions,
          ],
        ChatMessageLayout.normal => [
            if (message.files.isNotEmpty && message.filesId.isNotEmpty) ChatMessagePartKind.files,
            if (steps) ChatMessagePartKind.activity,
            if (text.isNotEmpty) ChatMessagePartKind.body,
            if (chart) ChatMessagePartKind.chart,
            if (chartPlaceholder) ChatMessagePartKind.chartPlaceholder,
            if (text.isNotEmpty && !typing) ChatMessagePartKind.actionBar,
          ],
      },
      if (renderable && !replace) ChatMessagePartKind.blocks,
      if (!typing && message.memoryReviewCard != null) ChatMessagePartKind.reviewCard,
      if (visibleSupplementalEvidence(message) != null) ChatMessagePartKind.evidence,
      if (!typing && message.memoryAction != null) ChatMessagePartKind.memoryActionReceipt,
    ];
    return ChatMessagePlan._(message, layout, parts, showTypingIndicator: typing);
  }

  /// A plan with explicit parts; a part its layout does not render, or one out of order, throws.
  /// [ChatMessagePlan.of] never builds such a plan, so no renderer throws while it builds.
  factory ChatMessagePlan.fromParts(ServerMessage message, ChatMessageLayout layout, List<ChatMessagePartKind> parts,
      {bool showTypingIndicator = false}) {
    if (!_mapped(layout, parts)) throw ArgumentError.value(parts, 'parts', 'Unmapped chat message part for $layout');
    return ChatMessagePlan._(message, layout, List.unmodifiable(parts), showTypingIndicator: showTypingIndicator);
  }

  /// The parts each layout can render, in render order. The appended chrome is shared.
  static const _appended = [
    ChatMessagePartKind.blocks,
    ChatMessagePartKind.reviewCard,
    ChatMessagePartKind.evidence,
    ChatMessagePartKind.memoryActionReceipt,
  ];
  static const _layoutParts = {
    ChatMessageLayout.blocks: [
      ChatMessagePartKind.blocksReplaceBody,
      ChatMessagePartKind.reviewCard,
      ChatMessagePartKind.evidence,
      ChatMessagePartKind.memoryActionReceipt,
    ],
    ChatMessageLayout.citations: [
      ChatMessagePartKind.activity,
      ChatMessagePartKind.body,
      ChatMessagePartKind.actionBar,
      ChatMessagePartKind.chart,
      ChatMessagePartKind.chartPlaceholder,
      ChatMessagePartKind.citations,
      ..._appended,
    ],
    ChatMessageLayout.daySummary: [ChatMessagePartKind.daySummary, ..._appended],
    ChatMessageLayout.initialOptions: [ChatMessagePartKind.body, ChatMessagePartKind.initialOptions, ..._appended],
    ChatMessageLayout.normal: [
      ChatMessagePartKind.files,
      ChatMessagePartKind.activity,
      ChatMessagePartKind.body,
      ChatMessagePartKind.chart,
      ChatMessagePartKind.chartPlaceholder,
      ChatMessagePartKind.actionBar,
      ..._appended,
    ],
  };

  final ServerMessage message;
  final ChatMessageLayout layout;
  final List<ChatMessagePartKind> parts;
  final bool showTypingIndicator;

  bool has(ChatMessagePartKind kind) => parts.contains(kind);

  bool get blocksReplaceBody => layout == ChatMessageLayout.blocks;

  /// The body text as its layout shows it: a citation reply that has not arrived reads '…'.
  String get text => layout == ChatMessageLayout.citations && message.isEmpty ? '…' : message.text.decodeString;

  /// The reply is still streaming and has no answer text yet, so its steps are the live activity.
  bool get working => showTypingIndicator && (layout == ChatMessageLayout.citations ? text == '…' : text.isEmpty);

  /// The reply's tool steps as streamed (decoded, blank ones dropped), oldest first.
  List<String> get activitySteps => _steps(message);

  static List<String> _steps(ServerMessage message) =>
      message.thinkings.map((t) => t.decodeString).where((t) => t.trim().isNotEmpty).toList();

  ChatEvidenceReferenceEnvelope? get evidence => visibleSupplementalEvidence(message);

  MemoryReviewCardBlock? get reviewCard => has(ChatMessagePartKind.reviewCard) ? message.memoryReviewCard : null;

  /// The content blocks that render, in wire order.
  List<ChatBlockEntry> get blockEntries => chatBlockEntries(message, renderStructuredFallbackText: blocksReplaceBody);

  /// True when at least one block in [message] has an interactable component.
  static bool hasRenderableBlocks(ServerMessage message) => message.typedContentBlocks.any(isRenderableBlock);

  static bool isRenderableBlock(ChatContentBlock block) {
    return block is TaskCardContentBlock ||
        block is GoalLinkContentBlock ||
        block is CaptureLinkContentBlock ||
        block is ConversationLinkContentBlock ||
        block is MemoryLinkContentBlock ||
        block is QuestionCardContentBlock ||
        block is DiscoveryCardContentBlock ||
        block is AgentSpawnContentBlock ||
        block is AgentCompletionContentBlock;
  }
}

/// Walks the raw wire array instead of only the typed projection. The decoder intentionally drops
/// malformed blocks, but the message body still contains their canonical fallback line; keeping
/// this pass raw prevents a mixed turn from losing that line beside a valid card.
List<ChatBlockEntry> chatBlockEntries(ServerMessage message, {required bool renderStructuredFallbackText}) {
  final entries = <ChatBlockEntry>[];
  for (var index = 0; index < message.contentBlocks.length; index++) {
    final rawBlock = message.contentBlocks[index];
    final block = ChatContentBlock.tryDecode(rawBlock);
    if (block != null && ChatMessagePlan.isRenderableBlock(block)) {
      entries.add(ChatBlockEntry(index: index, key: block.id, component: block));
      continue;
    }
    if (block is TextContentBlock && renderStructuredFallbackText && block.text.trim().isNotEmpty) {
      entries.add(ChatBlockEntry(index: index, key: 'text-${block.id}', text: block.text));
      continue;
    }
    final fallback = renderStructuredFallbackText ? message.structuredFallbackTextForRawBlock(rawBlock) : null;
    if (fallback == null) continue;
    final fallbackKey =
        rawBlock['id'] is String && (rawBlock['id'] as String).isNotEmpty ? rawBlock['id'] as String : '$index';
    entries.add(ChatBlockEntry(index: index, key: 'fallback-$fallbackKey', text: fallback));
  }
  return entries;
}
