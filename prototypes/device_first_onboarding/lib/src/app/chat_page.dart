import 'package:flutter/material.dart';

import '../theme.dart';
import 'app_state.dart';
import 'app_widgets.dart';
import 'mock_data.dart';

class _Message {
  const _Message(this.fromUser, this.text, [this.source]);

  final bool fromUser;
  final String text;
  final String? source;
}

/// "Ask Omi": chat over everything Omi has heard. Answers are canned.
class ChatPage extends StatefulWidget {
  const ChatPage({super.key, this.initialQuestion});

  /// Ask this straight away (screenshots of an answered chat).
  final String? initialQuestion;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final TextEditingController _input = TextEditingController();
  final List<_Message> _messages = <_Message>[];

  @override
  void initState() {
    super.initState();
    final q = widget.initialQuestion;
    if (q != null) _messages.addAll(_exchange(q));
  }

  static List<_Message> _exchange(String q) =>
      <_Message>[_Message(true, q), _Message(false, MockData.answerFor(q), MockData.sourceFor(q))];

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  void _ask(String question) {
    final q = question.trim();
    if (q.isEmpty) return;
    setState(() {
      _messages.addAll(_exchange(q));
      _input.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    return AppPage(
      title: 'Ask Omi',
      actions: <Widget>[
        IconButton(
          tooltip: 'New chat',
          onPressed: () => setState(_messages.clear),
          icon: Icon(Icons.edit_square, size: 20, color: t.text),
        ),
      ],
      bottom: Padding(
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
        child: Container(
          padding: const EdgeInsets.only(left: 18, right: 6),
          decoration: BoxDecoration(
            color: t.surface,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: t.border),
          ),
          child: Row(
            children: <Widget>[
              Expanded(
                child: TextField(
                  controller: _input,
                  cursorColor: t.accent,
                  style: t.label(),
                  onSubmitted: _ask,
                  decoration: InputDecoration(
                    border: InputBorder.none,
                    hintText: 'Ask anything',
                    hintStyle: t.label(color: t.textTertiary),
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Send',
                onPressed: () => _ask(_input.text),
                icon: Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(color: t.accent, shape: BoxShape.circle),
                  child: Icon(Icons.arrow_upward, size: 18, color: t.onAccent),
                ),
              ),
            ],
          ),
        ),
      ),
      children: _messages.isEmpty
          ? <Widget>[
              const SizedBox(height: 48),
              Center(child: _Glow(t: t)),
              const SizedBox(height: 22),
              Text('Hi ${state.userName}', textAlign: TextAlign.center, style: t.headline(34)),
              const SizedBox(height: 6),
              Text(
                'What do you want to know?',
                textAlign: TextAlign.center,
                style: t.body(size: 16, color: t.textTertiary),
              ),
              const SizedBox(height: 28),
              for (final s in MockData.chatSuggestions)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Center(child: AppChip(s, onTap: () => _ask(s))),
                ),
            ]
          : <Widget>[
              for (final m in _messages) _Bubble(message: m),
            ],
    );
  }
}

class _Glow extends StatelessWidget {
  const _Glow({required this.t});

  final DfTheme t;

  @override
  Widget build(BuildContext context) {
    final glow = t.glow;
    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: glow == null ? t.surface2 : null,
        gradient: glow == null ? null : LinearGradient(colors: glow),
      ),
      child: Icon(Icons.auto_awesome, color: glow == null ? t.text : Colors.white),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final _Message message;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final source = message.source;
    if (message.fromUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(left: 56, bottom: 14),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(color: t.surface2, borderRadius: BorderRadius.circular(18)),
          child: Text(message.text, style: t.label()),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 18, right: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(message.text, style: t.body(size: 16, color: t.text, height: 1.5)),
          if (source != null) ...<Widget>[
            const SizedBox(height: 10),
            Row(
              children: <Widget>[
                Icon(Icons.link, size: 14, color: t.textTertiary),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    source,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: t.body(size: 12, color: t.textTertiary),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
