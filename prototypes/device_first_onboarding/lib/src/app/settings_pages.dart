import 'package:flutter/material.dart';

import '../art.dart';
import '../content.dart';
import '../theme.dart';
import '../widgets.dart';
import 'app_state.dart';
import 'app_widgets.dart';
import 'mock_data.dart';
import 'upgrade_page.dart';

/// Settings home, grouped like the app's settings drawer.
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final chevron = appChevron(t);

    DfListRow row(String label, IconData icon, {String? value, WidgetBuilder? page}) => DfListRow(
          icon: icon,
          label: label,
          value: value,
          trailing: chevron,
          onTap: () => page == null ? dfNotInPrototype(context, label) : pushDf<void>(context, page),
        );

    return AppPage(
      title: 'Settings',
      children: <Widget>[
        DfCard(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: <Widget>[
              Container(
                width: 52,
                height: 52,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: t.glow == null ? t.surface2 : null,
                  gradient: t.glow == null ? null : LinearGradient(colors: t.glow!),
                ),
                child: Text(
                  state.userName.characters.first,
                  style: t.headline(24).copyWith(color: t.glow == null ? t.text : Colors.white),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(state.userName, style: t.label(size: 17, weight: FontWeight.w600)),
                    Text('alex@example.com', style: t.body(size: 13, color: t.textTertiary)),
                  ],
                ),
              ),
              _PlanBadge(unlimited: state.unlimited),
            ],
          ),
        ),
        const SizedBox(height: 18),
        DfCard(
          child: Column(
            children: <Widget>[
              row('Plan & Usage', Icons.bar_chart_rounded, page: (_) => const PlanUsagePage()),
              row('Device', Icons.radio_button_checked, value: 'Connected', page: (_) => const DevicePage()),
              row('Refer a friend', Icons.card_giftcard, value: 'Give a month'),
            ],
          ),
        ),
        const SizedBox(height: 14),
        DfCard(
          child: Column(
            children: <Widget>[
              row('Recording & Transcription', Icons.mic_none, page: (_) => const RecordingPage()),
              row('Voice', Icons.record_voice_over_outlined),
              row('Notifications & Display', Icons.notifications_none),
              row('Integrations', Icons.extension_outlined, page: (_) => const AppsPage()),
              row('Memories', Icons.psychology_outlined, page: (_) => const MemoriesPage()),
              row('Goals', Icons.flag_outlined),
            ],
          ),
        ),
        const SizedBox(height: 14),
        DfCard(
          child: Column(
            children: <Widget>[
              row('Data & Privacy', Icons.shield_outlined),
              row('Help', Icons.help_outline),
              row('Send feedback', Icons.chat_bubble_outline),
              row('Developer', Icons.code),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Center(
          child: TextButton(
            onPressed: () => dfNotInPrototype(context, 'Signing out'),
            child: Text('Sign out', style: t.label(color: t.danger, weight: FontWeight.w600)),
          ),
        ),
        Center(child: Text('Omi 2.0 · prototype', style: t.body(size: 12, color: t.textTertiary))),
      ],
    );
  }
}

class _PlanBadge extends StatelessWidget {
  const _PlanBadge({required this.unlimited});

  final bool unlimited;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: unlimited ? t.text : t.surface2,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        unlimited ? 'Unlimited' : 'Free',
        style: t.label(size: 12, weight: FontWeight.w600, color: unlimited ? t.background : t.textSecondary),
      ),
    );
  }
}

/// Plan & Usage: the plan card and listening stats by period.
class PlanUsagePage extends StatefulWidget {
  const PlanUsagePage({super.key});

  @override
  State<PlanUsagePage> createState() => _PlanUsagePageState();
}

class _PlanUsagePageState extends State<PlanUsagePage> {
  int _period = 1;

  static const List<String> _periods = <String>['Today', 'This Month', 'This Year', 'All Time'];

  // (listened, words, memories, conversations) per period.
  static const List<(String, String, String, String)> _stats = <(String, String, String, String)>[
    ('77 min', '9.8k', '6', '3'),
    ('214 min', '27k', '41', '38'),
    ('31 h', '232k', '310', '402'),
    ('44 h', '329k', '466', '571'),
  ];

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final (listened, words, memories, conversations) = _stats[_period];
    final ends = state.trialEnds;
    return AppPage(
      title: 'Plan & Usage',
      children: <Widget>[
        DfCard(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(child: Text(state.unlimited ? 'Unlimited' : 'Free', style: t.headline(28))),
                  _PlanBadge(unlimited: state.unlimited),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                state.unlimited
                    ? 'Free trial until ${ends == null ? '—' : dfLongDate(ends)}, then ${DfPricing.yearly}.'
                    : '${MockData.freeMinutes} cloud minutes a month, then on-device transcription.',
                style: t.body(size: 14),
              ),
              const SizedBox(height: 14),
              if (!state.unlimited) ...<Widget>[
                const UsageBar(used: MockData.usedMinutes, limit: MockData.freeMinutes),
                const SizedBox(height: 16),
                DfButton('Upgrade to Unlimited', onPressed: () => showUpgrade(context, capHit: false)),
              ] else
                DfButton(
                  'Manage plan',
                  kind: DfButtonKind.secondary,
                  onPressed: () => dfNotInPrototype(context, 'Plan management'),
                ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        DfSegmented(labels: _periods, index: _period, onChanged: (i) => setState(() => _period = i)),
        const SizedBox(height: 14),
        Row(
          children: <Widget>[
            Expanded(child: StatTile(value: listened, label: 'Listened')),
            const SizedBox(width: 10),
            Expanded(child: StatTile(value: words, label: 'Words heard')),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: <Widget>[
            Expanded(child: StatTile(value: memories, label: 'Memories')),
            const SizedBox(width: 10),
            Expanded(child: StatTile(value: conversations, label: 'Conversations')),
          ],
        ),
        if (!state.unlimited) ...<Widget>[
          const SizedBox(height: 20),
          DfCard(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: <Widget>[
                Icon(Icons.bolt_rounded, color: t.glow?.last ?? t.text),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Preview: what users see when they hit the monthly cap',
                    style: t.body(size: 14, color: t.text),
                  ),
                ),
                TextButton(
                  onPressed: () => showUpgrade(context, capHit: true),
                  child: Text('Show', style: t.label(size: 14, weight: FontWeight.w600)),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// Device: status, button actions, LED and mic, firmware, unpair.
class DevicePage extends StatefulWidget {
  const DevicePage({super.key});

  @override
  State<DevicePage> createState() => _DevicePageState();
}

class _DevicePageState extends State<DevicePage> {
  double _led = 0.6;
  double _gain = 0.5;
  bool _offlineSync = true;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    return AppPage(
      title: 'Device',
      children: <Widget>[
        const Center(child: DfPendant(size: 120, showCord: false, glow: true)),
        const SizedBox(height: 14),
        Text("${state.userName}'s Omi", textAlign: TextAlign.center, style: t.headline(28)),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Container(width: 8, height: 8, decoration: BoxDecoration(color: t.success, shape: BoxShape.circle)),
            const SizedBox(width: 6),
            Flexible(child: Text('Connected · 82% battery', style: t.body(size: 14))),
          ],
        ),
        const SizedBox(height: 20),
        const DfSectionTitle('Button'),
        DfCard(
          child: Column(
            children: <Widget>[
              DfListRow(
                label: 'Double tap',
                value: 'Star conversation',
                trailing: appChevron(t),
                onTap: () => dfNotInPrototype(context, 'Button actions'),
              ),
              DfListRow(
                label: 'Long press',
                value: 'Ask Omi',
                trailing: appChevron(t),
                onTap: () => dfNotInPrototype(context, 'Button actions'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        const DfSectionTitle('Hardware'),
        DfCard(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _SliderRow(label: 'LED brightness', value: _led, onChanged: (v) => setState(() => _led = v)),
              _SliderRow(label: 'Mic gain', value: _gain, onChanged: (v) => setState(() => _gain = v)),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text('Offline sync', style: t.label()),
                          Text(
                            'Records without your phone, syncs later',
                            style: t.body(size: 12, color: t.textTertiary),
                          ),
                        ],
                      ),
                    ),
                    DfToggle(value: _offlineSync, onChanged: (v) => setState(() => _offlineSync = v)),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        const DfSectionTitle('About'),
        DfCard(
          child: Column(
            children: <Widget>[
              DfListRow(label: 'Firmware', value: '3.0.2 · Up to date', valueColor: t.success),
              const DfListRow(label: 'Model', value: 'Omi'),
              const DfListRow(label: 'Serial number', value: 'OMI-4F2A-91C0'),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Center(
          child: TextButton(
            onPressed: () => dfNotInPrototype(context, 'Unpairing'),
            child: Text('Unpair and Forget Device', style: t.label(color: t.danger, weight: FontWeight.w600)),
          ),
        ),
      ],
    );
  }
}

class _SliderRow extends StatelessWidget {
  const _SliderRow({required this.label, required this.value, required this.onChanged});

  final String label;
  final double value;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(child: Text(label, style: t.label())),
            Text('${(value * 100).round()}%', style: t.label(color: t.textTertiary)),
          ],
        ),
        SliderTheme(
          data: SliderThemeData(
            activeTrackColor: t.text,
            inactiveTrackColor: t.surface2,
            thumbColor: t.text,
            overlayColor: t.text.withValues(alpha: 0.08),
            trackHeight: 4,
          ),
          child: Slider(
              value: value, onChanged: onChanged, semanticFormatterCallback: (v) => '$label ${(v * 100).round()}%'),
        ),
      ],
    );
  }
}

/// Memories: what Omi has learned, searchable and filtered by category.
class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> {
  String _category = 'All';
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final items = MockData.memories
        .where((m) => _category == 'All' || m.category == _category)
        .where((m) => _query.isEmpty || m.text.toLowerCase().contains(_query.toLowerCase()))
        .toList();
    return AppPage(
      title: 'Memories',
      actions: <Widget>[
        IconButton(
          tooltip: 'Add memory',
          onPressed: () => dfNotInPrototype(context, 'Adding memories'),
          icon: Icon(Icons.add, color: t.text),
        ),
      ],
      children: <Widget>[
        Text('${MockData.memories.length} things Omi knows about you', style: t.body(size: 14, color: t.textTertiary)),
        const SizedBox(height: 12),
        DfSearchField(hint: 'Search memories', onChanged: (q) => setState(() => _query = q)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            for (final c in MockData.memoryCategories)
              AppChip(c, selected: _category == c, onTap: () => setState(() => _category = c)),
          ],
        ),
        const SizedBox(height: 14),
        for (final m in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: DfCard(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(m.text, style: t.label()),
                  const SizedBox(height: 4),
                  Text('${m.category} · ${m.when}', style: t.body(size: 12, color: t.textTertiary)),
                ],
              ),
            ),
          ),
        if (items.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 24),
            child: Text('No memories match.', textAlign: TextAlign.center, style: t.body(size: 14)),
          ),
      ],
    );
  }
}

/// Integrations / apps: explore and enable.
class AppsPage extends StatelessWidget {
  const AppsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final featured = MockData.apps[3];
    return AppPage(
      title: 'Integrations',
      children: <Widget>[
        Row(
          children: <Widget>[
            Text('Apps', style: t.headline(28)),
            const SizedBox(width: 8),
            const DfBadge('BETA'),
          ],
        ),
        const SizedBox(height: 4),
        Text('Connect Omi to the tools you already use.', style: t.body(size: 14)),
        const SizedBox(height: 14),
        GestureDetector(
          onTap: () => pushDf<void>(context, (_) => AppDetailPage(app: featured)),
          child: Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(22),
              color: t.glow == null ? t.surface2 : null,
              gradient: t.glow == null
                  ? null
                  : LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: t.glow!),
            ),
            child: Row(
              children: <Widget>[
                AppIconTile(icon: featured.icon, color: Colors.white.withValues(alpha: 0.25), size: 52),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        'FEATURED',
                        style: TextStyle(
                          fontSize: 11,
                          letterSpacing: 1.4,
                          fontWeight: FontWeight.w700,
                          color: t.glow == null ? t.textTertiary : Colors.white70,
                        ),
                      ),
                      Text(
                        featured.name,
                        style: t.headline(24).copyWith(color: t.glow == null ? t.text : Colors.white),
                      ),
                      Text(
                        featured.tagline,
                        style: TextStyle(fontSize: 13, color: t.glow == null ? t.textSecondary : Colors.white),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),
        const DfSectionTitle('Popular'),
        for (final app in MockData.apps)
          InkWell(
            onTap: () => pushDf<void>(context, (_) => AppDetailPage(app: app)),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 9),
              child: Row(
                children: <Widget>[
                  AppIconTile(icon: app.icon, color: app.color),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(app.name, style: t.label(weight: FontWeight.w600)),
                        Text(
                          app.tagline,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: t.body(size: 13, color: t.textTertiary),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  if (state.isEnabled(app))
                    Icon(Icons.check_circle, size: 20, color: t.success)
                  else
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Icon(Icons.star_rounded, size: 15, color: t.textTertiary),
                        Text(app.rating.toStringAsFixed(1), style: t.label(size: 13, color: t.textTertiary)),
                      ],
                    ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class AppDetailPage extends StatelessWidget {
  const AppDetailPage({super.key, required this.app});

  final MockApp app;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final state = OmiAppScope.of(context);
    final enabled = state.isEnabled(app);
    return AppPage(
      title: '',
      children: <Widget>[
        Row(
          children: <Widget>[
            AppIconTile(icon: app.icon, color: app.color, size: 68),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(app.name, style: t.headline(26)),
                  Text('${app.category} · by ${app.author}', style: t.body(size: 13, color: t.textTertiary)),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),
        Row(
          children: <Widget>[
            Expanded(child: StatTile(value: app.rating.toStringAsFixed(1), label: '${app.reviews} ratings')),
            const SizedBox(width: 10),
            Expanded(child: StatTile(value: app.installs, label: 'Installs')),
          ],
        ),
        const SizedBox(height: 18),
        DfButton(
          enabled ? 'Disable' : 'Enable',
          kind: enabled ? DfButtonKind.secondary : DfButtonKind.primary,
          onPressed: () => state.toggleApp(app),
        ),
        const SizedBox(height: 10),
        DfButton(
          'Chat with ${app.name}',
          kind: DfButtonKind.text,
          onPressed: () => dfNotInPrototype(context, 'App chat'),
        ),
        const SizedBox(height: 14),
        Text('About', style: t.label(size: 17, weight: FontWeight.w600)),
        const SizedBox(height: 6),
        Text(app.description, style: t.body(size: 15, color: t.text, height: 1.5)),
        const SizedBox(height: 22),
        Text('Ratings & Reviews', style: t.label(size: 17, weight: FontWeight.w600)),
        const SizedBox(height: 10),
        for (final (who, text) in const <(String, String)>[
          ('Priya', 'Set it up once and forgot about it. Exactly what I wanted.'),
          ('Marco', 'Works well; I wish it let me pick which conversations to send.'),
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: DfCard(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Expanded(child: Text(who, style: t.label(size: 14, weight: FontWeight.w600))),
                      for (var i = 0; i < 5; i++) Icon(Icons.star_rounded, size: 14, color: t.text),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(text, style: t.body(size: 14)),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

/// Recording & Transcription settings.
class RecordingPage extends StatefulWidget {
  const RecordingPage({super.key});

  @override
  State<RecordingPage> createState() => _RecordingPageState();
}

class _RecordingPageState extends State<RecordingPage> {
  final Map<String, bool> _on = <String, bool>{
    'Speaker labels': true,
    'Save audio recordings': false,
    'Transcribe on device when offline': true,
    'Auto-create tasks': true,
  };

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return AppPage(
      title: 'Recording',
      children: <Widget>[
        DfCard(
          child: Column(
            children: <Widget>[
              DfListRow(
                label: 'Language',
                value: 'English',
                trailing: appChevron(t),
                onTap: () => dfNotInPrototype(context, 'Language'),
              ),
              DfListRow(
                label: 'Transcription',
                value: 'Omi Cloud',
                trailing: appChevron(t),
                onTap: () => dfNotInPrototype(context, 'Transcription models'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        DfCard(
          child: Column(
            children: <Widget>[
              for (final entry in _on.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: Row(
                    children: <Widget>[
                      Expanded(child: Text(entry.key, style: t.label())),
                      const SizedBox(width: 8),
                      DfToggle(value: entry.value, onChanged: (v) => setState(() => _on[entry.key] = v)),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Audio is deleted after transcription unless "Save audio recordings" is on.',
          style: t.body(size: 12, color: t.textTertiary),
        ),
      ],
    );
  }
}
