import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_navigation_chrome.dart';
import 'package:omi/mobile/native_ui/native_rich_text.dart';
import 'package:omi/models/chat_evidence_reference.dart';
import 'package:omi/pages/memories/widgets/memory_dialog.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/components/memory_review_card.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/text_selection_controls.dart';

import 'package:omi/backend/http/api/goals.dart';

import 'ai_message.dart';
import 'chat_message_plan.dart';
import 'content_blocks/agent_run_blocks.dart';
import 'content_blocks/conversation_link_blocks.dart';
import 'content_blocks/goal_link_block.dart';
import 'markdown_message_widget.dart';

/// What the native transcript asks of the chat page. Every mutation stays with its existing owner:
/// sends and retries with the page and [MessageProvider], ratings with [MessageProvider.setMessageNps],
/// links with [openChatMarkdownLink].
class ChatNativeActions {
  const ChatNativeActions({
    required this.send,
    required this.askOmi,
    required this.retry,
    required this.setMessageNps,
    required this.updateConversation,
    this.openLink = openChatMarkdownLink,
    this.fetchConversation,
  });

  final void Function(String text) send;

  /// Quotes [text] as the context of the next message.
  final void Function(String text) askOmi;
  final Future<void> Function(ServerMessage failed) retry;
  final Future<bool> Function(ServerMessage message, int value, {String? reason}) setMessageNps;
  final void Function(ServerConversation conversation) updateConversation;
  final Future<void> Function(String href) openLink;
  final Future<ServerConversation?> Function(String id)? fetchConversation;
}

/// The chat transcript as native rows: every [ChatMessagePlan] part of every message, inline.
///
/// Row ids are 'chat_<part>_<message>_<index>' (the bubble keeps 'chat_message_<message>'): the
/// message id, made unique when the transcript repeats one, plus a position. Block, task, memory
/// and conversation ids never become row ids or payloads. The page owns this object; its local
/// presentation state (opening links, expanded discoveries, optimistic ratings) lives as long as the
/// page: rating commands, review controllers and parsed bodies are released with their message,
/// the rest on [dispose].
class ChatNativeTranscript {
  ChatNativeTranscript({required this.onChanged});

  /// Repaints the page after local presentation state changed.
  final VoidCallback onChanged;

  final _rich = <String, (int, _RichBody)>{};
  final _commands = <String, MessageActionCommands>{};
  final _reviews = <String, MemoryReviewController>{};
  final _opening = <String>{};
  final _unavailable = <String>{};
  final _expanded = <String>{};
  final _toggling = <String>{};
  final _taskHydration = <String>{};
  final _taskHydrated = <String>{};
  final _memoryHydration = <String>{};
  bool _disposed = false;

  void _changed() {
    if (!_disposed) onChanged();
  }

  /// The rows for every message in [provider], in transcript order.
  List<NativeRow> rows(BuildContext context, MessageProvider provider, ChatNativeActions actions) {
    final messages = provider.messages;
    final keys = <String>{};
    final rows = <NativeRow>[];
    for (final (position, message) in messages.indexed) {
      // Placeholder replies share one id; a repeat gets the first free '~n' suffix.
      var key = message.id;
      for (var n = 1; keys.contains(key); n++) {
        key = '${message.id}~$n';
      }
      keys.add(key);
      if (message.sender != MessageSender.ai) {
        rows.addAll(_userRows(context, message, key, actions));
        continue;
      }
      if (provider.isReplyFailed(message)) {
        final retry = provider.canRetryReply(message);
        rows.add(NativeRow(
          'chat_message_$key',
          chatReplyFailureText(context.l10n, provider.replyFailure(message)),
          kind: 'message_ai',
          plainText: true,
          symbol: retry ? 'arrow.clockwise' : null,
          subtitle: retry ? context.l10n.tryAgain : '',
          onVisible: (_) {
            if (!message.isEmpty) provider.markChatResultVisible(message.id);
          },
          action: retry ? (_) => actions.retry(message) : null,
        ));
        continue;
      }
      final plan = ChatMessagePlan.of(
        message,
        // The same rule as the classic transcript: only the first message offers the starters.
        displayOptions: messages.length <= 1,
        showTypingIndicator: provider.showTypingIndicator && position == messages.length - 1,
      );
      rows.addAll(nativeMessageRows(context, plan, key, actions, onVisible: (_) {
        if (!message.isEmpty) provider.markChatResultVisible(message.id);
        _reviewVisible(context, key);
      }));
    }
    _release(keys);
    return rows;
  }

  void _release(Set<String> keys) {
    bool gone(String key) => !keys.contains(key);
    for (final key in _commands.keys.where(gone).toList()) {
      _commands.remove(key)!.dispose();
    }
    for (final key in _reviews.keys.where(gone).toList()) {
      _reviews.remove(key)!
        ..removeListener(_changed)
        ..dispose();
    }
    // Block bodies are cached as '<message key>/<block index>'.
    _rich.removeWhere((key, _) => gone(key.split('/').first));
  }

  /// One AI message's rows. Its bubble 'chat_message_<key>' always comes first or in its body's
  /// place, so the visibility receipt reports it. A part this projection cannot represent yields an
  /// invalid row, so the whole chat keeps its complete Flutter transcript instead of dropping content.
  List<NativeRow> nativeMessageRows(
    BuildContext context,
    ChatMessagePlan plan,
    String key,
    ChatNativeActions actions, {
    NativeAction? onVisible,
  }) {
    final l10n = context.l10n;
    final message = plan.message;
    final rows = <NativeRow>[];
    if (!plan.has(ChatMessagePartKind.body)) {
      rows.add(NativeRow('chat_message_$key', '', kind: 'message_ai', onVisible: onVisible));
    }
    for (final part in plan.parts) {
      switch (part) {
        case ChatMessagePartKind.files:
          rows.addAll(_fileRows(message, key));
        case ChatMessagePartKind.activity:
          rows.addAll(_activityRows(context, plan, key));
        case ChatMessagePartKind.body:
          rows.add(_bubble('chat_message_$key', key, plan.text, actions, onVisible: onVisible));
        case ChatMessagePartKind.blocksReplaceBody:
        case ChatMessagePartKind.blocks:
          rows.addAll(_blockRows(context, plan, key, actions));
        case ChatMessagePartKind.daySummary:
          rows.addAll(_daySummaryRows(context, plan, key, actions));
        case ChatMessagePartKind.initialOptions:
          rows.addAll([
            for (final (index, option) in [
              l10n.chatStarterYesterday,
              l10n.chatStarterDoDifferently,
              l10n.chatStarterTeachMe,
            ].indexed)
              NativeRow('chat_starter_${key}_$index', option,
                  symbol: 'text.bubble', action: (_) => actions.send(option)),
          ]);
        case ChatMessagePartKind.chart:
          final chart = _chartRow(message.chartData!, key);
          if (chart != null) rows.add(chart);
        case ChatMessagePartKind.chartPlaceholder:
          rows.add(NativeRow('chat_chart_${key}_0', l10n.loading, kind: 'label', symbol: 'chart.bar'));
        case ChatMessagePartKind.actionBar:
          rows.add(_actionsRow(context, plan, key, actions));
        case ChatMessagePartKind.citations:
          rows.addAll(_citationRows(context, message, key, actions));
        case ChatMessagePartKind.reviewCard:
          rows.addAll(_reviewRows(context, plan, key));
        case ChatMessagePartKind.evidence:
          rows.addAll([
            for (final (index, reference) in plan.evidence!.references.indexed)
              NativeRow(
                'chat_evidence_${key}_$index',
                reference.title?.trim().isNotEmpty == true ? reference.title! : reference.sourceLabel,
                kind: 'label',
                subtitle: reference.summary?.trim().isNotEmpty == true ? reference.summary! : reference.statusLabel,
                symbol: chatEvidenceSymbol(reference.kind),
              ),
          ]);
        case ChatMessagePartKind.memoryActionReceipt:
          rows.add(NativeRow(
            'chat_receipt_${key}_0',
            message.memoryAction == 'updated' ? l10n.memoryReviewUpdated : l10n.saved,
            kind: 'label',
            symbol: 'brain',
          ));
      }
    }
    return rows;
  }

  List<NativeRow> _userRows(BuildContext context, ServerMessage message, String key, ChatNativeActions actions) {
    final text = message.text.decodeString;
    final match = RegExp(r'^Context: "([\s\S]+?)"\n\n').firstMatch(text);
    final quoted = match?.group(1);
    final body = (match == null ? text : text.substring(match.end)).trimRight();
    return [
      if (message.files.isNotEmpty && message.filesId.isNotEmpty) ..._fileRows(message, key),
      if (quoted != null)
        NativeRow(
          'chat_context_${key}_0',
          quoted.length > 50 ? '${quoted.substring(0, 50)}…' : quoted,
          kind: 'label',
          symbol: 'arrow.turn.down.right',
        ),
      NativeRow('chat_message_$key', body, kind: 'message_user', plainText: true),
      // The documented replacement for the selection menu's Ask Omi on the user's own text.
      if (body.trim().isNotEmpty)
        NativeRow(
          'chat_ask_${key}_0',
          context.l10n.askOmi,
          symbol: 'quote.bubble',
          action: (_) => _ask(context, body, actions.askOmi),
        ),
    ];
  }

  /// Attachments by name, with a symbol by extension; images keep their existing thumbnail.
  List<NativeRow> _fileRows(ServerMessage message, String key) => [
        for (final (index, file) in message.files.indexed)
          NativeRow(
            'chat_file_${key}_$index',
            file.name,
            kind: 'label',
            symbol: file.mimeTypeToFileType() == 'image' ? 'photo' : chatFileSymbol(file.name),
            imageUri: file.mimeTypeToFileType() == 'image' ? nativeImageUri(file.thumbnail) : null,
          ),
      ];

  /// The reply's Markdown body. Links reach the existing URL owner only through the row's whitelist.
  NativeRow _bubble(String id, String key, String text, ChatNativeActions actions, {NativeAction? onVisible}) {
    final body = _richBody(key, text);
    return NativeRow(
      id,
      text,
      kind: 'message_ai',
      blocks: body.blocks,
      plainText: body.blocks.isEmpty,
      options: body.links,
      onVisible: onVisible,
      action: body.links.isEmpty ? null : (value) => _openLink(body, value, actions),
    );
  }

  Future<void> _openLink(_RichBody body, Object? value, ChatNativeActions actions) async {
    final href = value is String ? body.links[value] : null;
    if (href != null) await actions.openLink(href);
  }

  /// Parsed once per message and text while a reply streams.
  _RichBody _richBody(String key, String text) {
    final cached = _rich[key];
    if (cached != null && cached.$1 == text.hashCode && cached.$2.source == text) return cached.$2;
    final body = _RichBody.parse(text);
    _rich[key] = (text.hashCode, body);
    return body;
  }

  List<NativeRow> _activityRows(BuildContext context, ChatMessagePlan plan, String key) {
    final l10n = context.l10n;
    final steps = plan.activitySteps;
    final working = plan.working;
    void open() => unawaited(_openActivity(context, steps, working));
    if (working) {
      return [
        for (final (index, step) in steps.indexed)
          NativeRow(
            'chat_activity_${key}_$index',
            _stepText(step, l10n.thinking),
            kind: 'navigation',
            symbol: chatThinkingSymbol(getThinkingDisplayText(step)),
            imageUri: _appIcon(context, step),
            // Every step opens the timeline, as each Flutter step line does.
            action: (_) => open(),
          ),
      ];
    }
    return [
      NativeRow(
        'chat_activity_${key}_0',
        _stepText(steps.last, l10n.thinking),
        kind: 'navigation',
        subtitle: l10n.activity,
        symbol: chatThinkingSymbol(getThinkingDisplayText(steps.last)),
        imageUri: _appIcon(context, steps.last),
        action: (_) => open(),
      ),
    ];
  }

  static String _stepText(String step, String empty) {
    final text = getThinkingDisplayText(step).trim();
    return text.isEmpty ? empty : text;
  }

  /// The step's app icon, when it names an app the user has; a URL the image owner cannot load
  /// renders without one.
  String? _appIcon(BuildContext context, String step) {
    final appId = parseAppIdFromThinking(step);
    if (appId == null) return null;
    final app = context.read<AppProvider?>()?.apps.firstWhereOrNull((app) => app.id == appId) ??
        context.read<MessageProvider?>()?.chatApps.firstWhereOrNull((app) => app.id == appId);
    return app == null ? null : nativeImageUri(app.getImageUrl());
  }

  /// The Activity timeline as a native sheet; the Flutter sheet when it cannot be presented.
  Future<void> _openActivity(BuildContext context, List<String> steps, bool working) async {
    final l10n = context.l10n;
    final result = await showIosNativeModal(
      context,
      title: l10n.activity,
      cancelId: 'chat_activity_close',
      actions: [NativeRow('chat_activity_close', l10n.close)],
      sections: [
        NativeSection('chat_activity_steps', [
          for (final (index, step) in steps.indexed)
            NativeRow(
              'chat_activity_step_$index',
              _stepText(step, l10n.thinking),
              kind: 'label',
              symbol: chatThinkingSymbol(getThinkingDisplayText(step)),
              imageUri: _appIcon(context, step),
            ),
          NativeRow(
            'chat_activity_end',
            working ? l10n.thinking : l10n.done,
            kind: 'label',
            symbol: working ? 'ellipsis.circle' : 'checkmark.circle',
          ),
        ]),
      ],
    );
    if (result == null && context.mounted) await showChatActivitySheet(context, steps: steps, working: working);
  }

  /// A categorical chart in index order. An empty dataset has no row; values that cannot be drawn
  /// keep the chart's title readable instead of making the transcript invalid.
  NativeRow? _chartRow(ChartData chart, String key) {
    if (chart.datasets.isEmpty || chart.datasets.first.dataPoints.isEmpty) return null;
    final dataset = chart.datasets.first;
    final points = dataset.dataPoints.take(10000).toList();
    if (points.any((point) => !point.value.isFinite)) {
      return NativeRow('chat_chart_${key}_0', chart.title, kind: 'label', symbol: 'chart.bar');
    }
    return NativeRow(
      'chat_chart_${key}_0',
      chart.title,
      kind: 'chart',
      chartStyle: chart.chartType == 'bar' ? 'bar' : 'line',
      subtitle: dataset.label,
      points: [
        for (final (index, point) in points.indexed)
          {'x': index, 'y': point.value, 'label': nativeChartLabel(point.label)},
      ],
    );
  }

  MessageActionCommands _commandsFor(String key, String text, ServerMessage message, ChatNativeActions? actions) {
    final commands = _commands.putIfAbsent(
      key,
      () => MessageActionCommands(messageText: text, currentNps: message.rating, onChanged: _changed),
    );
    Future<bool> rate(int value, {String? reason}) => actions!.setMessageNps(message, value, reason: reason);
    commands
      ..messageText = text
      ..setMessageNps = actions == null ? null : rate
      ..syncCurrentNps(message.rating);
    return commands;
  }

  /// Copy, Helpful, Not Helpful, Share and Ask Omi, with the current rating as the subtitle.
  NativeRow _actionsRow(BuildContext context, ChatMessagePlan plan, String key, ChatNativeActions actions) {
    final l10n = context.l10n;
    final commands = _commandsFor(key, plan.text, plan.message, actions);
    return NativeRow(
      'chat_actions_${key}_0',
      l10n.moreOptions,
      kind: 'menu',
      symbol: 'ellipsis',
      subtitle: switch (commands.selectedNps) {
        1 => l10n.helpful,
        -1 => l10n.notHelpful,
        _ => '',
      },
      options: {
        'copy': l10n.copyMessage,
        'helpful': l10n.helpful,
        'not_helpful': l10n.notHelpful,
        'share': l10n.share,
        'ask': l10n.askOmi,
      },
      action: (value) async {
        switch (value) {
          case 'copy':
            await commands.copy(context);
          case 'helpful':
            await commands.toggleHelpful();
          case 'not_helpful':
            if (commands.selectedNps == -1) {
              await commands.clearNotHelpful();
            } else {
              await showFeedbackBottomSheet(
                context,
                onSubmit: (reason, comment) => commands.submitNotHelpful(context, reason, comment),
              );
            }
          case 'share':
            await commands.share();
          case 'ask':
            await _ask(context, plan.text, actions.askOmi);
        }
      },
    );
  }

  List<NativeRow> _daySummaryRows(BuildContext context, ChatMessagePlan plan, String key, ChatNativeActions actions) {
    final l10n = context.l10n;
    final text = plan.text;
    final sentences = plan.showTypingIndicator ? const <String>[] : DaySummaryWidget.splitMessage(text);
    return [
      NativeRow(
        'chat_daysummary_${key}_0',
        l10n.daySummaryForDate(OmiDateFormat.of(context).date(plan.message.createdAt)),
        kind: 'label',
        symbol: 'calendar',
      ),
      if (sentences.isNotEmpty)
        NativeRow('chat_daysummary_${key}_1', '', kind: 'rich_text', blocks: [
          for (final (index, sentence) in sentences.indexed)
            {'kind': 'text', 'text': _escape(sentence), 'indent': 0, 'prefix': '${index + 1}.'},
        ]),
      if (text.isNotEmpty && !plan.showTypingIndicator)
        () {
          final commands = _commandsFor(key, text, plan.message, null);
          return NativeRow(
            'chat_actions_${key}_0',
            l10n.moreOptions,
            kind: 'menu',
            symbol: 'ellipsis',
            options: {'copy': l10n.copyMessage, 'share': l10n.share},
            action: (value) => value == 'copy' ? commands.copy(context) : commands.share(),
          );
        }(),
    ];
  }

  List<NativeRow> _citationRows(BuildContext context, ServerMessage message, String key, ChatNativeActions actions) {
    return [
      for (final (index, citation) in message.memories.indexed)
        () {
          final id = 'chat_citation_${key}_$index';
          return NativeRow(
            id,
            '${citation.structured.emoji.decodeString} ${citation.structured.title}',
            kind: 'navigation',
            symbol: _opening.contains(id) ? 'hourglass' : null,
            enabled: !_opening.contains(id),
            action: (_) {
              final current = _sessionFence();
              return openChatCitation(
                context,
                citation,
                fetchConversation: actions.fetchConversation,
                isCurrent: current,
                isLoading: () => _opening.contains(id),
                setLoading: (loading) {
                  loading ? _opening.add(id) : _opening.remove(id);
                  _changed();
                },
                updateConversation: actions.updateConversation,
                replaceCitation: (replacement) {
                  final copy = List<MessageConversation>.from(message.memories);
                  if (index >= copy.length) return;
                  copy[index] = replacement;
                  message.memories
                    ..clear()
                    ..addAll(copy);
                  _changed();
                },
              );
            },
          );
        }(),
    ];
  }

  List<NativeRow> _reviewRows(BuildContext context, ChatMessagePlan plan, String key) {
    final card = plan.reviewCard!;
    final controller = _reviews.putIfAbsent(
      key,
      () => MemoryReviewController(
        items: card.items,
        source: MemoryReviewSource.chatBlock,
        impressionKey: card.id.isNotEmpty ? card.id : plan.message.id,
        // Counted when the reply scrolls into view, not for every card in the loaded history.
        shown: false,
      )..addListener(_changed),
    )..updateItems(card.items);
    return nativeMemoryReviewRows(
      context,
      controller,
      id: (part, index) => 'chat_${part}_${key}_$index',
      header: context.l10n.memoryReviewTitle,
    );
  }

  /// The reply [key] became visible: its review card counts as shown and hydrates its memories.
  void _reviewVisible(BuildContext context, String key) {
    final controller = _reviews[key];
    if (controller == null || _disposed) return;
    controller.recordShown();
    final provider = context.mounted ? context.read<MemoriesProvider?>() : null;
    if (provider != null) controller.startHydrationIfNeeded(provider);
  }

  List<NativeRow> _blockRows(BuildContext context, ChatMessagePlan plan, String key, ChatNativeActions actions) {
    final rows = <NativeRow>[];
    final counters = <String, int>{};
    String next(String part) => 'chat_${part}_${key}_${counters.update(part, (n) => n + 1, ifAbsent: () => 0)}';
    final prose = <String>[];
    for (final entry in plan.blockEntries) {
      final component = entry.component;
      if (component == null) {
        prose.add(entry.text!);
        rows.add(_textBlockRow(next('text'), key, entry, actions));
        continue;
      }
      rows.addAll(_componentRows(context, component, plan.message, key, next, actions));
    }
    // The fallback prose keeps the Ask Omi its Flutter selection menu offers.
    if (prose.isNotEmpty) {
      final text = prose.join('\n\n');
      rows.add(NativeRow(
        'chat_ask_${key}_0',
        context.l10n.askOmi,
        symbol: 'quote.bubble',
        action: (_) => _ask(context, text, actions.askOmi),
      ));
    }
    return rows;
  }

  NativeRow _textBlockRow(String id, String key, ChatBlockEntry entry, ChatNativeActions actions) {
    final body = _richBody('$key/${entry.index}', entry.text!);
    if (body.blocks.isEmpty) return NativeRow(id, entry.text!, kind: 'label');
    return NativeRow(
      id,
      '',
      kind: 'rich_text',
      blocks: body.blocks,
      options: body.links,
      action: body.links.isEmpty ? null : (value) => _openLink(body, value, actions),
    );
  }

  List<NativeRow> _componentRows(BuildContext context, ChatContentBlock block, ServerMessage message, String key,
      String Function(String part) next, ChatNativeActions actions) {
    final l10n = context.l10n;
    switch (block) {
      case TaskCardContentBlock():
        return [_taskRow(context, block, key, next('task'))];
      case GoalLinkContentBlock():
        final id = next('goal');
        final goals = context.watch<GoalsProvider?>();
        final goal = goals?.goals.firstWhereOrNull((goal) => goal.id == block.goalId);
        if (goal == null && goals?.isLoading != true) {
          return [_unavailableRow(id, l10n.chatBlockGoal, 'flag', l10n.chatBlockUnavailable)];
        }
        return [
          NativeRow(
            id,
            block.summary.trim().isEmpty ? l10n.chatBlockGoal : block.summary,
            kind: 'navigation',
            subtitle: goal == null ? l10n.loading : l10n.chatBlockOpenInGoals,
            symbol: 'flag',
            enabled: goal != null,
            action: goal == null ? null : (_) => _openGoal(context, block, goal),
          ),
        ];
      case CaptureLinkContentBlock():
        return [_linkRow(context, next('link'), block.conversationId, block.summary, 'waveform', actions)];
      case ConversationLinkContentBlock():
        final id = next('link');
        final items = block.recommendedActionItems;
        return [
          _linkRow(context, id, block.conversationId, block.summary, 'text.alignleft', actions),
          if (items.isNotEmpty && !_unavailable.contains(id))
            NativeRow(next('linksteps'), l10n.chatBlockRecommendedNextSteps, kind: 'rich_text', blocks: [
              {'kind': 'text', 'text': '**${_escape(l10n.chatBlockRecommendedNextSteps)}**', 'indent': 0, 'prefix': ''},
              for (final item in items) {'kind': 'text', 'text': _escape(item.description), 'indent': 0, 'prefix': '•'},
            ]),
        ];
      case MemoryLinkContentBlock():
        final id = next('memory');
        final memories = context.watch<MemoriesProvider?>();
        // Memories load once per message, when Swift first shows its card: never for history alone.
        void hydrate(Object? _) {
          if (!_disposed && memories != null && _memoryHydration.add(key) && !memories.hasLoaded) {
            memories.loadMemories();
          }
        }

        final memory = memories?.memories.firstWhereOrNull((memory) => memory.id == block.memoryId);
        if (memory == null && memories?.loading != true) {
          return [
            NativeRow(id, l10n.chatBlockMemory,
                kind: 'label', subtitle: l10n.chatBlockUnavailable, symbol: 'brain', onVisible: hydrate),
          ];
        }
        return [
          NativeRow(
            id,
            block.summary.trim().isEmpty ? l10n.chatBlockMemory : block.summary,
            kind: 'navigation',
            subtitle: memory == null ? l10n.loading : l10n.chatBlockOpenInMemories,
            symbol: 'brain',
            enabled: memory != null,
            onVisible: hydrate,
            action: memory == null ? null : (_) => showMemoryDialog(context, memories!, memory: memory),
          ),
        ];
      case QuestionCardContentBlock():
        final selected = block.selectedOptionId;
        final options = selected == null ? block.options : block.options.where((o) => o.optionId == selected);
        return [
          NativeRow(next('question'), block.text,
              kind: 'label', subtitle: l10n.chatBlockQuestion, symbol: 'questionmark.circle'),
          for (final option in options)
            NativeRow(
              next('answer'),
              option.label,
              enabled: selected == null,
              action: selected == null ? (_) => actions.send(option.preparedAnswer) : null,
            ),
        ];
      case DiscoveryCardContentBlock():
        final id = next('discovery');
        final summary = block.summary.trim();
        final fullText = block.fullText.trim();
        // Expanding is only worth offering when there is more than the summary.
        final hasMore = fullText.isNotEmpty && fullText != summary;
        final expanded = _expanded.contains(id);
        return [
          NativeRow(
            id,
            block.title.trim().isEmpty ? l10n.discovery : block.title,
            kind: 'label',
            subtitle: expanded && hasMore ? fullText : summary,
            symbol: 'sparkles',
          ),
          if (hasMore)
            NativeRow(
              next('discoverymore'),
              expanded ? l10n.chatBlockShowLess : l10n.chatBlockShowMore,
              symbol: expanded ? 'chevron.up' : 'chevron.down',
              action: (_) {
                expanded ? _expanded.remove(id) : _expanded.add(id);
                _changed();
              },
            ),
        ];
      case AgentSpawnContentBlock():
        return [_agentRow(next('agent'), 'cpu', l10n.processing, block.title, block.objective)];
      case AgentCompletionContentBlock():
        final status = agentCompletionStatus(l10n, block.status);
        return [_agentRow(next('agent'), status.symbol, status.label, block.title, block.output)];
      case TextContentBlock():
      case ThinkingContentBlock():
      case ToolCallContentBlock():
      case CitationContentBlock():
      case UnknownContentBlock():
        // Not a component: an invalid row keeps the complete Flutter chat rather than dropping it.
        return [NativeRow('_unmapped_${next('block')}', '')];
    }
  }

  /// A read-only agent run: its status, title and output.
  static NativeRow _agentRow(String id, String symbol, String label, String title, String body) {
    final trimmed = title.trim();
    return NativeRow(
      id,
      trimmed.isEmpty ? label : trimmed,
      kind: 'label',
      symbol: symbol,
      subtitle: [if (trimmed.isNotEmpty) label, body.trim()].where((line) => line.isNotEmpty).join('\n'),
    );
  }

  static NativeRow _unavailableRow(String id, String title, String symbol, String message) =>
      NativeRow(id, title, kind: 'label', subtitle: message, symbol: symbol);

  /// A task card: the live task from [ActionItemsProvider], loading while the list hydrates (asked
  /// once per message) and unavailable once it has loaded without the task. Only a toggle mutates,
  /// through [ActionItemsProvider.updateActionItemState].
  NativeRow _taskRow(BuildContext context, TaskCardContentBlock block, String key, String id) {
    final l10n = context.l10n;
    final tasks = context.watch<ActionItemsProvider?>();
    if (tasks == null) return _unavailableRow(id, l10n.chatBlockTask, 'checklist', l10n.chatBlockUnavailable);
    // Tasks load once per message, when Swift first shows its card: never for history alone.
    Future<void> hydrate(Object? _) async {
      if (_disposed || !_taskHydration.add(key)) return;
      try {
        await tasks.ensureLoaded();
      } finally {
        // A failed load settles too: the card reads unavailable instead of loading forever.
        _taskHydrated.add(key);
        _changed();
      }
    }

    final item = tasks.actionItems.firstWhereOrNull((item) => item.id == block.taskId || item.taskId == block.taskId);
    if (item == null) {
      final loading = !_taskHydrated.contains(key) || tasks.isLoading;
      return NativeRow(id, l10n.chatBlockTask,
          kind: 'label',
          subtitle: loading ? l10n.loading : l10n.chatBlockUnavailable,
          symbol: 'checklist',
          onVisible: hydrate);
    }
    return NativeRow(
      id,
      item.description,
      kind: 'task',
      value: item.completed,
      subtitle: l10n.chatBlockTask,
      onVisible: hydrate,
      action: (value) async {
        if (value is! bool || !_toggling.add(id)) return;
        try {
          await tasks.updateActionItemState(item, value);
        } finally {
          _toggling.remove(id);
        }
      },
    );
  }

  /// Capture and conversation links open the conversation through the existing route. A link
  /// whose conversation is gone becomes unavailable; a session that changed meanwhile changes nothing.
  NativeRow _linkRow(BuildContext context, String id, String conversationId, String summary, String symbol,
      ChatNativeActions actions) {
    final l10n = context.l10n;
    if (_unavailable.contains(id)) {
      return _unavailableRow(id, l10n.chatBlockConversation, symbol, l10n.chatBlockUnavailable);
    }
    return NativeRow(
      id,
      summary.trim().isEmpty ? l10n.chatBlockConversation : summary,
      kind: 'navigation',
      subtitle: l10n.chatBlockOpenConversation,
      symbol: symbol,
      enabled: !_opening.contains(id),
      action: (_) async {
        if (!_opening.add(id)) return;
        _changed();
        final current = _sessionFence();
        final bool opened;
        try {
          opened = await openChatBlockConversation(
            context,
            conversationId: conversationId,
            fetchConversation: actions.fetchConversation,
            isCurrent: current,
          );
        } finally {
          _opening.remove(id);
          _changed();
        }
        if (_disposed) return;
        if (current() && !opened) _unavailable.add(id);
        _changed();
      },
    );
  }

  /// The goal's title and progress as a native alert; the Flutter goal sheet when it cannot be shown.
  Future<void> _openGoal(BuildContext context, GoalLinkContentBlock block, Goal goal) async {
    final result = await showIosNativeModal(
      context,
      title: goal.title,
      alert: true,
      cancelId: 'chat_goal_close',
      actions: [NativeRow('chat_goal_close', context.l10n.close)],
      sections: [
        NativeSection('chat_goal', [NativeRow('chat_goal_progress', formatGoalProgress(goal), kind: 'label')]),
      ],
    );
    if (result == null && context.mounted) showGoalLinkSheet(context, block, goal);
  }

  void dispose() {
    _disposed = true;
    for (final commands in _commands.values) {
      commands.dispose();
    }
    for (final review in _reviews.values) {
      review
        ..removeListener(_changed)
        ..dispose();
    }
    _commands.clear();
    _reviews.clear();
    for (final state in [
      _opening,
      _unavailable,
      _expanded,
      _toggling,
      _taskHydration,
      _taskHydrated,
      _memoryHydration
    ]) {
      state.clear();
    }
  }
}

/// Ask Omi: a native editor prefilled with [text]; the person trims it to the part they mean, and
/// the trimmed result becomes the next message's context. Cancel quotes nothing. Text the editor
/// cannot carry opens a Flutter sheet with the selectable text and its Ask Omi selection menu.
Future<void> _ask(BuildContext context, String text, void Function(String text) askOmi) async {
  final l10n = context.l10n;
  final result = await showIosNativeModal(
    context,
    title: l10n.askOmi,
    actions: [NativeRow('cancel', l10n.cancel), NativeRow('ask', l10n.askOmi)],
    sections: [
      NativeSection('chat_ask', [
        NativeRow(
          'chat_ask_text',
          l10n.askOmi,
          kind: 'text',
          value: text,
          maximumLength: min(max(text.characters.length, 10000), 262144),
        ),
      ]),
    ],
  );
  if (result == null) {
    if (context.mounted) await _askInFlutter(context, text, askOmi);
    return;
  }
  final value = result.values['chat_ask_text'];
  if (result.action != 'ask' || value is! String || value.trim().isEmpty) return;
  askOmi(value.trim());
}

Future<void> _askInFlutter(BuildContext context, String text, void Function(String text) askOmi) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.askOmi,
    builder: (sheetContext) {
      String? selectedText;
      return SingleChildScrollView(
        child: SelectionArea(
          onSelectionChanged: (selected) => selectedText = selected?.plainText,
          contextMenuBuilder: (context, state) => omiSelectionMenuBuilder(context, state, (selected) {
            Navigator.of(sheetContext).pop();
            askOmi(selected);
          }, selectedText: selectedText),
          child: SizedBox(width: double.infinity, child: getMarkdownWidget(sheetContext, text)),
        ),
      );
    },
  );
}

/// Whether the account session that asked is still the current one.
bool Function() _sessionFence() {
  final owner = AuthService.instance.captureSessionSnapshot();
  return () => owner != null && AuthService.instance.isSessionSnapshotCurrent(owner);
}

/// A symbol for an attachment, by its file extension.
String chatFileSymbol(String name) {
  final dot = name.lastIndexOf('.');
  final extension = dot < 0 ? '' : name.substring(dot + 1).toLowerCase();
  return switch (extension) {
    'pdf' => 'doc.richtext',
    'txt' || 'md' => 'doc.plaintext',
    'doc' || 'docx' => 'doc.text',
    'xls' || 'xlsx' => 'tablecells',
    'ppt' || 'pptx' => 'rectangle.on.rectangle.angled',
    _ => 'doc',
  };
}

/// A symbol for an evidence reference, by its kind.
String chatEvidenceSymbol(ChatEvidenceReferenceKind kind) => switch (kind) {
      ChatEvidenceReferenceKind.conversationSummary => 'text.alignleft',
      ChatEvidenceReferenceKind.conversationSegment => 'text.quote',
      ChatEvidenceReferenceKind.screen => 'desktopcomputer',
      ChatEvidenceReferenceKind.keyframe => 'photo',
      ChatEvidenceReferenceKind.request || ChatEvidenceReferenceKind.unknown => 'link',
    };

/// Literal text inside a rich block, which Swift reads as inline Markdown.
String _escape(String text) => text.replaceAllMapped(RegExp(r'[\\`*_\[\]]'), (match) => '\\${match[0]}');

/// A reply body as native blocks plus its link whitelist. A body the native renderer cannot
/// represent (an image it cannot load, or more blocks than one reply carries) becomes literal text,
/// so real-world Markdown never makes the transcript invalid.
class _RichBody {
  _RichBody(this.source, this.blocks, this.links);

  factory _RichBody.parse(String source) {
    final blocks = [
      for (final block in nativeRichText(source))
        if (block['kind'] == 'image' && nativeImageUri(block['uri'] as String) == null)
          {'kind': 'text', 'text': _escape(block['text'] as String), 'indent': block['indent']!, 'prefix': ''}
        else
          block,
    ];
    final links = {
      for (final entry in nativeRichTextLinks(source).entries)
        if (entry.key.isNotEmpty) entry.key: entry.value,
    };
    final valid = NativeRow('body', source, kind: 'message_ai', blocks: blocks, options: links).valid;
    return valid ? _RichBody(source, blocks, links) : _RichBody(source, const [], const {});
  }

  final String source;
  final List<Map<String, Object>> blocks;
  final Map<String, String> links;
}

/// The plans sheet the chat opens when the chat quota runs out. Natively, [PlansSheet] projects its
/// own surface, with its own close row, and the hero animations stay stopped beneath it; a surface
/// that falls back gets the Flutter sheet scaffold and its close control back. Plans the projection
/// cannot map keep [PlansSheet]'s complete classic body, which closes by drag or the scrim.
Future<void> showChatQuotaPlansSheet(BuildContext context) => showOmiSheet<void>(
      context: context,
      padding: EdgeInsets.zero,
      builder: (_) => const _QuotaPlansSheet(),
      nativeBuilder: (_) => TickerMode(
        enabled: false,
        child: NativeNavigationChrome(
          wrapFallback: (fallback) => OmiSheetScaffold(padding: EdgeInsets.zero, child: fallback),
          child: const _QuotaPlansSheet(),
        ),
      ),
    );

class _QuotaPlansSheet extends StatefulWidget {
  const _QuotaPlansSheet();

  @override
  State<_QuotaPlansSheet> createState() => _QuotaPlansSheetState();
}

class _QuotaPlansSheetState extends State<_QuotaPlansSheet> with TickerProviderStateMixin {
  late AnimationController _waveController;
  late AnimationController _arrowController;
  late AnimationController _notesController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
    _arrowController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat();
    _notesController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();
    _arrowAnimation = Tween<double>(begin: 0, end: 10).animate(
      CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _waveController,
      notesController: _notesController,
      arrowController: _arrowController,
      arrowAnimation: _arrowAnimation,
    );
  }
}
