import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/services/experiments/home_redesign.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/chat/widgets/chat_entrance.dart';
import 'package:omi/pages/chat/widgets/typing_indicator.dart';
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

/// Omi's first chat message: shown in the empty chat until the person sends their first message,
/// typed in the first time it appears. Remembered per account.
abstract final class ChatWelcome {
  static String _key(String uid) => 'chat/welcome/$uid';

  /// Still to be answered: the person has not sent a chat message since it was introduced.
  /// Only in the redesigned Home (home-redesign experiment); today's chat opens as before.
  static bool get pending =>
      HomeRedesign.on && SharedPreferencesUtil().getString(_key(SharedPreferencesUtil().uid)) != 'done';

  /// It has been typed in once; later visits show it settled.
  static bool get shown => SharedPreferencesUtil().getString(_key(SharedPreferencesUtil().uid)) != '';

  static void markShown() {
    if (!shown) SharedPreferencesUtil().saveString(_key(SharedPreferencesUtil().uid), 'shown');
  }

  static void markDone() => SharedPreferencesUtil().saveString(_key(SharedPreferencesUtil().uid), 'done');
}

class ChatGreeting extends StatelessWidget {
  const ChatGreeting({
    super.key,
    required this.isConnected,
    this.name = '',
    this.hour,
    this.todayCount,
    this.welcome = false,
    this.animateWelcome = true,
  });
  final bool isConnected;
  final String name;
  final int? hour;
  final int? todayCount;

  /// Show Omi's welcome message in place of "What do you want to know?".
  final bool welcome;

  /// Type the welcome in (the first time); otherwise it appears settled.
  final bool animateWelcome;

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
            if (welcome)
              _WelcomeMessage(text: l10n.chatWelcomeMessage, animate: animateWelcome)
            else
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

/// Omi "texting" its first message: the typing dots, then the words arriving like a streamed reply,
/// in the same plain style as Omi's chat answers.
class _WelcomeMessage extends StatefulWidget {
  const _WelcomeMessage({required this.text, required this.animate});

  final String text;
  final bool animate;

  @override
  State<_WelcomeMessage> createState() => _WelcomeMessageState();
}

class _WelcomeMessageState extends State<_WelcomeMessage> {
  late final List<String> _words = widget.text.split(' ');
  late int _shown = widget.animate ? 0 : _words.length;
  bool _typing = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (!widget.animate) return;
    _typing = true;
    _timer = Timer(const Duration(milliseconds: 1300), () {
      if (!mounted) return;
      setState(() => _typing = false);
      // omi-perf-allow: fast-periodic-timer -- one-shot reveal of the first chat message (~2 s), setState local to this small widget
      _timer = Timer.periodic(const Duration(milliseconds: 45), (timer) {
        if (!mounted) return timer.cancel();
        setState(() => _shown++);
        if (_shown >= _words.length) {
          timer.cancel();
          ChatWelcome.markShown();
        }
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final shown = reduceMotion ? _words.length : _shown;
    if (_typing && !reduceMotion) {
      return const Padding(
        key: Key('chat_welcome_typing'),
        padding: EdgeInsets.symmetric(vertical: OmiSpacing.sm),
        child: Row(mainAxisSize: MainAxisSize.min, children: [TypingIndicator()]),
      );
    }
    return Semantics(
      liveRegion: true,
      label: widget.text,
      excludeSemantics: true,
      child: Text(
        // The whole message lays out from the start, so lines don't jump as words arrive.
        widget.text,
        key: const Key('chat_welcome_message'),
        style: OmiType.body.copyWith(height: 1.45, color: OmiColors.textPrimary),
      ).revealedUpTo(shown, _words),
    );
  }
}

extension on Text {
  /// The same text, with the words after [count] drawn transparent so the layout never shifts.
  Widget revealedUpTo(int count, List<String> words) {
    if (count >= words.length) return this;
    final visible = words.take(count).join(' ');
    final hidden = words.skip(count).join(' ');
    return Text.rich(
      key: key,
      TextSpan(
        style: style,
        children: [
          TextSpan(text: visible),
          TextSpan(text: count == 0 ? hidden : ' $hidden', style: const TextStyle(color: Colors.transparent)),
        ],
      ),
    );
  }
}
