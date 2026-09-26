import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/appearance_preferences.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Settings → Appearance (canvas "Appearance · light and dark"): System, Light or Dark, each shown
/// as a small phone, then Feel — haptics and text size. A choice applies at once, everywhere.
class AppearancePage extends StatefulWidget {
  const AppearancePage({super.key});

  @override
  State<AppearancePage> createState() => _AppearancePageState();
}

class _AppearancePageState extends State<AppearancePage> {
  bool _haptics = OmiHaptics.enabled;

  void _pick(OmiAppearanceMode mode) {
    if (OmiAppearance.mode.value == mode) return;
    OmiHaptics.selection();
    OmiAppearance.mode.value = mode;
  }

  void _setHaptics(bool on) {
    setHapticsEnabled(on);
    setState(() => _haptics = on);
    OmiHaptics.selection();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      key: const ValueKey('settings_page_appearance'),
      appBar: OmiAppBar(leading: const OmiBackButton(), title: Text(l10n.appearance)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.xxl),
        children: [
          ValueListenableBuilder<OmiAppearanceMode>(
            valueListenable: OmiAppearance.mode,
            builder: (context, mode, _) => OmiCard(
              radius: OmiRadius.cardLarge,
              padding: const EdgeInsets.fromLTRB(12, 20, 12, 16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final option in OmiAppearanceMode.values)
                    Expanded(
                      child: _ModeOption(
                        key: ValueKey('appearance_${option.name}'),
                        mode: option,
                        label: switch (option) {
                          OmiAppearanceMode.system => l10n.appearanceSystem,
                          OmiAppearanceMode.light => l10n.appearanceLight,
                          OmiAppearanceMode.dark => l10n.appearanceDark,
                        },
                        selected: mode == option,
                        onTap: () => _pick(option),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 22),
          OmiSettingsGroup(
            header: l10n.feel,
            children: [
              OmiSettingsRow.toggle(
                key: const ValueKey('appearance_haptics'),
                leading: const OmiIconTile(child: OmiGlyph(OmiGlyphs.hand, size: 17)),
                title: l10n.haptics,
                subtitle: l10n.hapticsSubtitle,
                value: _haptics,
                onChanged: _setHaptics,
              ),
              OmiSettingsRow(
                leading: const OmiIconTile(child: OmiGlyph(OmiGlyphs.textLines, size: 17)),
                title: l10n.textSize,
                subtitle: l10n.textSizeSubtitle,
                value: l10n.defaultLabel,
                showChevron: false,
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
            child: Text(l10n.appearanceMotionNote, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          ),
        ],
      ),
    );
  }
}

/// One choice: a small phone in that palette (System is half light, half dark), its name and a
/// radio. The selected phone wears a 3 pt ring.
class _ModeOption extends StatelessWidget {
  const _ModeOption({super.key, required this.mode, required this.label, required this.selected, required this.onTap});

  final OmiAppearanceMode mode;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    final phone = switch (mode) {
      OmiAppearanceMode.light => const _PhonePreview(palette: OmiPalette.light),
      OmiAppearanceMode.dark => const _PhonePreview(palette: OmiPalette.dark),
      OmiAppearanceMode.system => const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _HalfPhone(palette: OmiPalette.light, alignment: Alignment.centerLeft),
            _HalfPhone(palette: OmiPalette.dark, alignment: Alignment.centerRight),
          ],
        ),
    };
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      excludeSemantics: true,
      child: OmiPressable(
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // The canvas's 100 × 204 frame (4 pt inset, 18 pt inner corners) with its 3 pt ring
            // drawn outside it.
            AnimatedContainer(
              duration: motion.standard,
              curve: OmiMotion.springCurve,
              width: 106,
              height: 210,
              padding: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(25), // omi-ux-allow: radius-literal -- the canvas phone frame
                border: Border.all(
                  color: selected ? OmiColors.textPrimary : OmiColors.textPrimary.withValues(alpha: 0),
                  width: 3,
                ),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18), // omi-ux-allow: radius-literal -- a miniature screen
                child: phone,
              ),
            ),
            const SizedBox(height: 10),
            Text(label, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(height: 10),
            AnimatedContainer(
              duration: motion.standard,
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: selected ? OmiColors.textPrimary : Colors.transparent,
                border: selected ? null : Border.all(color: OmiColors.textTertiary, width: 1.5),
              ),
              child: selected ? Icon(Icons.check_rounded, size: 15, color: OmiColors.onAccent) : null,
            ),
          ],
        ),
      ),
    );
  }
}

/// The left or right half of a [_PhonePreview] (the System option shows light beside dark).
class _HalfPhone extends StatelessWidget {
  const _HalfPhone({required this.palette, required this.alignment});

  final OmiPalette palette;
  final Alignment alignment;

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: Align(alignment: alignment, widthFactor: 0.5, child: _PhonePreview(palette: palette)),
    );
  }
}

/// A tiny Today screen in [palette]: a title bar, two cards (one with the device's lit orb) and the
/// dock.
class _PhonePreview extends StatelessWidget {
  const _PhonePreview({required this.palette});

  final OmiPalette palette;

  @override
  Widget build(BuildContext context) {
    final line = palette.surface4;
    Widget bar(double widthFactor, Color color, double height) => FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: widthFactor,
          child: Container(
            height: height,
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(height / 2)),
          ),
        );
    Widget card({bool orb = false}) => Container(
          padding: const EdgeInsets.all(9),
          decoration: BoxDecoration(
              color: palette.surface1,
              borderRadius: BorderRadius.circular(10)), // omi-ux-allow: radius-literal -- a miniature card
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (orb) ...[
                const OmiOrb(size: 12, live: true),
                const SizedBox(height: 6),
              ],
              bar(0.7, line, 7),
              const SizedBox(height: 6),
              bar(0.45, line, 7),
            ],
          ),
        );
    return SizedBox(
      width: 92,
      height: 196,
      child: ColoredBox(
        color: palette.surface0,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(9, 24, 9, 9),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              bar(0.64, palette.textPrimary, 10),
              const SizedBox(height: 7),
              card(orb: true),
              const SizedBox(height: 7),
              card(),
              const Spacer(),
              Opacity(
                opacity: 0.8,
                child: Container(
                  height: 16,
                  decoration: BoxDecoration(
                      color: palette.surface1,
                      borderRadius: BorderRadius.circular(8)), // omi-ux-allow: radius-literal -- a miniature dock
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
