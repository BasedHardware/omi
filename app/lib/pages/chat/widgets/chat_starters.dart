import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/chat/widgets/chat_entrance.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

int countConversationsForLocalDay(Iterable<ServerConversation> conversations, DateTime day) {
  final localDay = day.toLocal();
  return conversations.where((conversation) {
    final at = (conversation.startedAt ?? conversation.createdAt).toLocal();
    return !conversation.discarded && at.year == localDay.year && at.month == localDay.month && at.day == localDay.day;
  }).length;
}

class ChatGreeting extends StatelessWidget {
  const ChatGreeting({super.key, required this.isConnected, this.name = '', this.hour, this.todayCount});
  final bool isConnected;
  final String name;
  final int? hour;
  final int? todayCount;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (!isConnected) return Center(child: Text(l10n.noInternetConnection, textAlign: TextAlign.center));
    final h = hour ?? DateTime.now().hour;
    final greeting = h < 12
        ? l10n.greetingMorning
        : h < 18
            ? l10n.greetingAfternoon
            : l10n.greetingEvening;
    final heading = OmiType.title1.copyWith(fontWeight: FontWeight.w600, letterSpacing: -0.7, height: 1.2);
    final hello = name.trim().isEmpty ? greeting : l10n.greetingWithName(greeting, name.trim());
    final count = todayCount ??
        context.select<ConversationProvider?, int>(
          (provider) => countConversationsForLocalDay(provider?.conversations ?? const [], DateTime.now()),
        );
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(18, 28, 18, OmiSpacing.md),
      child: SizedBox(
        width: double.infinity,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ChatRise(
              key: const Key('chat_greeting_rise'),
              child: Semantics(header: true, child: Text('$hello.', style: heading)),
            ),
            // "No conversations today." is a status line, not a greeting, and reads wrong early in
            // the day; the count line appears only once there is something to count.
            if (count > 0)
              ChatRise(
                key: const Key('chat_count_rise'),
                interval: ChatIntro.countLine,
                child: _ConversationCount(count: count, style: heading),
              ),
            const SizedBox(height: 10),
            ChatRise(
              key: const Key('chat_question_rise'),
              interval: ChatIntro.question,
              child: Text(
                l10n.whatDoYouWantToKnow,
                style: OmiType.title3.copyWith(
                  fontWeight: FontWeight.w500,
                  letterSpacing: -0.2,
                  height: 1.2,
                  color: OmiColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ConversationCount extends StatelessWidget {
  const _ConversationCount({required this.count, required this.style});
  final int count;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final animation = ChatEntrance.animationOf(context);
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    Widget label(double progress) => Text(
          l10n.conversationsTodayCount((count * progress).round()),
          key: const Key('chat_today_count'),
          style: style.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
        );
    return Semantics(
      label: l10n.conversationsTodayCount(count),
      excludeSemantics: true,
      child: animation == null || reduceMotion
          ? label(1)
          : AnimatedBuilder(
              animation: animation,
              builder: (context, _) => label(ChatIntro.countProgress(animation.value)),
            ),
    );
  }
}

/// Selecting a question fills the draft. Sending remains an explicit action.
class ChatSuggestions extends StatelessWidget {
  const ChatSuggestions({
    super.key,
    required this.hasExistingData,
    required this.isConnected,
    required this.onSelected,
  });
  final bool hasExistingData;
  final bool isConnected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    if (!isConnected) return const SizedBox.shrink();
    final l10n = context.l10n;
    final prompts = hasExistingData
        ? {'decide': l10n.askSuggestDecide, 'owe': l10n.askSuggestOwe, 'notice': l10n.askSuggestNotice}
        : {'capabilities': l10n.chatStarterPrompt('capabilities'), 'goal': l10n.chatStarterPrompt('goal')};
    return LayoutBuilder(
      builder: (context, constraints) => ChatRise(
        interval: ChatIntro.suggestions,
        fadeOnly: true,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
          child: Row(
            children: [
              for (final prompt in prompts.entries)
                Padding(
                  padding: const EdgeInsetsDirectional.only(end: OmiSpacing.xs),
                  child: OutlinedButton(
                    key: ValueKey('chat_starter_${prompt.key}'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: OmiColors.textPrimary,
                      minimumSize: const Size(44, 44),
                      maximumSize: Size(constraints.maxWidth - OmiSpacing.md * 2, double.infinity),
                      side: BorderSide(color: OmiColors.border),
                      shape: const StadiumBorder(),
                    ),
                    onPressed: () => onSelected(prompt.value),
                    child: Text(prompt.value, style: OmiType.callout),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
