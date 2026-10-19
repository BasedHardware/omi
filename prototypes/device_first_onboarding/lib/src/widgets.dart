import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'content.dart';
import 'theme.dart';

/// A full screen: optional full-bleed [header], then padded content that
/// fills the screen (so a [Spacer] pushes the actions to the bottom) and
/// scrolls when it does not fit.
class DfPage extends StatelessWidget {
  const DfPage({super.key, required this.children, this.header, this.spacing = 14, this.wash = false});

  final List<Widget> children;
  final Widget? header;
  final double spacing;

  /// Paint the faint aurora wash behind the page (light, Pocket-style screens).
  final bool wash;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final header = this.header;
    return DecoratedBox(
      decoration: wash ? BoxDecoration(gradient: t.wash) : BoxDecoration(color: t.background),
      child: SafeArea(
        top: header == null,
        child: CustomScrollView(
          slivers: <Widget>[
            if (header != null) SliverToBoxAdapter(child: header),
            SliverFillRemaining(
              hasScrollBody: false,
              child: Padding(
                padding: EdgeInsets.fromLTRB(24, header == null ? 16 : 20, 24, 16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: _spaced(children, spacing)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

List<Widget> _spaced(List<Widget> children, double gap) {
  final out = <Widget>[];
  for (var i = 0; i < children.length; i++) {
    if (i > 0 && children[i] is! Spacer && children[i - 1] is! Spacer) {
      out.add(SizedBox(height: gap));
    }
    out.add(children[i]);
  }
  return out;
}

enum DfButtonKind { primary, secondary, text }

/// The one button used everywhere: 54pt tall, full width.
class DfButton extends StatelessWidget {
  const DfButton(this.label, {super.key, required this.onPressed, this.kind = DfButtonKind.primary});

  final String label;
  final VoidCallback? onPressed;
  final DfButtonKind kind;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final background = switch (kind) {
      DfButtonKind.primary => t.accent,
      DfButtonKind.secondary => t.surface,
      DfButtonKind.text => Colors.transparent,
    };
    final foreground = switch (kind) {
      DfButtonKind.primary => t.onAccent,
      DfButtonKind.secondary => t.text,
      DfButtonKind.text => t.textSecondary,
    };
    final radius = BorderRadius.circular(t.buttonRadius);
    final outlined = kind == DfButtonKind.secondary && t.isLight;
    return Opacity(
      opacity: onPressed == null ? 0.35 : 1,
      child: Material(
        color: background,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: outlined ? BorderSide(color: t.border) : BorderSide.none,
        ),
        child: InkWell(
          borderRadius: radius,
          onTap: onPressed,
          child: SizedBox(
            height: 54,
            child: Center(
              child: Text(label, style: t.label(size: 17, color: foreground, weight: FontWeight.w600)),
            ),
          ),
        ),
      ),
    );
  }
}

/// Segmented progress for the paired part of onboarding.
class DfProgress extends StatelessWidget {
  const DfProgress({super.key, required this.step, this.total = 5});

  final int step;
  final int total;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Semantics(
      label: 'Step $step of $total',
      child: Row(
        children: <Widget>[
          for (var i = 0; i < total; i++)
            Container(
              width: 22,
              height: 3,
              margin: EdgeInsets.only(right: i == total - 1 ? 0 : 4),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(2),
                color: i < step && t.hasGlow ? null : t.accent.withValues(alpha: i < step ? 1 : 0.25),
                gradient: i < step && t.hasGlow ? t.accentGradient : null,
              ),
            ),
        ],
      ),
    );
  }
}

class DfHeadline extends StatelessWidget {
  const DfHeadline(this.text, {super.key, this.size = 32, this.align});

  final String text;
  final double size;
  final TextAlign? align;

  @override
  Widget build(BuildContext context) => Text(text, textAlign: align, style: DfThemeScope.of(context).headline(size));
}

class DfBody extends StatelessWidget {
  const DfBody(this.text, {super.key, this.align});

  final String text;
  final TextAlign? align;

  @override
  Widget build(BuildContext context) => Text(text, textAlign: align, style: DfThemeScope.of(context).body());
}

class DfCaption extends StatelessWidget {
  const DfCaption(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Text(text, textAlign: TextAlign.center, style: t.body(size: 12, color: t.textTertiary));
  }
}

class DfEyebrow extends StatelessWidget {
  const DfEyebrow(this.text, {super.key, this.color});

  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) => Text(text.toUpperCase(), style: DfThemeScope.of(context).eyebrow(color: color));
}

class DfCard extends StatelessWidget {
  const DfCard({super.key, required this.child, this.padding = EdgeInsets.zero});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BorderRadius.circular(16),
        border: t.isLight ? Border.all(color: t.border) : null,
      ),
      child: child,
    );
  }
}

/// One row inside a [DfCard]: icon, label, and a value or trailing widget.
class DfListRow extends StatelessWidget {
  const DfListRow({
    super.key,
    required this.label,
    this.value,
    this.icon,
    this.iconColor,
    this.trailing,
    this.emphasize = false,
    this.labelColor,
    this.valueColor,
    this.onTap,
  });

  final String label;
  final String? value;
  final IconData? icon;
  final Color? iconColor;
  final Widget? trailing;
  final bool emphasize;
  final Color? labelColor;
  final Color? valueColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final weight = emphasize ? FontWeight.w600 : FontWeight.w400;
    final icon = this.icon;
    final value = this.value;
    final trailing = this.trailing;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        child: Row(
          children: <Widget>[
            if (icon != null) ...<Widget>[Icon(icon, size: 20, color: iconColor ?? t.text), const SizedBox(width: 12)],
            Expanded(flex: 3, child: Text(label, style: t.label(weight: weight, color: labelColor))),
            if (value != null) const SizedBox(width: 12),
            // Right-aligned value that wraps (rather than overflows) when it is long.
            if (value != null)
              Flexible(
                flex: 2,
                child: Align(
                  alignment: Alignment.centerRight,
                  child: Text(
                    value,
                    textAlign: TextAlign.right,
                    style: t.label(color: valueColor ?? t.textTertiary, weight: weight),
                  ),
                ),
              ),
            if (trailing != null) trailing,
          ],
        ),
      ),
    );
  }
}

/// Free vs. paid comparison. Cells of exactly '✓' or '✕' render as icons.
class DfCompareTable extends StatelessWidget {
  const DfCompareTable({super.key, required this.columns, required this.rows});

  final List<String> columns;
  final List<List<String>> rows;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final width = columns.length > 2 ? 64.0 : 88.0;
    final last = columns.length - 1;
    return DfCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              const Spacer(),
              for (var i = 0; i < columns.length; i++)
                SizedBox(
                  width: width,
                  child: Text(
                    columns[i],
                    textAlign: TextAlign.center,
                    style: t.label(size: 12, weight: FontWeight.w600, color: i == last ? t.text : t.textTertiary),
                  ),
                ),
            ],
          ),
          for (final row in rows)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Row(
                children: <Widget>[
                  Expanded(child: Text(row.first, style: t.label(size: 13))),
                  for (var i = 1; i < row.length; i++)
                    SizedBox(width: width, child: Center(child: _cell(t, row[i], highlight: i == row.length - 1))),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _cell(DfTheme t, String value, {required bool highlight}) {
    if (value == '✓') return Icon(Icons.check, size: 16, color: t.success, semanticLabel: 'Included');
    if (value == '✕') return Icon(Icons.close, size: 15, color: t.danger, semanticLabel: 'Not included');
    return Text(
      value,
      textAlign: TextAlign.center,
      style: t.label(
        size: 12,
        weight: highlight ? FontWeight.w600 : FontWeight.w400,
        color: highlight ? t.text : t.textSecondary,
      ),
    );
  }
}

/// Today / reminder day / last day of the trial.
class DfTrialTimeline extends StatelessWidget {
  const DfTrialTimeline({super.key, required this.trial});

  final TrialLength trial;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final steps = <(IconData, String, String)>[
      (Icons.lock_open_outlined, 'Today', r'Full access, $0'),
      (Icons.notifications_none, 'Day ${trial.reminderDay}', 'We remind you'),
      (Icons.credit_card, 'Day ${trial.days}', 'Trial ends'),
    ];
    return DfCard(
      padding: const EdgeInsets.all(14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (final (icon, title, subtitle) in steps)
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(icon, size: 18, color: t.text),
                  const SizedBox(height: 4),
                  Text(title, style: t.label(size: 13, weight: FontWeight.w600)),
                  Text(subtitle, style: t.body(size: 11, color: t.textTertiary)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class DfBadge extends StatelessWidget {
  const DfBadge(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(borderRadius: BorderRadius.circular(6), gradient: t.badgeGradient),
      child: Text(text.toUpperCase(), style: t.label(size: 10, weight: FontWeight.w700, color: t.onAccent)),
    );
  }
}

/// A selectable plan row on the paywalls.
class DfPlanOption extends StatelessWidget {
  const DfPlanOption({
    super.key,
    required this.title,
    required this.subtitle,
    required this.price,
    required this.per,
    required this.selected,
    required this.onTap,
    this.badge,
  });

  final String title;
  final String subtitle;
  final String price;
  final String per;
  final bool selected;
  final VoidCallback onTap;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final badge = this.badge;
    return Semantics(
      selected: selected,
      button: true,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: t.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: selected ? t.accent : t.border, width: selected ? 2 : 1),
          ),
          child: Row(
            children: <Widget>[
              DfRadio(selected: selected),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: <Widget>[
                        Text(title, style: t.label(size: 16, weight: FontWeight.w600)),
                        if (badge != null) DfBadge(badge),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle, style: t.body(size: 13, height: 1.3)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: <Widget>[
                  Text(price, style: t.label(size: 16, weight: FontWeight.w600)),
                  Text(per, style: t.body(size: 12, color: t.textTertiary)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class DfRadio extends StatelessWidget {
  const DfRadio({super.key, required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: selected ? t.accent : Colors.transparent,
        border: Border.all(color: selected ? t.accent : t.textTertiary, width: 1.5),
      ),
    );
  }
}

/// iOS-style switch, drawn so both directions control its colours.
class DfToggle extends StatelessWidget {
  const DfToggle({super.key, required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Semantics(
      toggled: value,
      child: GestureDetector(
        onTap: () => onChanged(!value),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          width: 51,
          height: 31,
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(color: value ? t.success : t.surface2, borderRadius: BorderRadius.circular(16)),
          child: AnimatedAlign(
            duration: const Duration(milliseconds: 150),
            alignment: value ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              width: 27,
              height: 27,
              decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
            ),
          ),
        ),
      ),
    );
  }
}

/// Back arrow row for pushed screens.
class DfBackRow extends StatelessWidget {
  const DfBackRow({super.key, required this.onBack, this.trailing});

  final VoidCallback onBack;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final trailing = this.trailing;
    return Row(
      children: <Widget>[
        IconButton(
          onPressed: onBack,
          tooltip: 'Back',
          padding: EdgeInsets.zero,
          alignment: Alignment.centerLeft,
          icon: Icon(Icons.arrow_back_ios_new, size: 20, color: t.text),
        ),
        const Spacer(),
        if (trailing != null) trailing,
      ],
    );
  }
}

/// The Omi mark: a ring and the wordmark.
class DfOmiMark extends StatelessWidget {
  const DfOmiMark({super.key, this.size = 18, this.color});

  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final c = color ?? t.text;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: c, width: size * 0.16),
          ),
        ),
        SizedBox(width: size * 0.35),
        Text('omi', style: TextStyle(fontSize: size, fontWeight: FontWeight.w700, color: c, letterSpacing: -0.3)),
      ],
    );
  }
}

/// Pill-style segmented control ("Summary | Transcript").
class DfSegmented extends StatelessWidget {
  const DfSegmented({super.key, required this.labels, required this.index, required this.onChanged});

  final List<String> labels;
  final int index;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: t.surface2, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: <Widget>[
          for (var i = 0; i < labels.length; i++)
            Expanded(
              child: Semantics(
                button: true,
                selected: i == index,
                child: GestureDetector(
                  onTap: () => onChanged(i),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    decoration: BoxDecoration(
                      color: i == index ? t.surface : Colors.transparent,
                      borderRadius: BorderRadius.circular(9),
                      boxShadow: i == index && t.isLight
                          ? <BoxShadow>[BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 6)]
                          : null,
                    ),
                    child: Text(
                      labels[i],
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: t.label(
                        size: 13,
                        weight: FontWeight.w600,
                        color: i == index ? t.text : t.textTertiary,
                      ),
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

/// Rounded search / text field.
class DfSearchField extends StatelessWidget {
  const DfSearchField(
      {super.key, required this.hint, this.onChanged, this.autofocus = false, this.icon = Icons.search});

  final String hint;
  final ValueChanged<String>? onChanged;
  final bool autofocus;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: t.isLight ? t.surface : t.surface,
        borderRadius: BorderRadius.circular(14),
        border: t.isLight ? Border.all(color: t.border) : null,
      ),
      child: TextField(
        autofocus: autofocus,
        cursorColor: t.accent,
        style: t.label(size: 16),
        onChanged: onChanged,
        decoration: InputDecoration(
          border: InputBorder.none,
          icon: Icon(icon, size: 18, color: t.textTertiary),
          hintText: hint,
          hintStyle: t.label(size: 16, color: t.textTertiary),
        ),
      ),
    );
  }
}

/// Small section title above a card ("Action items", "Today").
class DfSectionTitle extends StatelessWidget {
  const DfSectionTitle(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final trailing = this.trailing;
    return Padding(
      padding: const EdgeInsets.only(top: 6, bottom: 2),
      child: Row(
        children: <Widget>[
          Expanded(child: Text(text, style: t.label(size: 13, weight: FontWeight.w600, color: t.textTertiary))),
          if (trailing != null) trailing,
        ],
      ),
    );
  }
}

/// Top bar for pushed pages: back, centred title, optional actions.
class DfTopBar extends StatelessWidget {
  const DfTopBar({super.key, required this.title, this.onBack, this.actions = const <Widget>[]});

  final String title;
  final VoidCallback? onBack;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return SizedBox(
      height: 52,
      child: Row(
        children: <Widget>[
          SizedBox(
            width: 96,
            child: Align(
              alignment: Alignment.centerLeft,
              child: IconButton(
                tooltip: 'Back',
                onPressed: onBack ?? () => Navigator.of(context).maybePop(),
                icon: Icon(Icons.arrow_back_ios_new, size: 20, color: t.text),
              ),
            ),
          ),
          Expanded(
            child: Text(
              title,
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: t.label(size: 17, weight: FontWeight.w600),
            ),
          ),
          SizedBox(
            width: 96,
            child: Row(mainAxisAlignment: MainAxisAlignment.end, children: actions),
          ),
        ],
      ),
    );
  }
}

/// Status-bar icons that suit the theme (dark icons on Aurora Light).
class DfStatusBar extends StatelessWidget {
  const DfStatusBar({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: t.isLight ? SystemUiOverlayStyle.dark : SystemUiOverlayStyle.light,
      child: child,
    );
  }
}

/// A screen with [sheet] presented over a dimmed, inert [behind] screen.
/// Used for the checkout sheets and the winback, so each is its own step.
class DfSheetOver extends StatelessWidget {
  const DfSheetOver({super.key, required this.behind, required this.sheet, this.floating = false});

  final Widget behind;
  final Widget sheet;

  /// A floating card with margins (winback) rather than an edge-to-edge sheet.
  final bool floating;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final media = MediaQuery.of(context);
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        IgnorePointer(child: ExcludeSemantics(child: behind)),
        ColoredBox(color: Colors.black.withValues(alpha: t.isLight ? 0.32 : 0.55)),
        Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: floating
                ? EdgeInsets.fromLTRB(10, media.padding.top + 24, 10, media.padding.bottom + 10)
                : EdgeInsets.only(top: media.padding.top + 24),
            child: Container(
              decoration: BoxDecoration(
                color: t.surface,
                borderRadius:
                    floating ? BorderRadius.circular(30) : const BorderRadius.vertical(top: Radius.circular(28)),
              ),
              clipBehavior: Clip.antiAlias,
              child: SafeArea(top: false, bottom: !floating, child: SingleChildScrollView(child: sheet)),
            ),
          ),
        ),
      ],
    );
  }
}

/// Pushes [builder] as a full page that keeps the current [DfTheme].
Future<T?> pushDf<T>(BuildContext context, WidgetBuilder builder) {
  final theme = DfThemeScope.of(context);
  return Navigator.of(context).push<T>(
    MaterialPageRoute<T>(
      builder: (_) => DfThemeScope(
        theme: theme,
        child: DfStatusBar(child: Builder(builder: builder)),
      ),
    ),
  );
}

/// Snackbar for controls that exist in the app but not in this prototype.
void dfNotInPrototype(BuildContext context, String what) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text('$what isn\u2019t part of this prototype')));
}
