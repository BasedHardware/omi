import 'package:flutter/material.dart';

import '../content.dart';
import '../theme.dart';
import '../widgets.dart';
import 'app_state.dart';
import 'app_widgets.dart';
import 'chat_page.dart';
import 'conversation_page.dart';
import 'mock_data.dart';
import 'search_page.dart';
import 'settings_pages.dart';
import 'upgrade_page.dart';

/// The Omi app after onboarding, in the current [DfTheme].
///
/// Owns its own navigator so pushed pages share [OmiAppScope].
class OmiApp extends StatefulWidget {
  const OmiApp({
    super.key,
    required this.plan,
    this.userName = 'Alex',
    required this.today,
    this.home,
    this.onExit,
  });

  final DfPlanState plan;
  final String userName;
  final DateTime today;

  /// Open on this page instead of home (used by the launcher and screenshots).
  final WidgetBuilder? home;
  final VoidCallback? onExit;

  @override
  State<OmiApp> createState() => _OmiAppState();
}

class _OmiAppState extends State<OmiApp> {
  late final OmiAppState _state = OmiAppState(plan: widget.plan, userName: widget.userName, today: widget.today);

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final home = widget.home;
    return OmiAppScope(
      state: _state,
      child: DfStatusBar(
        child: Navigator(
          onGenerateRoute: (_) => MaterialPageRoute<void>(
            builder: (context) => home == null ? AppHome(onExit: widget.onExit) : home(context),
          ),
        ),
      ),
    );
  }
}

/// Home: top bar, Home / Tasks tabs, and the floating "Ask Omi" bar.
class AppHome extends StatefulWidget {
  const AppHome({super.key, this.initialTab = 0, this.onExit});

  final int initialTab;
  final VoidCallback? onExit;

  @override
  State<AppHome> createState() => _AppHomeState();
}

class _AppHomeState extends State<AppHome> {
  late int _tab = widget.initialTab;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final onExit = widget.onExit;
    return Scaffold(
      backgroundColor: t.background,
      body: DecoratedBox(
        decoration: BoxDecoration(gradient: t.wash),
        child: SafeArea(
          bottom: false,
          child: Stack(
            children: <Widget>[
              Column(
                children: <Widget>[
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 6, 6, 0),
                    child: Row(
                      children: <Widget>[
                        const _DevicePill(),
                        const Spacer(),
                        if (onExit != null)
                          IconButton(
                            tooltip: 'Back to launcher',
                            onPressed: onExit,
                            icon: Icon(Icons.close, color: t.textTertiary),
                          ),
                        IconButton(
                          tooltip: 'Calendar',
                          onPressed: () => dfNotInPrototype(context, 'The calendar'),
                          icon: Icon(Icons.calendar_today_outlined, size: 21, color: t.text),
                        ),
                        IconButton(
                          tooltip: 'Search',
                          onPressed: () => pushDf<void>(context, (_) => const SearchPage()),
                          icon: Icon(Icons.search, color: t.text),
                        ),
                        IconButton(
                          tooltip: 'Settings',
                          onPressed: () => pushDf<void>(context, (_) => const SettingsPage()),
                          icon: Icon(Icons.settings_outlined, color: t.text),
                        ),
                      ],
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 4, 20, 8),
                    child: Row(
                      children: <Widget>[
                        _TabLabel('Home', selected: _tab == 0, onTap: () => setState(() => _tab = 0)),
                        const SizedBox(width: 18),
                        _TabLabel('Tasks', selected: _tab == 1, onTap: () => setState(() => _tab = 1)),
                      ],
                    ),
                  ),
                  Expanded(child: _tab == 0 ? const HomeTab() : const TasksTab()),
                ],
              ),
              const Positioned(left: 16, right: 16, bottom: 0, child: SafeArea(top: false, child: _AskBar())),
            ],
          ),
        ),
      ),
    );
  }
}

class _TabLabel extends StatelessWidget {
  const _TabLabel(this.label, {required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Semantics(
      button: true,
      selected: selected,
      child: GestureDetector(
        onTap: onTap,
        child: Text(label, style: t.headline(30).copyWith(color: selected ? t.text : t.textTertiary)),
      ),
    );
  }
}

class _DevicePill extends StatelessWidget {
  const _DevicePill();

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Semantics(
      button: true,
      label: 'Omi, connected, 82% battery',
      child: GestureDetector(
        onTap: () => pushDf<void>(context, (_) => const DevicePage()),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: t.surface,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: t.border),
          ),
          child: ExcludeSemantics(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: t.success, shape: BoxShape.circle),
                ),
                const SizedBox(width: 7),
                Text('Omi', style: t.label(size: 13, weight: FontWeight.w600)),
                const SizedBox(width: 6),
                Icon(Icons.battery_5_bar_rounded, size: 15, color: t.textSecondary),
                Text('82%', style: t.label(size: 13, color: t.textSecondary)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AskBar extends StatelessWidget {
  const _AskBar();

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final shadow = <BoxShadow>[
      BoxShadow(color: Colors.black.withValues(alpha: 0.10), blurRadius: 18, offset: const Offset(0, 6))
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Semantics(
              button: true,
              label: 'Ask Omi',
              child: GestureDetector(
                onTap: () => pushDf<void>(context, (_) => const ChatPage()),
                child: Container(
                  height: 54,
                  padding: const EdgeInsets.symmetric(horizontal: 18),
                  decoration: BoxDecoration(
                    color: t.surface,
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(color: t.border),
                    boxShadow: shadow,
                  ),
                  child: ExcludeSemantics(
                    child: Row(
                      children: <Widget>[
                        Icon(Icons.auto_awesome, size: 18, color: t.glow?.first ?? t.text),
                        const SizedBox(width: 10),
                        Expanded(child: Text('Ask Omi', style: t.label(color: t.textTertiary))),
                        Icon(Icons.mic_none_rounded, color: t.textSecondary),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Tooltip(
            message: state.listening ? 'Pause listening' : 'Resume listening',
            child: Semantics(
              button: true,
              label: state.listening ? 'Pause listening' : 'Resume listening',
              child: GestureDetector(
                onTap: state.toggleListening,
                child: Container(
                  width: 54,
                  height: 54,
                  decoration: BoxDecoration(color: t.accent, shape: BoxShape.circle, boxShadow: shadow),
                  child: Icon(
                    state.listening ? Icons.pause_rounded : Icons.fiber_manual_record_rounded,
                    color: state.listening ? t.onAccent : t.danger,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Home feed: capture card, daily recaps, conversations by day.
class HomeTab extends StatelessWidget {
  const HomeTab({super.key});

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final data = state.data;
    final free = !state.unlimited;

    // Free keeps the last two days; older conversations are locked.
    final visible = <MockConversation>[];
    var locked = 0;
    for (final c in data.conversations) {
      if (free && dfDayDiff(data.today, c.start) > 1) {
        locked++;
      } else {
        visible.add(c);
      }
    }
    final groups = <String, List<MockConversation>>{};
    for (final c in visible) {
      groups.putIfAbsent(appDayLabel(c.start, data.today), () => <MockConversation>[]).add(c);
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 110),
      children: <Widget>[
        const _CaptureCard(),
        if (free) ...<Widget>[
          const SizedBox(height: 12),
          DfCard(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(child: Text('Free plan', style: t.label(weight: FontWeight.w600))),
                    GestureDetector(
                      onTap: () => showUpgrade(context),
                      child: Text('Upgrade', style: t.label(size: 14, weight: FontWeight.w600, color: t.glow?.first)),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                const UsageBar(used: MockData.usedMinutes, limit: MockData.freeMinutes),
              ],
            ),
          ),
        ],
        const SizedBox(height: 18),
        DfSectionTitle(
          'Daily Recaps',
          trailing: GestureDetector(
            onTap: () => pushDf<void>(context, (_) => RecapPage(recap: data.recaps.first)),
            child: Text('View All', style: t.label(size: 13, weight: FontWeight.w600)),
          ),
        ),
        const SizedBox(height: 6),
        SizedBox(
          height: 118,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: data.recaps.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (context, i) => _RecapCard(recap: data.recaps[i]),
          ),
        ),
        for (final entry in groups.entries) ...<Widget>[
          const SizedBox(height: 14),
          DfSectionTitle(entry.key),
          for (final c in entry.value)
            ConversationRow(
              conversation: c,
              onTap: () => pushDf<void>(context, (_) => ConversationPage(conversation: c)),
            ),
        ],
        if (locked > 0) ...<Widget>[
          const SizedBox(height: 14),
          _LockedCard(count: locked),
        ],
      ],
    );
  }
}

class _CaptureCard extends StatelessWidget {
  const _CaptureCard();

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final listening = state.listening;
    return DfCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: listening ? t.danger : t.textTertiary, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  listening ? 'Listening' : 'Paused',
                  style: t.label(size: 14, weight: FontWeight.w600),
                ),
              ),
              Text(listening ? 'Live Transcript' : 'Tap record to resume',
                  style: t.body(size: 12, color: t.textTertiary)),
            ],
          ),
          const SizedBox(height: 10),
          if (listening) ...<Widget>[
            Text.rich(
              TextSpan(
                children: <InlineSpan>[
                  TextSpan(text: 'Maya  ', style: t.label(size: 13, weight: FontWeight.w600, color: t.glow?.first)),
                  TextSpan(text: 'Then support gets the walkthrough Monday.', style: t.body(size: 14, color: t.text)),
                ],
              ),
            ),
            const SizedBox(height: 4),
            Text.rich(
              TextSpan(
                children: <InlineSpan>[
                  TextSpan(text: 'You  ', style: t.label(size: 13, weight: FontWeight.w600)),
                  TextSpan(text: 'Great, I’ll send the deck Friday…', style: t.body(size: 14, color: t.textTertiary)),
                ],
              ),
            ),
          ] else
            Text('Omi is not capturing right now.', style: t.body(size: 14)),
        ],
      ),
    );
  }
}

class _RecapCard extends StatelessWidget {
  const _RecapCard({required this.recap});

  final MockRecap recap;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final today = OmiAppScope.of(context).today;
    return GestureDetector(
      onTap: () => pushDf<void>(context, (_) => RecapPage(recap: recap)),
      child: SizedBox(
        width: 200,
        child: DfCard(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(appDayLabel(recap.day, today), style: t.eyebrow()),
              const SizedBox(height: 6),
              Text(recap.headline, maxLines: 2, overflow: TextOverflow.ellipsis, style: t.headline(19)),
              const Spacer(),
              Text(
                '${recap.conversations} conversations · ${recap.minutes} min',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: t.body(size: 12, color: t.textTertiary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LockedCard extends StatelessWidget {
  const _LockedCard({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        children: <Widget>[
          Icon(Icons.lock_outline_rounded, color: t.textSecondary),
          const SizedBox(height: 8),
          Text(
            '$count older conversations are locked',
            textAlign: TextAlign.center,
            style: t.label(weight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            'Free keeps the last two days. Unlimited keeps everything, forever.',
            textAlign: TextAlign.center,
            style: t.body(size: 13, color: t.textTertiary),
          ),
          const SizedBox(height: 14),
          DfButton('Upgrade to Unlimited', onPressed: () => showUpgrade(context)),
        ],
      ),
    );
  }
}

/// Tasks: grouped by due date, tap to complete, "New task" sheet.
class TasksTab extends StatelessWidget {
  const TasksTab({super.key});

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final today = state.today;
    final sections = <String, List<MockTask>>{
      'Overdue': <MockTask>[],
      'Today': <MockTask>[],
      'Tomorrow': <MockTask>[],
      'Later': <MockTask>[],
      'No Deadline': <MockTask>[],
    };
    for (final task in state.data.tasks) {
      final due = task.due;
      final key = due == null
          ? 'No Deadline'
          : switch (dfDayDiff(due, today)) {
              < 0 => 'Overdue',
              0 => 'Today',
              1 => 'Tomorrow',
              _ => 'Later',
            };
      sections[key]!.add(task);
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 110),
      children: <Widget>[
        Align(
          alignment: Alignment.centerLeft,
          child: AppChip('New Task', icon: Icons.add, onTap: () => showNewTaskSheet(context)),
        ),
        for (final entry in sections.entries)
          if (entry.value.isNotEmpty) ...<Widget>[
            const SizedBox(height: 14),
            DfSectionTitle(entry.key),
            for (final task in entry.value)
              _TaskRow(task: task, overdue: entry.key == 'Overdue', onToggle: () => state.toggleTask(task)),
          ],
        if (state.data.tasks.every((task) => task.done))
          Padding(
            padding: const EdgeInsets.only(top: 40),
            child: Text('All done.', textAlign: TextAlign.center, style: t.headline(24)),
          ),
      ],
    );
  }
}

class _TaskRow extends StatelessWidget {
  const _TaskRow({required this.task, required this.overdue, required this.onToggle});

  final MockTask task;
  final bool overdue;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final due = task.due;
    final source = task.source;
    final meta = <String>[
      if (due != null) dfShortDate(due),
      if (source != null) source,
    ].join(' · ');
    return Semantics(
      checked: task.done,
      label: task.title,
      child: InkWell(
        onTap: onToggle,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 9),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                width: 22,
                height: 22,
                margin: const EdgeInsets.only(top: 1),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: task.done ? t.text : null,
                  border: Border.all(color: task.done ? t.text : (overdue ? t.danger : t.textTertiary), width: 1.6),
                ),
                child: task.done ? Icon(Icons.check, size: 14, color: t.background) : null,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ExcludeSemantics(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        task.title,
                        style: t.label(color: task.done ? t.textTertiary : t.text).copyWith(
                              decoration: task.done ? TextDecoration.lineThrough : null,
                            ),
                      ),
                      if (meta.isNotEmpty)
                        Text(
                          meta,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: t.body(size: 12, color: overdue && !task.done ? t.danger : t.textTertiary),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "New Task" bottom sheet.
Future<void> showNewTaskSheet(BuildContext context) {
  final t = DfThemeScope.of(context);
  final state = OmiAppScope.of(context);
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: t.surface,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (sheetContext) => DfThemeScope(theme: t, child: NewTaskSheet(state: state)),
  );
}

class NewTaskSheet extends StatefulWidget {
  const NewTaskSheet({super.key, required this.state});

  final OmiAppState state;

  @override
  State<NewTaskSheet> createState() => _NewTaskSheetState();
}

class _NewTaskSheetState extends State<NewTaskSheet> {
  final TextEditingController _title = TextEditingController();
  int _due = 0;

  static const List<String> _options = <String>['Today', 'Tomorrow', 'Next week', 'No date'];

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  void _add() {
    final title = _title.text.trim();
    if (title.isEmpty) return;
    final today = widget.state.today;
    final due = switch (_due) {
      0 => today,
      1 => today.add(const Duration(days: 1)),
      2 => today.add(const Duration(days: 7)),
      _ => null,
    };
    widget.state.addTask(title, due);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text('New Task', style: t.headline(24)),
          const SizedBox(height: 12),
          TextField(
            controller: _title,
            autofocus: true,
            cursorColor: t.accent,
            style: t.label(size: 17),
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => _add(),
            decoration: InputDecoration(
              border: InputBorder.none,
              hintText: 'What needs to be done?',
              hintStyle: t.label(size: 17, color: t.textTertiary),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              for (var i = 0; i < _options.length; i++)
                AppChip(_options[i], selected: _due == i, onTap: () => setState(() => _due = i)),
            ],
          ),
          const SizedBox(height: 18),
          DfButton('Add task', onPressed: _title.text.trim().isEmpty ? null : _add),
        ],
      ),
    );
  }
}
