import 'package:flutter/material.dart';

import '../content.dart';
import '../theme.dart';
import '../widgets.dart';
import 'mock_data.dart';

/// Scaffold for pushed app pages: themed background, top bar, scrolling body.
class AppPage extends StatelessWidget {
  const AppPage({super.key, required this.title, required this.children, this.actions = const <Widget>[], this.bottom});

  final String title;
  final List<Widget> children;
  final List<Widget> actions;
  final Widget? bottom;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final bottom = this.bottom;
    return Scaffold(
      backgroundColor: t.background,
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: DfTopBar(title: title, actions: actions),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
                children: children,
              ),
            ),
            if (bottom != null) bottom,
          ],
        ),
      ),
    );
  }
}

/// Rounded square with an icon: conversation and app tiles.
class AppIconTile extends StatelessWidget {
  const AppIconTile({super.key, required this.icon, this.color, this.size = 44});

  final IconData icon;
  final Color? color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final color = this.color;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color ?? t.surface2,
        borderRadius: BorderRadius.circular(size * 0.28),
      ),
      child: Icon(icon, size: size * 0.48, color: color == null ? t.text : Colors.white),
    );
  }
}

/// Filter / suggestion chip.
class AppChip extends StatelessWidget {
  const AppChip(this.label, {super.key, this.selected = false, this.onTap, this.icon});

  final String label;
  final bool selected;
  final VoidCallback? onTap;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final icon = this.icon;
    return Semantics(
      button: onTap != null,
      selected: selected,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
          decoration: BoxDecoration(
            color: selected ? t.text : t.surface,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: selected ? t.text : t.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (icon != null) ...<Widget>[
                Icon(icon, size: 15, color: selected ? t.background : t.textSecondary),
                const SizedBox(width: 5),
              ],
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: t.label(size: 13, weight: FontWeight.w500, color: selected ? t.background : t.text),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One conversation in a list.
class ConversationRow extends StatelessWidget {
  const ConversationRow({super.key, required this.conversation, required this.onTap});

  final MockConversation conversation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final c = conversation;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: <Widget>[
            AppIconTile(icon: c.icon),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    c.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: t.label(weight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${c.timeAndLength} · ${c.category}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: t.body(size: 13, color: t.textTertiary),
                  ),
                ],
              ),
            ),
            if (c.starred) Icon(Icons.star_rounded, size: 18, color: t.glow?.last ?? t.text),
          ],
        ),
      ),
    );
  }
}

/// Big number with a label underneath.
class StatTile extends StatelessWidget {
  const StatTile({super.key, required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          FittedBox(fit: BoxFit.scaleDown, child: Text(value, style: t.headline(26))),
          const SizedBox(height: 2),
          Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: t.body(size: 12, color: t.textTertiary)),
        ],
      ),
    );
  }
}

/// Usage bar ("214 of 300 min used this month").
class UsageBar extends StatelessWidget {
  const UsageBar({super.key, required this.used, required this.limit});

  final int used;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final glow = t.glow;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: SizedBox(
            height: 8,
            child: Stack(
              children: <Widget>[
                Container(color: t.surface2),
                FractionallySizedBox(
                  widthFactor: (used / limit).clamp(0.0, 1.0),
                  child: Container(
                    decoration: BoxDecoration(
                      color: glow == null ? t.accent : null,
                      gradient: glow == null ? null : LinearGradient(colors: glow),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text('$used of $limit min used this month', style: t.body(size: 12, color: t.textTertiary)),
      ],
    );
  }
}

/// Chevron used at the end of tappable settings rows.
Widget appChevron(DfTheme t) => Padding(
      padding: const EdgeInsets.only(left: 6),
      child: Icon(Icons.chevron_right, size: 20, color: t.textTertiary),
    );

/// "Today", "Yesterday" or "Thu, Oct 16".
String appDayLabel(DateTime day, DateTime today) {
  final diff = dfDayDiff(today, day);
  if (diff == 0) return 'Today';
  if (diff == 1) return 'Yesterday';
  return dfDayDate(day);
}

int dfDayDiff(DateTime a, DateTime b) =>
    DateTime.utc(a.year, a.month, a.day).difference(DateTime.utc(b.year, b.month, b.day)).inDays;
