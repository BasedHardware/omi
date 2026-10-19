import 'package:flutter/material.dart';

import '../content.dart';
import '../theme.dart';
import '../widgets.dart';
import 'app_state.dart';
import 'app_widgets.dart';
import 'mock_data.dart';

/// Conversation detail: Summary / Transcript.
class ConversationPage extends StatefulWidget {
  const ConversationPage({super.key, required this.conversation, this.initialTab = 0});

  final MockConversation conversation;
  final int initialTab;

  @override
  State<ConversationPage> createState() => _ConversationPageState();
}

class _ConversationPageState extends State<ConversationPage> {
  late int _tab = widget.initialTab;
  final Set<int> _done = <int>{};
  bool? _helpful;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final today = OmiAppScope.of(context).today;
    final c = widget.conversation;
    return AppPage(
      title: '',
      actions: <Widget>[
        IconButton(
          tooltip: 'Share',
          onPressed: () => dfNotInPrototype(context, 'Sharing'),
          icon: Icon(Icons.ios_share, size: 20, color: t.text),
        ),
        IconButton(
          tooltip: 'More',
          onPressed: () => dfNotInPrototype(context, 'This menu'),
          icon: Icon(Icons.more_horiz, color: t.text),
        ),
      ],
      children: <Widget>[
        Row(children: <Widget>[AppIconTile(icon: c.icon, size: 52)]),
        const SizedBox(height: 14),
        Text(c.title, style: t.headline(28)),
        const SizedBox(height: 6),
        Text(
          '${appDayLabel(c.start, today)} · ${c.timeAndLength}',
          style: t.body(size: 14, color: t.textTertiary),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            AppChip(c.category),
            AppChip('Private', icon: Icons.lock_outline, onTap: () => dfNotInPrototype(context, 'Sharing settings')),
            if (c.starred) const AppChip('Starred', icon: Icons.star_rounded),
          ],
        ),
        const SizedBox(height: 18),
        DfSegmented(
            labels: const <String>['Summary', 'Transcript'], index: _tab, onChanged: (i) => setState(() => _tab = i)),
        const SizedBox(height: 18),
        if (_tab == 0) ..._summary(t, c) else ..._transcript(t, c),
      ],
    );
  }

  List<Widget> _summary(DfTheme t, MockConversation c) => <Widget>[
        Text('Overview', style: t.label(size: 17, weight: FontWeight.w600)),
        const SizedBox(height: 6),
        Text(c.overview, style: t.body(size: 16, color: t.text, height: 1.5)),
        if (c.actionItems.isNotEmpty) ...<Widget>[
          const SizedBox(height: 22),
          Text('Action items', style: t.label(size: 17, weight: FontWeight.w600)),
          const SizedBox(height: 4),
          for (var i = 0; i < c.actionItems.length; i++)
            Semantics(
              checked: _done.contains(i),
              label: c.actionItems[i],
              child: InkWell(
                onTap: () => setState(() => _done.contains(i) ? _done.remove(i) : _done.add(i)),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: ExcludeSemantics(
                    child: Row(
                      children: <Widget>[
                        Icon(
                          _done.contains(i) ? Icons.check_circle : Icons.radio_button_unchecked,
                          size: 22,
                          color: _done.contains(i) ? t.text : t.textTertiary,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            c.actionItems[i],
                            style: t.label(color: _done.contains(i) ? t.textTertiary : t.text).copyWith(
                                  decoration: _done.contains(i) ? TextDecoration.lineThrough : null,
                                ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
        const SizedBox(height: 22),
        Text('Speakers', style: t.label(size: 17, weight: FontWeight.w600)),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[for (final p in c.participants) AppChip(p, icon: Icons.person_outline)],
        ),
        const SizedBox(height: 28),
        DfCard(
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
          child: Row(
            children: <Widget>[
              Expanded(child: Text('Was this helpful?', style: t.label(size: 14))),
              IconButton(
                tooltip: 'Helpful',
                onPressed: () => setState(() => _helpful = true),
                icon: Icon(_helpful == true ? Icons.thumb_up : Icons.thumb_up_outlined, size: 20, color: t.text),
              ),
              IconButton(
                tooltip: 'Not helpful',
                onPressed: () => setState(() => _helpful = false),
                icon: Icon(_helpful == false ? Icons.thumb_down : Icons.thumb_down_outlined, size: 20, color: t.text),
              ),
            ],
          ),
        ),
      ];

  List<Widget> _transcript(DfTheme t, MockConversation c) {
    if (c.transcript.isEmpty) {
      return <Widget>[
        Padding(
          padding: const EdgeInsets.only(top: 24),
          child: Text('No transcript for this sample.', textAlign: TextAlign.center, style: t.body(size: 14)),
        ),
      ];
    }
    return <Widget>[
      for (final line in c.transcript)
        Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Text(
                    line.speaker,
                    style: t.label(
                      size: 13,
                      weight: FontWeight.w600,
                      color: line.speaker == 'You' ? t.text : (t.glow?.first ?? t.textSecondary),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(line.offset, style: t.body(size: 12, color: t.textTertiary)),
                ],
              ),
              const SizedBox(height: 3),
              Text(line.text, style: t.body(size: 16, color: t.text, height: 1.45)),
            ],
          ),
        ),
    ];
  }
}

/// Daily recap: the day in a headline, stats, highlights and conversations.
class RecapPage extends StatelessWidget {
  const RecapPage({super.key, required this.recap});

  final MockRecap recap;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final day = state.data.conversations.where((c) => dfDayDiff(c.start, recap.day) == 0).toList();
    return AppPage(
      title: 'Daily Recap',
      children: <Widget>[
        Text(dfDayDate(recap.day).toUpperCase(), style: t.eyebrow()),
        const SizedBox(height: 6),
        Text(recap.headline, style: t.headline(32)),
        const SizedBox(height: 18),
        Row(
          children: <Widget>[
            Expanded(child: StatTile(value: '${recap.conversations}', label: 'Conversations')),
            const SizedBox(width: 10),
            Expanded(child: StatTile(value: '${recap.minutes}', label: 'Minutes')),
            const SizedBox(width: 10),
            Expanded(child: StatTile(value: '${recap.tasks}', label: 'Tasks')),
          ],
        ),
        const SizedBox(height: 22),
        Text('Highlights', style: t.label(size: 17, weight: FontWeight.w600)),
        const SizedBox(height: 8),
        for (final h in recap.highlights)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.only(top: 7),
                  child: Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(color: t.glow?.first ?? t.text, shape: BoxShape.circle),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(child: Text(h, style: t.body(size: 16, color: t.text, height: 1.45))),
              ],
            ),
          ),
        if (day.isNotEmpty) ...<Widget>[
          const SizedBox(height: 12),
          Text('Conversations', style: t.label(size: 17, weight: FontWeight.w600)),
          const SizedBox(height: 4),
          for (final c in day)
            ConversationRow(
              conversation: c,
              onTap: () => pushDf<void>(context, (_) => ConversationPage(conversation: c)),
            ),
        ],
      ],
    );
  }
}
