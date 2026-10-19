import 'package:flutter/material.dart';

import '../theme.dart';
import '../widgets.dart';
import 'app_state.dart';
import 'app_widgets.dart';
import 'conversation_page.dart';
import 'mock_data.dart';

/// Global search with Starred / Recaps / Memories / People filters.
class SearchPage extends StatefulWidget {
  const SearchPage({super.key});

  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  static const List<(String, IconData)> _filters = <(String, IconData)>[
    ('Starred', Icons.star_outline_rounded),
    ('Recaps', Icons.wb_twilight),
    ('Memories', Icons.psychology_outlined),
    ('People', Icons.person_outline),
  ];

  String _query = '';
  String? _filter;

  bool _matches(String text) => _query.isEmpty || text.toLowerCase().contains(_query.toLowerCase());

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final data = OmiAppScope.of(context).data;
    final results = <Widget>[];
    switch (_filter) {
      case 'Recaps':
        for (final r in data.recaps.where((r) => _matches(r.headline))) {
          results.add(
            DfListRow(
              icon: Icons.wb_twilight,
              label: r.headline,
              value: appDayLabel(r.day, data.today),
              onTap: () => pushDf<void>(context, (_) => RecapPage(recap: r)),
            ),
          );
        }
      case 'Memories':
        for (final m in MockData.memories.where((m) => _matches(m.text))) {
          results.add(DfListRow(icon: Icons.psychology_outlined, label: m.text));
        }
      case 'People':
        final people = <String>{for (final c in data.conversations) ...c.participants}..remove('You');
        for (final p in people.where(_matches)) {
          final count = data.conversations.where((c) => c.participants.contains(p)).length;
          results.add(DfListRow(icon: Icons.person_outline, label: p, value: '$count conversations'));
        }
      default:
        for (final c in data.conversations) {
          if (_filter == 'Starred' && !c.starred) continue;
          if (!_matches('${c.title} ${c.overview}')) continue;
          results.add(
            ConversationRow(
              conversation: c,
              onTap: () => pushDf<void>(context, (_) => ConversationPage(conversation: c)),
            ),
          );
        }
    }
    return AppPage(
      title: 'Search',
      children: <Widget>[
        DfSearchField(hint: 'Search conversations', onChanged: (q) => setState(() => _query = q)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            for (final (label, icon) in _filters)
              AppChip(
                label,
                icon: icon,
                selected: _filter == label,
                onTap: () => setState(() => _filter = _filter == label ? null : label),
              ),
          ],
        ),
        const SizedBox(height: 14),
        if (results.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 32),
            child: Text('Nothing matches “$_query”', textAlign: TextAlign.center, style: t.body(size: 14)),
          )
        else if (_filter == null || _filter == 'Starred')
          ...results
        else
          DfCard(child: Column(children: results)),
      ],
    );
  }
}
